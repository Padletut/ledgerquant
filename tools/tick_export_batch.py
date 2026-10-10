"""Run the TickExport cBot over a long interval, one bounded cTrader CLI backtest at a time.

Each chunk is one TickExport run (at most seven days). A chunk that hits the row
limit is split in half and retried under new run IDs. Completed runs are verified
against their manifest and skipped on the next invocation, so the batch can be
resumed. Every attempt is appended to ``batch.jsonl`` in the output directory.

The cTrader ID and account number are read from CTRADER_ID and
CTRADER_ACCOUNT_NUMBER (environment or the ignored .env file) and are never
printed. Stored CLI logs are redacted. The password stays in
credentials/ctrader-cli.pwd. The exporter's manifest still records the account
number until the account registry exists.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
IMAGE_DIGEST = "sha256:285484fad431e0ffa4ca96662e82ea66cead93c97cf0e3c46006e80cab4734ba"
IMAGE = f"ghcr.io/spotware/ctrader-console@{IMAGE_DIGEST}"
ALGO_DIR = REPO / "cbots/LedgerQuant.TickExport/LedgerQuant.TickExport/bin/Release/net6.0"
PASSWORD_FILE = REPO / "credentials/ctrader-cli.pwd"
ROW_LIMIT_MESSAGE = "row limit"
MIN_CHUNK = timedelta(hours=2)


@dataclass(frozen=True)
class Chunk:
    start: datetime
    end: datetime

    def run_id(self, symbol: str, attempt: int) -> str:
        base = f"{symbol.lower()}_{self.start:%Y%m%dT%H%M}_{self.end:%Y%m%dT%H%M}"
        return base if attempt == 1 else f"{base}_r{attempt}"

    def halves(self) -> list["Chunk"]:
        middle = self.start + (self.end - self.start) / 2
        middle = middle.replace(minute=0, second=0, microsecond=0)
        return [Chunk(self.start, middle), Chunk(middle, self.end)]


def chunks(start: datetime, end: datetime, days: float) -> list[Chunk]:
    if not 0 < days <= 7:
        raise ValueError("chunk length must be within (0, 7] days")
    step, result, cursor = timedelta(days=days), [], start
    while cursor < end:
        result.append(Chunk(cursor, min(cursor + step, end)))
        cursor += step
    return result


def cli_time(value: datetime) -> str:
    return value.strftime("%d/%m/%Y %H:%M")


def cli_end(chunk: Chunk, margin_days: int, now: datetime) -> datetime:
    """End of the CLI backtest: past the chunk for an end witness, but never in the future.

    A CLI backtest whose end lies in the future waits for data that does not exist.
    """
    latest = (now - timedelta(hours=1)).replace(second=0, microsecond=0)
    return min(chunk.end + timedelta(days=margin_days), latest)


def utc_text(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def verify(out: Path, run_id: str) -> dict | None:
    """Return the manifest when the CSV matches its row count, size and hash."""
    manifest_path, data_path = out / f"{run_id}.manifest.json", out / f"{run_id}.ticks.csv"
    if not manifest_path.is_file() or not data_path.is_file():
        return None
    manifest = json.loads(manifest_path.read_text())
    digest, size, lines = hashlib.sha256(), 0, 0
    with data_path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
            size += len(block)
            lines += block.count(b"\n")
    if (manifest.get("data_sha256") == digest.hexdigest() and manifest.get("data_bytes") == size
            and manifest.get("row_count") == lines - 1):
        return manifest
    return None


def redact(text: str, ctid: str, account: str) -> str:
    """Remove the cTrader login, any e-mail address and the account number from CLI output."""
    text = text.replace(ctid, "<ctid>").replace(account, "<account>")
    return re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "<email>", text)


def outcome(log: str) -> tuple[str, str]:
    for line in log.splitlines():
        if "TICK_EXPORT_COMPLETE" in line:
            return "COMPLETE", line.strip()
        if "TICK_EXPORT_FAILED" in line or "TICK_EXPORT_INCOMPLETE" in line:
            status = "ROW_LIMIT" if ROW_LIMIT_MESSAGE in line else "FAILED"
            return status, line.strip()
    return "PENDING", ""


def credentials() -> tuple[str, str]:
    values = dict(os.environ)
    env_file = REPO / ".env"
    if env_file.is_file():
        for line in env_file.read_text().splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() in ("CTRADER_ID", "CTRADER_ACCOUNT_NUMBER"):
                values.setdefault(key.strip(), value.strip().strip("'\""))
    ctid, account = values.get("CTRADER_ID", ""), values.get("CTRADER_ACCOUNT_NUMBER", "")
    if not ctid or not account.isdecimal():
        sys.exit("CTRADER_ID and a numeric CTRADER_ACCOUNT_NUMBER are required (environment or .env)")
    return ctid, account


def run_one(symbol: str, chunk: Chunk, run_id: str, out: Path, args, ctid: str, account: str) -> tuple[str, str]:
    name = f"lq-tick-export-{run_id}".replace("_", "-")
    command = [
        "docker", "run", "-d", "--name", name,
        "--mount", f"type=bind,src={ALGO_DIR},dst=/algo,readonly",
        "--mount", f"type=bind,src={PASSWORD_FILE},dst=/run/secrets/ctrader-cli.pwd,readonly",
        "--mount", f"type=bind,src={out},dst=/export",
        IMAGE, "backtest", "/algo/LedgerQuant.TickExport.algo",
        f"--ctid={ctid}", "--pwd-file=/run/secrets/ctrader-cli.pwd",
        f"--account={account}", f"--symbol={symbol}", "--period=h1",
        f"--start={cli_time(chunk.start - timedelta(days=args.margin_days))}",
        f"--end={cli_time(cli_end(chunk, args.margin_days, datetime.now(timezone.utc)))}",
        "--data-mode=ticks",
        f"--StartUtc={utc_text(chunk.start)}", f"--EndExclusiveUtc={utc_text(chunk.end)}",
        "--OutputDirectory=/export", f"--RunId={run_id}",
        f"--ExpectedAccountNumber={account}", f"--ExpectedBrokerName={args.broker}",
        f"--CliImageDigest={IMAGE_DIGEST}", f"--MaximumRows={args.max_rows}", "--full-access",
    ]
    started = subprocess.run(command, capture_output=True, text=True)
    if started.returncode != 0:
        return "FAILED", "docker run failed: " + started.stderr.strip().splitlines()[-1][:200]
    deadline, status, detail = time.monotonic() + args.timeout_minutes * 60, "TIMEOUT", ""
    try:
        while time.monotonic() < deadline:
            time.sleep(10)
            log = subprocess.run(["docker", "logs", name], capture_output=True, text=True)
            status, detail = outcome(log.stdout + log.stderr)
            if status != "PENDING":
                break
            state = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", name],
                                   capture_output=True, text=True).stdout.strip()
            if state != "true":
                status, detail = "FAILED", "CLI exited without an export marker"
                break
        else:
            status = "TIMEOUT"
    finally:
        log = subprocess.run(["docker", "logs", name], capture_output=True, text=True)
        (out / f"{run_id}.cli.log").write_text(redact(log.stdout + log.stderr, ctid, account))
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    return status, detail


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--start", required=True, type=date.fromisoformat, help="first UTC date")
    parser.add_argument("--end", required=True, type=date.fromisoformat, help="exclusive UTC date")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--chunk-days", type=float, default=7)
    parser.add_argument("--margin-days", type=int, default=4, help="CLI warm-up and end-witness margin")
    parser.add_argument("--max-rows", type=int, default=1_000_000)
    parser.add_argument("--timeout-minutes", type=int, default=90)
    parser.add_argument("--broker", default="IC Markets EU Ltd")
    args = parser.parse_args()

    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    ctid, account = credentials()
    start = datetime.combine(args.start, datetime.min.time(), timezone.utc)
    end = datetime.combine(args.end, datetime.min.time(), timezone.utc)
    # Each run needs a tick at or after its end as a witness. An end that is not
    # followed by an already traded tick would only wait for its timeout.
    if end > datetime.now(timezone.utc) - timedelta(hours=1):
        sys.exit("--end must lie in the past, before ticks that have already traded")
    queue = chunks(start, end, args.chunk_days)
    ledger = out / "batch.jsonl"
    while queue:
        chunk = queue.pop(0)
        attempt = 1
        while verify(out, chunk.run_id(args.symbol, attempt)) is None and any(
                out.glob(chunk.run_id(args.symbol, attempt) + ".*")):
            attempt += 1
        run_id = chunk.run_id(args.symbol, attempt)
        if verify(out, run_id) is not None:
            print(f"{run_id} VERIFIED_EXISTING", flush=True)
            continue
        status, detail = run_one(args.symbol, chunk, run_id, out, args, ctid, account)
        if status == "COMPLETE" and verify(out, run_id) is None:
            status = "UNVERIFIED"
        record = {"run_id": run_id, "symbol": args.symbol, "start_utc": utc_text(chunk.start),
                  "end_exclusive_utc": utc_text(chunk.end), "status": status,
                  "recorded_at_utc": utc_text(datetime.now(timezone.utc))}
        if status != "COMPLETE":
            record["detail"] = redact(detail, ctid, account)
        with ledger.open("a") as handle:
            handle.write(json.dumps(record) + "\n")
        print(f"{run_id} {status}", flush=True)
        if status == "ROW_LIMIT" and chunk.end - chunk.start >= 2 * MIN_CHUNK:
            queue[:0] = chunk.halves()
        elif status in ("FAILED", "TIMEOUT", "UNVERIFIED") and attempt < 2:
            queue.insert(0, chunk)


if __name__ == "__main__":
    main()

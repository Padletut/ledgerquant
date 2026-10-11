"""Run one analyst variant through replay and journal every step.

For each symbol, decision times are processed in order: an open shadow position is
moved forward to the decision time, the context visible at that time is built,
the model is called within the run's spending cap, and the validated answer is
applied (open, hold, close or adjust). Every decision, with its context, request,
raw response, validation and cost, and every closed trade, with its static-exit
and mirrored-direction comparisons, is appended to the run's journal.

This is a retrospective simulation over backfilled data and a single-analyst
variant without Jev or the Risk Engine; results are in R and labelled as such.
"""

import argparse
import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from pydantic import ValidationError

from ledgerquant.models.generation import ModelProfile
from ledgerquant.pipeline.analyst import CONTRACT_VERSION, INSTRUCTIONS, TOOL, Analysis, unknown_citations, validate
from ledgerquant.records import canonical, digest
from ledgerquant.replay.context import NEWS_RECIPE, NewsArchive, replay_context
from ledgerquant.replay.market import TickArchive
from ledgerquant.replay.positions import Position, advance, close, exit_side, mirrored, static_outcome
from ledgerquant.replay.schedule import plan


class Budget:
    """A hard spending cap shared by all symbols; reservations use maximum output."""

    def __init__(self, cap_usd: float, profile: ModelProfile):
        self.cap, self.profile, self.spent, self.lock = Decimal(str(cap_usd)), profile, Decimal(0), threading.Lock()

    def worst_case(self, request: dict) -> Decimal:
        incoming = len(canonical(request).encode()) + 4096  # bytes exceed tokens; framing margin
        return (Decimal(str(self.profile.input_usd_per_million)) * incoming
                + Decimal(str(self.profile.output_usd_per_million)) * self.profile.max_output_tokens) / 10 ** 6

    def reserve(self, request: dict) -> Decimal | None:
        with self.lock:
            amount = self.worst_case(request)
            if self.spent + amount > self.cap:
                return None
            self.spent += amount
            return amount

    def settle(self, reserved: Decimal, input_tokens: int | None, output_tokens: int | None) -> Decimal:
        """Replace the reservation by the actual cost; unknown usage keeps the reservation."""
        if input_tokens is None or output_tokens is None:
            return reserved
        actual = (Decimal(str(self.profile.input_usd_per_million)) * input_tokens
                  + Decimal(str(self.profile.output_usd_per_million)) * output_tokens) / 10 ** 6
        with self.lock:
            self.spent += actual - reserved
        return actual


class Journal:
    def __init__(self, directory: Path):
        self.directory, self.lock = directory, threading.Lock()
        directory.mkdir(parents=True, exist_ok=False)

    def append(self, name: str, record: dict) -> None:
        with self.lock, (self.directory / f"{name}.jsonl").open("a") as handle:
            handle.write(json.dumps(record, default=str) + "\n")


def decide(provider, context: dict, position_state: dict | None, budget: Budget) -> dict:
    """One model call; returns the decision record without applying it."""
    payload = dict(context, position=position_state)
    record = {"context_sha256": digest(payload), "context": payload}
    try:
        request = provider.prepare(INSTRUCTIONS, [provider.user_message(canonical(payload))], [TOOL])
    except ValueError as exc:
        return record | {"status": "REQUEST_TOO_LARGE" if "BUDGET" in str(exc) else "REQUEST_INVALID"}
    reserved = budget.reserve(request)
    record["request_sha256"] = digest(request)
    if reserved is None:
        return record | {"status": "BUDGET_STOP"}
    started = time.monotonic()
    generation = provider.invoke(request)
    record |= {"latency_seconds": round(time.monotonic() - started, 2), "provider_status": generation.status,
               "input_tokens": generation.input_tokens, "output_tokens": generation.output_tokens,
               "provider_response": generation.raw}
    record["cost_usd"] = str(budget.settle(reserved, generation.input_tokens, generation.output_tokens))
    if generation.status != "COMPLETED":
        return record | {"status": generation.status}
    call = generation.calls[0]
    if call.name != TOOL["name"]:
        return record | {"status": "WRONG_TOOL"}
    try:
        analysis = Analysis.model_validate(json.loads(call.arguments))
    except (ValueError, ValidationError):
        return record | {"status": "INVALID_MODEL_OUTPUT"}
    return record | {"analysis": analysis.model_dump(mode="json"),
                     "unknown_citations": unknown_citations(analysis, context),
                     "status": validate(analysis, context, position_state)}


def run_symbol(symbol: str, times: list, archive_root: Path, provider, budget: Budget, journal: Journal) -> None:
    ticks, news = TickArchive(archive_root), NewsArchive(archive_root)
    position, opening = None, None

    def finish(exit_: dict) -> None:
        nonlocal position, opening
        closes_by = datetime.fromisoformat(opening["close_by_utc"])
        exit_["label"] = opening["label"]
        exit_["static"] = static_outcome(ticks, symbol, opening["direction"],
                                         datetime.fromisoformat(opening["opened_at_utc"]), Decimal(opening["entry"]),
                                         Decimal(opening["stop"]), Decimal(opening["target"]), closes_by)
        exit_["mirrored"] = mirrored(ticks, opening, symbol)
        journal.append("trades", exit_)
        position, opening = None, None

    for at, label in times:
        if position and (exit_ := advance(ticks, position, at)):
            finish(exit_)
        context = replay_context(symbol, at, ticks, news)
        latest = context["market"]["latest"]
        state = position.state(Decimal(latest[exit_side(position.direction)])) if position and latest else None
        decision_id = f"{symbol}:{at.isoformat()}"
        base = {"decision_id": decision_id, "symbol": symbol, "decision_at_utc": at.isoformat(), "label": label}
        if context["market"]["status"] != "READY":
            journal.append("decisions", base | {"status": f"CONTEXT_{context['market']['status']}",
                                                "context_sha256": digest(context)})
            continue
        record = base | decide(provider, context, state, budget)
        journal.append("decisions", record)
        if record["status"] == "BUDGET_STOP":
            break
        if record["status"] != "VALID":
            continue
        analysis = record["analysis"]
        action = analysis["action"]
        if position is None and action in ("LONG", "SHORT"):
            setup = analysis["setup"]
            entry = Decimal(latest["ask"] if action == "LONG" else latest["bid"])
            close_by = at + timedelta(minutes=setup["max_holding_minutes"])
            position = Position(symbol, action, at, entry, Decimal(setup["stop"]), Decimal(setup["target"]),
                                close_by, decision_id)
            opening = {"direction": action, "entry": str(entry), "stop": setup["stop"], "target": setup["target"],
                       "opened_at_utc": at.isoformat(), "close_by_utc": close_by.isoformat(), "label": label,
                       "quote": {"bid": latest["bid"], "ask": latest["ask"]}}
        elif position is not None and action == "CLOSE":
            finish(close(position, at, Decimal(latest[exit_side(position.direction)]), "AGENT_CLOSE"))
        elif position is not None and action == "ADJUST":
            levels = analysis["adjustment"]
            position.adjustments.append({"at_utc": at.isoformat(), "stop": levels["new_stop"],
                                         "target": levels["new_target"]})
            position.stop = Decimal(levels["new_stop"]) if levels["new_stop"] else position.stop
            position.target = Decimal(levels["new_target"]) if levels["new_target"] else position.target
    if position is not None:
        exit_ = advance(ticks, position, position.close_by)
        finish(exit_ if exit_ else close(position, position.checked_until, position.entry, "OPEN_AT_END"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the GPT analyst through replay")
    parser.add_argument("--start", required=True, type=date.fromisoformat)
    parser.add_argument("--end", required=True, type=date.fromisoformat, help="exclusive")
    parser.add_argument("--symbols", nargs="+", default=["EURUSD", "GBPUSD", "XAUUSD"])
    parser.add_argument("--hours", nargs="+", type=int, default=list(range(7, 21)))
    parser.add_argument("--profile", type=Path, default=Path("configs/models/openai_gpt54_mini.profile.json"))
    parser.add_argument("--key-file", type=Path, default=Path("credentials/openai-api.key"))
    parser.add_argument("--archive", type=Path, default=Path("data/archive"))
    parser.add_argument("--runs", type=Path, default=Path("data/replay_runs"))
    parser.add_argument("--cost-cap", type=float, required=True, help="hard cap in USD for the whole run")
    parser.add_argument("--max-decisions", type=int, help="per symbol, for smoke tests")
    args = parser.parse_args()

    from ledgerquant.integrations.model_providers.openai import OpenAIResponses

    profile = ModelProfile.model_validate_json(args.profile.read_text())
    times = plan(args.start, args.end, [profile], hours=args.hours)
    if args.max_decisions:
        times = times[: args.max_decisions]
    run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_{CONTRACT_VERSION.replace('/', '')}_{profile.model}"
    journal = Journal(args.runs / run_id)
    manifests = {p.parent.name: hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted(args.archive.glob("*/*/manifest.json")) + sorted(args.archive.glob("*/manifest.json"))}
    (journal.directory / "run.json").write_text(json.dumps({
        "run_id": run_id, "kind": "replay (retrospective simulation over backfilled data)",
        "variant": {"contract": CONTRACT_VERSION, "instructions_sha256": digest(INSTRUCTIONS),
                    "tool_sha256": digest(TOOL), "news_recipe": NEWS_RECIPE,
                    "model_profile": profile.model_dump(mode="json"),
                    "pipeline": "single GPT analyst; no Jev, no Risk Engine; market entries only"},
        "inputs": {"archive_manifest_sha256": manifests},
        "plan": {"start": str(args.start), "end_exclusive": str(args.end), "symbols": args.symbols,
                 "hours_utc": args.hours, "decisions_per_symbol": len(times),
                 "labels": sorted({name for _, name in times})},
        "cost_cap_usd": args.cost_cap,
    }, indent=1, default=str))
    budget = Budget(args.cost_cap, profile)
    provider = OpenAIResponses(profile, args.key_file.read_text().strip())
    with ThreadPoolExecutor(max_workers=len(args.symbols)) as pool:
        for future in [pool.submit(run_symbol, s, times, args.archive, provider, budget, journal)
                       for s in args.symbols]:
            future.result()
    print(json.dumps({"run_id": run_id, "spent_usd": str(budget.spent.quantize(Decimal("0.0001")))}))


if __name__ == "__main__":
    main()

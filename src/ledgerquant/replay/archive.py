"""Build a columnar tick archive from verified TickExport runs.

Each symbol is rebuilt from all of its verified export runs into Parquet files
partitioned by symbol and UTC date. A run is used only when its CSV matches the
manifest's row count, size and SHA-256, and runs must not overlap. The archive
manifest records every source run, so each archived tick can be traced back.

Exported ticks are backfilled: they have no real `available_at`. Replay treats a
tick as visible at its event time, which is a declared assumption (see the
architecture, Section 5.2).
"""

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import duckdb

ARCHIVE_VERSION = "ticks_v1"
CSV_COLUMNS = {"ordinal": "BIGINT", "event_time_utc": "VARCHAR", "bid": "DECIMAL(18,6)", "ask": "DECIMAL(18,6)"}


class ArchiveError(ValueError):
    pass


def verified_runs(export_dir: Path) -> list[dict]:
    """Manifests whose CSV matches row count, size and hash, ordered by start."""
    runs = []
    for manifest_path in sorted(export_dir.glob("*.manifest.json")):
        manifest = json.loads(manifest_path.read_text())
        data_path = export_dir / manifest["data_file"]
        digest, size, lines = hashlib.sha256(), 0, 0
        with data_path.open("rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
                size += len(block)
                lines += block.count(b"\n")
        if (digest.hexdigest(), size, lines - 1) != (manifest["data_sha256"], manifest["data_bytes"],
                                                    manifest["row_count"]):
            raise ArchiveError(f"{data_path.name} does not match its manifest")
        runs.append({"run_id": manifest["run_id"], "path": data_path, "rows": manifest["row_count"],
                     "sha256": manifest["data_sha256"], "symbol": manifest["broker_symbol"],
                     "start": manifest["requested_start_utc"][:19], "end": manifest["requested_end_exclusive_utc"][:19]})
    runs.sort(key=lambda run: run["start"])
    for earlier, later in zip(runs, runs[1:]):
        if later["start"] < earlier["end"]:
            raise ArchiveError(f"runs {earlier['run_id']} and {later['run_id']} overlap")
    return runs


def build_symbol(export_dir: Path, archive_root: Path, symbol: str) -> dict:
    """Rebuild one symbol's archive; the previous version is replaced only after success."""
    runs = verified_runs(export_dir)
    if not runs:
        raise ArchiveError(f"no verified runs in {export_dir}")
    if {run["symbol"] for run in runs} != {symbol}:
        raise ArchiveError("export directory contains another symbol")
    target = archive_root / ARCHIVE_VERSION / f"symbol={symbol}"
    staging = archive_root / ARCHIVE_VERSION / f".staging-{symbol}"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    files = [str(run["path"]) for run in runs]
    con = duckdb.connect()
    # cTrader writes seven fractional digits with millisecond precision; six are kept.
    con.execute(f"""
        COPY (
            SELECT CAST(substr(event_time_utc, 1, 26) AS TIMESTAMP) AS event_time_utc,
                   bid, ask,
                   regexp_extract(filename, '([^/]+)\\.ticks\\.csv$', 1) AS source_run,
                   ordinal,
                   CAST(CAST(substr(event_time_utc, 1, 26) AS TIMESTAMP) AS DATE) AS date
            FROM read_csv($files, columns = $columns, header = true, filename = true)
            ORDER BY event_time_utc, source_run, ordinal
        ) TO '{staging}' (FORMAT parquet, PARTITION_BY (date), COMPRESSION zstd)
    """, {"files": files, "columns": CSV_COLUMNS})
    archived = con.execute(f"SELECT count(*) FROM read_parquet('{staging}/*/*.parquet')").fetchone()[0]
    expected = sum(run["rows"] for run in runs)
    if archived != expected:
        shutil.rmtree(staging)
        raise ArchiveError(f"{symbol}: archived {archived} rows, sources hold {expected}")
    manifest = {
        "archive_version": ARCHIVE_VERSION, "symbol": symbol, "rows": archived,
        "start_utc": runs[0]["start"], "end_exclusive_utc": runs[-1]["end"],
        "visibility": "backfilled; visible at event time (declared assumption)",
        "built_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "duckdb_version": duckdb.__version__,
        "sources": [{k: run[k] for k in ("run_id", "rows", "sha256", "start", "end")} for run in runs],
    }
    (staging / "manifest.json").write_text(json.dumps(manifest, indent=1))
    shutil.rmtree(target, ignore_errors=True)
    staging.rename(target)
    return manifest


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Build the replay tick archive from verified exports")
    parser.add_argument("--exports", type=Path, default=Path("data/ctrader_tick_exports/post_cutoff_v1"))
    parser.add_argument("--archive", type=Path, default=Path("data/archive"))
    parser.add_argument("--symbol", action="append", required=True)
    args = parser.parse_args()
    for symbol in args.symbol:
        manifest = build_symbol(args.exports / symbol, args.archive, symbol)
        print(json.dumps({k: manifest[k] for k in ("symbol", "rows", "start_utc", "end_exclusive_utc")}))


if __name__ == "__main__":
    main()

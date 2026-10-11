"""Snapshot news and macro tables from the capture database into the replay archive.

Replay reads pinned files instead of the live database, so a replay can be run
again on exactly the same inputs. The snapshot is read through `docker exec` and
`psql`, which needs no database port on the host and changes nothing in the
database. The manifest records row counts and the latest `first_seen_at` per
table: data that arrived later is not in the snapshot.
"""

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import duckdb

SNAPSHOT_VERSION = "news_v1"
QUERIES = {
    "news_items": """SELECT source, source_item_id, url, title, summary, published_at, first_seen_at,
                            available_at, backfilled, filter_version, details::text AS details
                     FROM news.items""",
    "macro_release_dates": """SELECT release_id, release_name, release_date, first_seen_at
                              FROM news.macro_release_dates""",
    "macro_observations": """SELECT series_id, observation_date, realtime_start, value, first_seen_at
                             FROM news.macro_observations""",
}
TIMESTAMP_COLUMNS = {"published_at", "first_seen_at", "available_at"}


def export_csv(container: str, query: str, target: Path) -> None:
    # Timestamps leave the database in UTC so the files carry no session time zone.
    command = ["docker", "exec", "-i", "-e", "PGTZ=UTC", container, "psql", "-X", "-v", "ON_ERROR_STOP=1",
               "-U", "ledgerquant", "-d", "ledgerquant", "-c",
               f"\\copy ({' '.join(query.split())}) TO STDOUT WITH (FORMAT csv, HEADER)"]
    with target.open("wb") as handle:
        result = subprocess.run(command, stdout=handle, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(f"psql export failed: {result.stderr.decode(errors='replace')[-300:]}")


def build_snapshot(archive_root: Path, container: str = "ledgerquant-capture-postgres-1") -> dict:
    target = Path(archive_root) / SNAPSHOT_VERSION
    staging = Path(archive_root) / f".staging-{SNAPSHOT_VERSION}"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    con = duckdb.connect()
    tables = {}
    for name, query in QUERIES.items():
        csv_path = staging / f"{name}.csv"
        export_csv(container, query, csv_path)
        con.execute(f"CREATE TABLE {name} AS SELECT * FROM read_csv('{csv_path}', header = true, all_varchar = true)")
        columns = [row[0] for row in con.execute(f"DESCRIBE {name}").fetchall()]
        # Postgres prints UTC timestamps as '2026-10-10 21:32:53.6+00'; store naive UTC timestamps.
        select = ", ".join(
            f"CAST(replace({c}, '+00', '') AS TIMESTAMP) AS {c}" if c in TIMESTAMP_COLUMNS else
            f"CAST({c} AS DATE) AS {c}" if c in ("release_date", "observation_date", "realtime_start") else
            f"CAST({c} AS INTEGER) AS {c}" if c == "release_id" else
            f"({c} = 't') AS {c}" if c == "backfilled" else c
            for c in columns)
        # Sorted by time so a replay query for one window reads only the row groups it needs.
        order = "published_at" if name == "news_items" else "first_seen_at"
        con.execute(f"COPY (SELECT {select} FROM {name} ORDER BY {order}) TO '{staging / name}.parquet' "
                    "(FORMAT parquet, COMPRESSION zstd)")
        rows, latest = con.execute(
            f"SELECT count(*), max(CAST(replace(first_seen_at, '+00', '') AS TIMESTAMP)) FROM {name}").fetchone()
        tables[name] = {"rows": rows, "latest_first_seen_utc": latest.isoformat() if latest else None}
        csv_path.unlink()
    manifest = {"snapshot_version": SNAPSHOT_VERSION, "container": container,
                "taken_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "tables": tables}
    (staging / "manifest.json").write_text(json.dumps(manifest, indent=1))
    shutil.rmtree(target, ignore_errors=True)
    staging.rename(target)
    return manifest


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Snapshot news and macro data for replay")
    parser.add_argument("--archive", type=Path, default=Path("data/archive"))
    parser.add_argument("--container", default="ledgerquant-capture-postgres-1")
    args = parser.parse_args()
    print(json.dumps(build_snapshot(args.archive, args.container)["tables"]))


if __name__ == "__main__":
    main()

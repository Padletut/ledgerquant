"""Backfill GDELT GKG batches for a past interval, labelled as backfilled.

Resumable: batches already fetched, or confirmed missing (404), are skipped.
Backfilled items keep `available_at` empty because a download today does not show
when the batch could first have been read.
"""

import argparse
from datetime import date, datetime, timedelta, timezone

from ledgerquant.capture.settings import database_url_from_environment
from ledgerquant.news.collector import Collector, client, log
from ledgerquant.news.storage import create_store


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start", required=True, type=date.fromisoformat, help="first UTC date")
    parser.add_argument("--end", required=True, type=date.fromisoformat, help="exclusive UTC date")
    parser.add_argument("--pause", type=float, default=0.5, help="seconds between downloads")
    args = parser.parse_args()
    start = datetime.combine(args.start, datetime.min.time(), timezone.utc)
    end = datetime.combine(args.end, datetime.min.time(), timezone.utc) - timedelta(minutes=15)
    collector = Collector(create_store(database_url_from_environment()), client())
    # A batch that is not published yet would return 404 and be recorded as missing.
    latest = collector.latest_gkg()
    if latest is None:
        raise SystemExit("cannot read the latest published GDELT batch")
    end = min(end, latest)
    log("gdelt_backfill_started", start=start, end=end)
    collector.gkg_batches(start, end, backfill=True, pause=args.pause)
    log("gdelt_backfill_finished", start=start, end=end)


if __name__ == "__main__":
    main()

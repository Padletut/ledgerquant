import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal as D
from collections import defaultdict
from pathlib import Path
from ledgerquant.replay.market import TickArchive
from ledgerquant.replay.positions import static_outcome
from ledgerquant.replay.costs import weekend_close
ticks = TickArchive(Path(os.environ.get("LEDGERQUANT_ARCHIVE", "data/archive")))
WEEKS = ["2025-09-08", "2025-10-13", "2025-11-10", "2025-12-08", "2026-01-12", "2026-02-09", "2026-03-09"]
GEOM = {"XAUUSD": D("0.0055"), "EURUSD": D("0.0024"), "GBPUSD": D("0.0025")}  # median risk share of price
RR = D("1.5")
for sym in ("XAUUSD", "EURUSD", "GBPUSD"):
    for direction in ("LONG", "SHORT"):
        per_week = defaultdict(D); n = 0
        for w in WEEKS:
            start = date.fromisoformat(w)
            for day in range(5):
                for h in range(7, 21):
                    at = datetime(start.year, start.month, start.day, h, tzinfo=timezone.utc) + timedelta(days=day)
                    q = ticks.latest(sym, at)
                    if not q: continue
                    sign = 1 if direction == "LONG" else -1
                    entry = D(q["ask"] if direction == "LONG" else q["bid"])
                    risk = entry * GEOM[sym]
                    o = static_outcome(ticks, sym, direction, at, entry, entry - sign * risk, entry + sign * risk * RR,
                                       weekend_close(at), "WEEKEND_CLOSE")
                    if o: per_week[w] += D(o["r"]); n += 1
        print(f"always {direction:5s} {sym}: n={n} total {sum(per_week.values()):+.1f} R  ({sum(per_week.values())/n:+.3f}/trade)  "
              + " ".join(f"{w[2:7]}:{v:+.0f}" for w, v in per_week.items()))

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
GEOM = {"XAUUSD": D("0.0055"), "EURUSD": D("0.0024"), "GBPUSD": D("0.0025")}
RR = D("1.5")
for sym in ("EURUSD", "GBPUSD", "XAUUSD"):
    per_week, n = defaultdict(D), 0
    for w in WEEKS:
        s = date.fromisoformat(w)
        for day in range(5):
            for h in range(7, 21):
                at = datetime(s.year, s.month, s.day, h, tzinfo=timezone.utc) + timedelta(days=day)
                now, then = ticks.latest(sym, at), ticks.latest(sym, at - timedelta(hours=23))
                if not now or not then: continue
                m_now, m_then = (D(now["bid"]) + D(now["ask"])) / 2, (D(then["bid"]) + D(then["ask"])) / 2
                direction = "LONG" if m_now > m_then else "SHORT"
                sign = 1 if direction == "LONG" else -1
                entry = D(now["ask"] if sign > 0 else now["bid"]); risk = entry * GEOM[sym]
                o = static_outcome(ticks, sym, direction, at, entry, entry - sign * risk, entry + sign * risk * RR,
                                   weekend_close(at), "WEEKEND_CLOSE")
                if o: per_week[w] += D(o["r"]); n += 1
    tot = sum(per_week.values())
    print(f"23h momentum {sym}: n={n} total {tot:+.1f} R ({tot/n:+.3f}/trade) " + " ".join(f"{w[2:7]}:{v:+.0f}" for w, v in per_week.items()))

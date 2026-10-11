import os
import json
from datetime import datetime, timedelta
from decimal import Decimal as D
from pathlib import Path
from collections import defaultdict
from ledgerquant.replay.market import TickArchive
from ledgerquant.replay.positions import static_outcome
from ledgerquant.replay.costs import weekend_close
RUNS = Path(os.environ.get("LEDGERQUANT_RUNS", "data/replay_runs")); ticks = TickArchive(Path(os.environ.get("LEDGERQUANT_ARCHIVE", "data/archive")))
out = defaultdict(lambda: defaultdict(list))
for d in RUNS.glob("2026*/"):
    r = json.loads((d / "run.json").read_text())
    if len(r["plan"]["hours_utc"]) != 14: continue
    v, w = r["variant"]["contract"][-1], r["plan"]["start"]
    dec = {x["decision_id"]: x for x in map(json.loads, (d / "decisions.jsonl").read_text().splitlines()) if "analysis" in x}
    tp = d / "trades.jsonl"
    for t in map(json.loads, tp.read_text().splitlines() if tp.exists() else []):
        target = D(dec[t["decision_id"]]["analysis"]["setup"]["target"])
        o = datetime.fromisoformat(t["opened_at_utc"])
        args = (ticks, t["symbol"], t["direction"], o, D(t["entry"]), D(t["initial_stop"]), target)
        wk = static_outcome(*args, weekend_close(o), "WEEKEND_CLOSE")
        oe = static_outcome(*args, o + timedelta(days=30), "OPEN_ENDED")
        out[v]["weekend"].append(D(wk.get("r_gross", wk["r"]))); out[v]["open"].append(D(oe["r"]))
        out[v]["open_exit"].append(oe["exit_reason"]); out[v]["week"].append(w)
        out[v]["crossed"].append(datetime.fromisoformat(oe["closed_at_utc"]) > weekend_close(o))
for v, x in sorted(out.items()):
    six = [i for i, w in enumerate(x["week"]) if w != "2026-03-09"]
    cross = [i for i in range(len(x["open"])) if x["crossed"][i]]
    print(f"v{v}: n={len(x['open'])}  weekend-close {sum(x['weekend']):+.2f}  open-ended {sum(x['open']):+.2f}"
          f"  | 6 weeks: n={len(six)} weekend {sum(x['weekend'][i] for i in six):+.2f} open {sum(x['open'][i] for i in six):+.2f}"
          f"  | trades that cross the weekend when open-ended: {len(cross)}, weekend {sum(x['weekend'][i] for i in cross):+.2f}"
          f" -> open {sum(x['open'][i] for i in cross):+.2f}")

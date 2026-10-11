"""Decompose analyst/3 vs analyst/4: exits, entries held under the same rules, entry geometry."""
import os
import glob
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal as D
from pathlib import Path

from ledgerquant.replay.costs import policy_rates, weekend_close
from ledgerquant.replay.market import TickArchive
from ledgerquant.replay.positions import static_outcome
from ledgerquant.replay.run import net_of_swap

RUNS = Path(os.environ.get("LEDGERQUANT_RUNS", "data/replay_runs"))
ticks = TickArchive(Path(os.environ.get("LEDGERQUANT_ARCHIVE", "data/archive")))


def load(d, name):
    p = d / name
    return [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []


runs = {}
for d in RUNS.glob("2026*/"):
    r = json.loads((d / "run.json").read_text())
    if len(r["plan"]["hours_utc"]) == 14:
        runs[(r["variant"]["contract"][-1], r["plan"]["start"])] = d
weeks = sorted({w for _, w in runs})

rows = []  # one row per trade with all variants
for (v, w), d in runs.items():
    decisions = {x["decision_id"]: x for x in load(d, "decisions.jsonl") if "analysis" in x}
    for t in load(d, "trades.jsonl"):
        dec = decisions[t["decision_id"]]
        setup = dec["analysis"]["setup"]
        q = dec["context"]["market"]["latest"]
        rates = policy_rates(dec["context"].get("macro") or {})
        opened = datetime.fromisoformat(t["opened_at_utc"])
        entry, stop, target = D(t["entry"]), D(t["initial_stop"]), D(setup["target"])
        held = static_outcome(ticks, t["symbol"], t["direction"], opened, entry, stop, target,
                              weekend_close(opened), "WEEKEND_CLOSE")
        held = net_of_swap(held, t["symbol"], rates)
        actual = t if v == "4" else net_of_swap(t, t["symbol"], rates)
        spread = D(q["ask"]) - D(q["bid"])
        risk, reward = abs(entry - stop), abs(target - entry)
        rows.append({
            "v": v, "week": w, "symbol": t["symbol"], "dir": t["direction"], "at": t["opened_at_utc"],
            "exit": t["exit_reason"], "style": setup.get("style", "-"),
            "actual_gross": D(actual["r_gross"]), "actual_net": D(actual["r"]),
            "held_gross": D(held["r_gross"]), "held_net": D(held["r"]), "held_exit": held["exit_reason"],
            "held_hours": (datetime.fromisoformat(held["closed_at_utc"]) - opened).total_seconds() / 3600,
            "rr": reward / risk, "risk_spreads": risk / spread if spread else None, "risk_pct": risk / entry * 100,
            "hour": opened.hour, "weekday": opened.weekday(),
        })


def s(xs):
    return f"{sum(xs, D(0)):+7.2f}"


def table(title, key, filt=lambda r: True):
    print(f"\n## {title}")
    groups = defaultdict(list)
    for r in rows:
        if filt(r):
            groups[(key(r), r["v"])].append(r)
    for k in sorted({k for k, _ in groups}, key=str):
        parts = []
        for v in "34":
            g = groups.get((k, v), [])
            parts.append(f"v{v}: n={len(g):3d} actual {s([r['actual_gross'] for r in g])} "
                         f"held {s([r['held_gross'] for r in g])} held-net {s([r['held_net'] for r in g])}")
        print(f"{str(k):12s} | " + " | ".join(parts))


print("# Exit reasons, actual gross R")
for v in "34":
    c = defaultdict(list)
    for r in rows:
        if r["v"] == v:
            c[r["exit"]].append(r["actual_gross"])
    print(f"v{v}", {k: (len(x), f"{sum(x, D(0)):+.2f}") for k, x in c.items()})

table("Total (actual vs the same entries held to stop/target/weekend close, no management)", lambda r: "all")
table("By week", lambda r: r["week"])
table("By symbol", lambda r: r["symbol"])
table("By direction", lambda r: r["dir"])
table("v3 by its actual exit reason", lambda r: r["exit"], lambda r: r["v"] == "3")
table("v4 by style", lambda r: r["style"], lambda r: r["v"] == "4")

print("\n## Held-to-rules exit reasons")
for v in "34":
    print(f"v{v}", dict(Counter(r["held_exit"] for r in rows if r["v"] == v)),
          "median hours", round(statistics.median(r["held_hours"] for r in rows if r["v"] == v), 1))

print("\n## Entry geometry (median)")
for v in "34":
    for sym in ("EURUSD", "GBPUSD", "XAUUSD"):
        g = [r for r in rows if r["v"] == v and r["symbol"] == sym]
        print(f"v{v} {sym}: n={len(g):3d} reward/risk {statistics.median(r['rr'] for r in g):.2f} "
              f"risk in spreads {statistics.median(r["risk_spreads"] for r in g if r["risk_spreads"]):.1f} "
              f"risk % of price {statistics.median(r['risk_pct'] for r in g):.3f}")

print("\n## Same symbol, hour and direction entered by both")
k3 = {(r["symbol"], r["at"], r["dir"]) for r in rows if r["v"] == "3"}
k4 = {(r["symbol"], r["at"], r["dir"]) for r in rows if r["v"] == "4"}
print("v3", len(k3), "v4", len(k4), "both", len(k3 & k4))
both = [r for r in rows if (r["symbol"], r["at"], r["dir"]) in k3 & k4]
for v in "34":
    g = [r for r in both if r["v"] == v]
    print(f"v{v} on shared entries: actual {s([r['actual_gross'] for r in g])} held {s([r['held_gross'] for r in g])}")
json.dump([{k: str(x) if isinstance(x, D) else x for k, x in r.items()} for r in rows],
          open(sys.argv[1] if len(sys.argv) > 1 else "/dev/null", "w"), indent=0)

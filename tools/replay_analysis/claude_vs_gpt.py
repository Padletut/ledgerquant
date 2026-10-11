"""Claude Opus 4.6 vs GPT-5.4 mini (analyst/4) week by week, plus what Claude's waiting cost.

Cost of waiting: at every Claude WAIT or NO_SIGNAL without a position where its news and
chart views agree on a direction, enter that direction with Claude's own geometry, hold
to stop/target/weekend close, net of costs. This is what acting on its stated view would
have earned. Rows with no agreed direction are not counted.
"""
import os
import glob
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal as D
from pathlib import Path

from ledgerquant.replay.baselines import geometry, momentum_direction
from ledgerquant.replay.costs import policy_rates, weekend_close
from ledgerquant.replay.market import TickArchive
from ledgerquant.replay.positions import static_outcome
from ledgerquant.replay.run import net_of_swap

RUNS = Path(os.environ.get("LEDGERQUANT_RUNS", "data/replay_runs"))
ticks = TickArchive(Path(os.environ.get("LEDGERQUANT_ARCHIVE", "data/archive")))


def load(d, name):
    p = d / name
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


def latest_run(pattern):
    found = sorted(RUNS.glob(pattern))
    return found[-1] if found else None


def summarise(d):
    dec, tr = load(d, "decisions.jsonl"), load(d, "trades.jsonl")
    called = [x for x in dec if "cost_usd" in x]
    valid = [x for x in dec if x["status"] == "VALID"]
    by_id = {x["decision_id"]: x for x in dec if "context" in x}
    aligned = [momentum_direction(by_id[t["decision_id"]]["context"]) == t["direction"] for t in tr if t["decision_id"] in by_id]
    hold_h = [(datetime.fromisoformat(t["closed_at_utc"]) - datetime.fromisoformat(t["opened_at_utc"])).total_seconds() / 3600 for t in tr]
    return {
        "calls": len(called), "cost": sum(D(x["cost_usd"]) for x in called),
        "status": Counter(x["status"] for x in dec), "actions": Counter(x["analysis"]["action"] for x in valid),
        "wait_kinds": Counter(x["analysis"]["wait"]["kind"] for x in valid if x["analysis"].get("wait")),
        "truncated": sum(1 for x in dec if x.get("truncated_text_fields")),
        "trades": len(tr), "long": sum(t["direction"] == "LONG" for t in tr),
        "net": sum((D(t["r"]) for t in tr), D(0)), "gross": sum((D(t["r_gross"]) for t in tr), D(0)),
        "static": sum((D(t["static"]["r"]) for t in tr), D(0)), "mirror": sum((D(t["mirrored"]["r"]) for t in tr), D(0)),
        "wins": sum(D(t["r"]) > 0 for t in tr), "exits": Counter(t["exit_reason"] for t in tr),
        "styles": Counter(t["style"] for t in tr), "aligned": f"{sum(aligned)}/{len(aligned)}",
        "hold_median_h": round(statistics.median(hold_h), 1) if hold_h else None,
        "by_symbol": {s: sum((D(t["r"]) for t in tr if t["symbol"] == s), D(0)) for s in ("EURUSD", "GBPUSD", "XAUUSD")},
    }


def cost_of_waiting(d):
    dec, tr = load(d, "decisions.jsonl"), load(d, "trades.jsonl")
    setups = {x["decision_id"]: x["analysis"]["setup"] for x in dec if x.get("status") == "VALID" and (x.get("analysis") or {}).get("setup")}
    geo = geometry(tr, setups)
    out = defaultdict(list)
    chains, chain = [], 0
    reasons = []
    for x in dec:
        a = x.get("analysis")
        if not a or x["status"] != "VALID" or x["context"].get("position"):
            continue
        if a["action"] == "WAIT":
            reasons.append((x["symbol"], x["decision_at_utc"][5:16], a["wait"]["kind"], a["wait"]["waiting_for"][:90]))
        if a["action"] not in ("WAIT", "NO_SIGNAL"):
            continue
        v = a["views"]
        stance = {v["news"]["stance"], v["chart"]["stance"]}
        if stance == {"BULLISH"}:
            direction = "LONG"
        elif stance == {"BEARISH"}:
            direction = "SHORT"
        elif "BULLISH" in stance and "BEARISH" not in stance and "NO_VIEW" not in stance - {"NEUTRAL"}:
            direction = "LONG" if v["chart"]["stance"] == "BULLISH" else None
        elif "BEARISH" in stance and "BULLISH" not in stance:
            direction = "SHORT" if v["chart"]["stance"] == "BEARISH" else None
        else:
            direction = None
        if direction is None:
            out["no_direction"].append(0)
            continue
        at = datetime.fromisoformat(x["decision_at_utc"])
        q = x["context"]["market"]["latest"]
        sign = 1 if direction == "LONG" else -1
        entry = D(q["ask"] if sign > 0 else q["bid"])
        g = geo[x["symbol"]]
        risk = entry * g["risk_share"]
        o = static_outcome(ticks, x["symbol"], direction, at, entry, entry - sign * risk, entry + sign * risk * g["reward_risk"],
                           weekend_close(at), "WEEKEND_CLOSE")
        if o:
            r = D(net_of_swap(o, x["symbol"], policy_rates(x["context"].get("macro") or {}))["r"])
            out[a["action"] + ":" + direction].append(r)
            out[a["action"]].append(r)
    return out, reasons


weeks = sys.argv[1:] or ["20251013", "20251208", "20260309"]
rows = {}
for w in weeks:
    for name, pat in (("claude", f"*claude-opus-4-6_{w}"), ("gpt", f"*analyst4_gpt-5.4-mini_{w}")):
        d = latest_run(pat)
        if d:
            rows[(w, name)] = summarise(d)

print("week     | model  | calls  cost | trades L/S wins | net R   gross  static  mirror | R/trade | styles | exits | mom | hold h | trunc | WAIT kinds")
for (w, name), s in rows.items():
    rt = (s["net"] / s["trades"]) if s["trades"] else D(0)
    print(f"{w} | {name:6s} | {s['calls']:3d} {s['cost']:6.2f} | {s['trades']:3d} {s['long']:2d}/{s['trades']-s['long']:<2d} {s['wins']:2d}  | "
          f"{s['net']:+6.2f} {s['gross']:+6.2f} {s['static']:+6.2f} {s['mirror']:+6.2f} | {rt:+.2f} | {dict(s['styles'])} | {dict(s['exits'])} | "
          f"{s['aligned']} | {s['hold_median_h']} | {s['truncated']} | {dict(s['wait_kinds'])}")
print()
for (w, name), s in rows.items():
    print(f"{w} {name:6s} actions {dict(s['actions'])} by symbol {{{', '.join(f'{k}: {v:+.2f}' for k, v in s['by_symbol'].items())}}}")

print("\n== What acting on Claude's own stated direction at WAIT / NO_SIGNAL would have earned (net R, own geometry) ==")
for w in weeks:
    d = latest_run(f"*claude-opus-4-6_{w}")
    if not d:
        continue
    out, reasons = cost_of_waiting(d)
    parts = []
    for k in sorted(out):
        if k == "no_direction":
            continue
        v = out[k]
        parts.append(f"{k}: n={len(v)} sum {sum(v):+.1f} mean {sum(v)/len(v):+.2f}")
    print(f"{w}: no agreed direction at {len(out['no_direction'])} times | " + " | ".join(parts))
    print("   WAIT reasons (symbol, time, kind, waiting_for):")
    seen = set()
    for sym, t, kind, text in reasons:
        key = (sym, text[:40])
        if key in seen:
            continue
        seen.add(key)
        print(f"     {sym} {t} {kind:12s} {text}")

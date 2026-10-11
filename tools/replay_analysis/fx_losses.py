"""Why FX trades lose: direction, noise stops, chasing, news. No model calls; ticks and recorded contexts only.

Every entry (v3 and v4) is held under the same rules: initial stop and target, closed at the weekly close.
Moves are measured on the mid price in units of the entry's initial risk, signed in the trade direction.
"""
import os
import json
import sys
from datetime import datetime, timedelta
from decimal import Decimal as D
from pathlib import Path

from ledgerquant.replay.costs import weekend_close
from ledgerquant.replay.market import TickArchive, _naive_utc
from ledgerquant.replay.positions import static_outcome

RUNS = Path(os.environ.get("LEDGERQUANT_RUNS", "data/replay_runs"))
ticks = TickArchive(Path(os.environ.get("LEDGERQUANT_ARCHIVE", "data/archive")))


def mid(symbol, at):
    q = ticks.latest(symbol, at)
    return (D(q["bid"]) + D(q["ask"])) / 2 if q else None


def extremes(symbol, start, end):
    """Highest and lowest mid between start and end."""
    src = ticks._ticks(symbol, _naive_utc(start), _naive_utc(end))
    hi, lo = ticks.con.execute(f"SELECT max((bid+ask)/2), min((bid+ask)/2) FROM {src}").fetchone()
    return (D(str(hi)), D(str(lo))) if hi is not None else (None, None)


def first_touch(symbol, direction, start, end, level, kind):
    """First time the exit-side price reaches `level` (kind TARGET or STOP) between start and end."""
    side = "bid" if direction == "LONG" else "ask"
    up = (direction == "LONG") == (kind == "TARGET")
    cond = f"{side} >= {level}" if up else f"{side} <= {level}"
    src = ticks._ticks(symbol, _naive_utc(start), _naive_utc(end))
    row = ticks.con.execute(f"SELECT min(event_time_utc) FROM {src} WHERE {cond}").fetchone()
    return row[0]


rows = []
for d in sorted(RUNS.glob("2026*/")):
    run = json.loads((d / "run.json").read_text())
    if len(run["plan"]["hours_utc"]) != 14:
        continue
    v, week = run["variant"]["contract"][-1], run["plan"]["start"]
    decisions = {x["decision_id"]: x for x in map(json.loads, (d / "decisions.jsonl").read_text().splitlines())
                 if "analysis" in x}
    tp = d / "trades.jsonl"
    for t in map(json.loads, tp.read_text().splitlines() if tp.exists() else []):
        dec = decisions[t["decision_id"]]
        a, ctx = dec["analysis"], dec["context"]
        setup = a["setup"]
        sym, direction = t["symbol"], t["direction"]
        sign = 1 if direction == "LONG" else -1
        opened = datetime.fromisoformat(t["opened_at_utc"])
        close_by = weekend_close(opened)
        entry, stop, target = D(t["entry"]), D(t["initial_stop"]), D(setup["target"])
        risk = abs(entry - stop)
        m0 = mid(sym, opened)

        held = static_outcome(ticks, sym, direction, opened, entry, stop, target, close_by, "WEEKEND_CLOSE")
        held_end = datetime.fromisoformat(held["closed_at_utc"])
        # Opposite direction, same distances, entered on the other side of the quote.
        q = ctx["market"]["latest"]
        m_entry = D(q["bid"] if direction == "LONG" else q["ask"])
        m_stop, m_target = m_entry + sign * risk, m_entry - sign * abs(target - entry)
        mirror = static_outcome(ticks, sym, "SHORT" if direction == "LONG" else "LONG", opened, m_entry, m_stop,
                                m_target, close_by, "WEEKEND_CLOSE")

        def move(hours):
            at = min(opened + timedelta(hours=hours), close_by)
            m = mid(sym, at)
            return float(sign * (m - m0) / risk) if m is not None else None

        hi, lo = extremes(sym, opened, held_end)
        mfe = float((hi - m0) / risk if sign > 0 else (m0 - lo) / risk) if hi is not None else None
        mae = float((m0 - lo) / risk if sign > 0 else (hi - m0) / risk) if hi is not None else None

        stopped_then_target = None
        if held["exit_reason"] == "STOP":
            stopped_then_target = first_touch(sym, direction, held_end, close_by, target, "TARGET") is not None

        h1 = ctx["market"]["bars"].get("H1") or []
        d1 = [b for b in ctx["market"]["bars"].get("D1") or [] if b.get("complete", True)]
        atr_h1 = sum(D(b["high"]) - D(b["low"]) for b in h1) / len(h1) if h1 else None
        atr_d1 = sum(D(b["high"]) - D(b["low"]) for b in d1) / len(d1) if d1 else None

        def pre(n):  # move over the last n hourly closes before entry, in the trade direction, in risk units
            if len(h1) <= n:
                return None
            return float(sign * (D(h1[-1]["close"]) - D(h1[-1 - n]["open"] if n == 0 else h1[-1 - n]["close"])) / risk)

        news_cites = [c for c in setup["citations"] if c.startswith("news:")]
        headlines = {h["id"]: h for h in (ctx.get("news") or {}).get("headlines", [])}
        ages = [(opened - datetime.fromisoformat(headlines[c]["published_utc"])).total_seconds() / 3600
                for c in news_cites if c in headlines]
        views = a["views"]
        want = "BULLISH" if direction == "LONG" else "BEARISH"
        rows.append({
            "v": v, "week": week, "symbol": sym, "fx": sym != "XAUUSD", "dir": direction, "at": t["opened_at_utc"],
            "hour": opened.hour, "weekday": opened.weekday(), "style": setup.get("style"),
            "horizon_h": setup.get("expected_horizon_hours") or (setup.get("max_holding_minutes", 0) / 60),
            "held_r": float(D(held["r"])), "held_exit": held["exit_reason"],
            "held_hours": (held_end - opened).total_seconds() / 3600,
            "mirror_r": float(D(mirror["r"])) if mirror else None,
            "mfe": mfe, "mae": mae, "stopped_then_target": stopped_then_target,
            "move_1h": move(1), "move_4h": move(4), "move_8h": move(8), "move_24h": move(24), "move_wk": move(200),
            "rr": float(abs(target - entry) / risk),
            "stop_atr_h1": float(risk / atr_h1) if atr_h1 else None,
            "stop_atr_d1": float(risk / atr_d1) if atr_d1 else None,
            "spread_r": float((D(q["ask"]) - D(q["bid"])) / risk),
            "pre_4h": pre(4), "pre_12h": pre(12), "pre_23h": pre(23),
            "news_cites": len(news_cites), "news_age_h_min": min(ages) if ages else None,
            "news_stance": views["news"]["stance"], "chart_stance": views["chart"]["stance"],
            "news_agrees": views["news"]["stance"] == want, "chart_agrees": views["chart"]["stance"] == want,
            "thesis": setup["thesis"][:300],
        })
    print(d.name, len(rows), file=sys.stderr)

Path(sys.argv[1]).write_text(json.dumps(rows, indent=0))

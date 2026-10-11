"""Rules that cost nothing to run, measured at the same decision times as the agent.

At every decision time the agent saw a ready market, each rule enters at market
with the agent's own geometry for that symbol (median risk as a share of price and
median reward/risk from the run's trades, or a declared default when the run has
fewer than MIN_TRADES on the symbol). Entries are independent and may overlap, are
held to stop, target or the run's close limit, and are netted of swap and
commission like the agent's trades. A rule the agent does not beat adds nothing.

- always_long, always_short: one direction every time.
- momentum_23h: the direction of the last 23 hourly closes (the move the agent's
  context shows), the rule the analyst most resembled in the first replays.
"""

import statistics
from datetime import datetime, timedelta
from decimal import Decimal

from ledgerquant.replay.costs import policy_rates, weekend_close
from ledgerquant.replay.market import TickArchive
from ledgerquant.replay.positions import static_outcome

MIN_TRADES = 5
DEFAULT_GEOMETRY = {"risk_share": {"EURUSD": Decimal("0.0024"), "GBPUSD": Decimal("0.0025"),
                                   "XAUUSD": Decimal("0.0055")},
                    "reward_risk": Decimal("1.5")}
OPEN_ENDED = timedelta(days=30)
RULES = ("always_long", "always_short", "momentum_23h")


def momentum_direction(context: dict) -> str | None:
    """LONG or SHORT by the last H1 close against the close 23 bars earlier; None when bars are missing or flat."""
    h1 = ((context.get("market") or {}).get("bars") or {}).get("H1") or []
    if len(h1) < 24:
        return None
    change = Decimal(h1[-1]["close"]) - Decimal(h1[-24]["close"])
    return "LONG" if change > 0 else "SHORT" if change < 0 else None


def geometry(trades: list[dict], setups: dict[str, dict]) -> dict[str, dict]:
    """Median risk share and reward/risk per symbol from the agent's trades."""
    result = {}
    for symbol, default_share in DEFAULT_GEOMETRY["risk_share"].items():
        own = [t for t in trades if t["symbol"] == symbol and t["decision_id"] in setups]
        if len(own) >= MIN_TRADES:
            shares = [abs(Decimal(t["entry"]) - Decimal(t["initial_stop"])) / Decimal(t["entry"]) for t in own]
            ratios = [abs(Decimal(setups[t["decision_id"]]["target"]) - Decimal(t["entry"]))
                      / abs(Decimal(t["entry"]) - Decimal(t["initial_stop"])) for t in own]
            result[symbol] = {"risk_share": statistics.median(shares), "reward_risk": statistics.median(ratios),
                              "source": f"median of {len(own)} agent trades"}
        else:
            result[symbol] = {"risk_share": default_share, "reward_risk": DEFAULT_GEOMETRY["reward_risk"],
                              "source": "declared default"}
    return result


def evaluate(decisions: list[dict], trades: list[dict], archive_root, close_before_weekend: bool) -> dict:
    from ledgerquant.replay.run import net_of_swap  # run imports the agent stack; keep this module light

    ticks = TickArchive(archive_root)
    seen, contexts = set(), []
    for d in decisions:
        if "context" in d and d["decision_id"] not in seen and (d["context"].get("market") or {}).get("latest"):
            seen.add(d["decision_id"])
            contexts.append(d)
    setups = {d["decision_id"]: d["analysis"]["setup"] for d in decisions
              if d.get("status") == "VALID" and (d.get("analysis") or {}).get("setup")}
    geo = geometry(trades, setups)
    totals = {rule: [] for rule in RULES}
    for d in contexts:
        context, symbol = d["context"], d["symbol"]
        if symbol not in geo:
            continue
        at = datetime.fromisoformat(d["decision_at_utc"])
        close_by = weekend_close(at) if close_before_weekend else at + OPEN_ENDED
        quote, rates = context["market"]["latest"], policy_rates(context.get("macro") or {})
        momentum = momentum_direction(context)
        for rule, direction in (("always_long", "LONG"), ("always_short", "SHORT"), ("momentum_23h", momentum)):
            if direction is None:
                continue
            sign = 1 if direction == "LONG" else -1
            entry = Decimal(quote["ask"] if sign > 0 else quote["bid"])
            risk = entry * geo[symbol]["risk_share"]
            outcome = static_outcome(ticks, symbol, direction, at, entry, entry - sign * risk,
                                     entry + sign * risk * geo[symbol]["reward_risk"], close_by,
                                     "WEEKEND_CLOSE" if close_before_weekend else "OPEN_ENDED")
            if outcome:
                totals[rule].append(Decimal(net_of_swap(outcome, symbol, rates)["r"]))

    by_id = {d["decision_id"]: d for d in contexts}
    aligned = [momentum_direction(by_id[t["decision_id"]]["context"]) == t["direction"]
               for t in trades if t["decision_id"] in by_id]
    # Older runs recorded gross R only; net them the same way so the comparison is like for like.
    agent = [Decimal(t["r"] if "r_gross" in t else net_of_swap(t, t["symbol"], policy_rates(
        (by_id.get(t["decision_id"], {}).get("context") or {}).get("macro") or {}))["r"]) for t in trades]
    summary = {rule: {"entries": len(values), "total_r": str(sum(values, Decimal(0)).quantize(Decimal("0.01"))),
                      "mean_r": str((sum(values, Decimal(0)) / len(values)).quantize(Decimal("0.001"))) if values else None}
               for rule, values in totals.items()}
    summary["agent"] = {"entries": len(agent), "total_r": str(sum(agent, Decimal(0)).quantize(Decimal("0.01"))),
                        "mean_r": str((sum(agent, Decimal(0)) / len(agent)).quantize(Decimal("0.001"))) if agent else None}
    return {"rules": summary,
            "agent_entries_with_23h_momentum": f"{sum(aligned)}/{len(aligned)}",
            "geometry": {s: {k: str(v) if isinstance(v, Decimal) else v for k, v in g.items()} for s, g in geo.items()},
            "basis": "net R per entry; rules enter at every ready decision time, overlapping, held to stop, target "
                     "or the run's close limit"}

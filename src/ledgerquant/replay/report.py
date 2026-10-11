"""Summarise one replay run: decisions, costs and trades in R against simple comparisons.

Comparisons per trade: the agent's managed result; the same entry and levels held
without any review (static exit); and the opposite direction with the same stop
and target distances (mirrored). The mean of static and mirrored is what a random
direction with the agent's own levels would have earned. Always NO_SIGNAL earns 0R.
"""

import argparse
import json
import statistics
from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path


def _read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def summarise(run_dir: Path) -> dict:
    run = json.loads((run_dir / "run.json").read_text())
    decisions, trades = _read(run_dir / "decisions.jsonl"), _read(run_dir / "trades.jsonl")
    called = [d for d in decisions if "provider_status" in d]
    valid = [d for d in decisions if d["status"] == "VALID"]
    latencies = sorted(d["latency_seconds"] for d in called)
    cost = sum(Decimal(d["cost_usd"]) for d in called)

    def r_sum(key):
        values = [Decimal(t[key]["r"] if key else t["r"]) for t in trades if (t.get(key) if key else True)]
        return values

    managed, static, mirror = r_sum(None), r_sum("static"), r_sum("mirrored")
    random_direction = [(s + m) / 2 for s, m in zip(static, mirror)]
    hold_minutes = [(datetime.fromisoformat(t["closed_at_utc"]) - datetime.fromisoformat(t["opened_at_utc"]))
                    .total_seconds() / 60 for t in trades]
    return {
        "run_id": run["run_id"], "kind": run["kind"], "pipeline": run["variant"]["pipeline"],
        "plan": run["plan"],
        "decisions": {
            "total": len(decisions), "model_calls": len(called),
            "by_status": dict(Counter(d["status"] for d in decisions)),
            "valid_by_action": dict(Counter(d["analysis"]["action"] for d in valid)),
            "wait_kinds": dict(Counter(d["analysis"]["wait"]["kind"] for d in valid if d["analysis"].get("wait"))),
            "decisions_with_unknown_citations": sum(1 for d in called if d.get("unknown_citations")),
        },
        "cost": {"usd": str(cost.quantize(Decimal("0.0001"))),
                 "usd_per_call": str((cost / len(called)).quantize(Decimal("0.0001"))) if called else None,
                 "input_tokens": sum(d.get("input_tokens") or 0 for d in called),
                 "output_tokens": sum(d.get("output_tokens") or 0 for d in called),
                 "latency_median_s": statistics.median(latencies) if latencies else None,
                 "latency_max_s": latencies[-1] if latencies else None},
        "trades": {
            "count": len(trades),
            "by_symbol": dict(Counter(t["symbol"] for t in trades)),
            "by_direction": dict(Counter(t["direction"] for t in trades)),
            "exit_reasons": dict(Counter(t["exit_reason"] for t in trades)),
            "wins": sum(1 for r in managed if r > 0),
            "total_r": {"agent_managed": str(sum(managed, Decimal(0))), "static_exit": str(sum(static, Decimal(0))),
                        "mirrored_direction": str(sum(mirror, Decimal(0))),
                        "random_direction": str(sum(random_direction, Decimal(0)).quantize(Decimal("0.0001"))),
                        "always_no_signal": "0"},
            "mean_r": str((sum(managed, Decimal(0)) / len(managed)).quantize(Decimal("0.0001"))) if managed else None,
            "holding_minutes_median": statistics.median(hold_minutes) if hold_minutes else None,
        },
    }


def markdown(summary: dict) -> str:
    d, c, t = summary["decisions"], summary["cost"], summary["trades"]
    lines = [
        f"# Replay report: {summary['run_id']}", "",
        f"{summary['kind']}. Pipeline: {summary['pipeline']}.",
        f"Plan: {summary['plan']['start']} to {summary['plan']['end_exclusive']} (exclusive), "
        f"{', '.join(summary['plan']['symbols'])}, hours {summary['plan']['hours_utc']}, "
        f"labels {summary['plan']['labels']}.", "",
        "## Decisions", "",
        f"- {d['total']} decision times, {d['model_calls']} model calls",
        f"- Status: {d['by_status']}",
        f"- Valid actions: {d['valid_by_action']}",
        f"- WAIT kinds: {d['wait_kinds']}",
        f"- Decisions citing an ID not in the context: {d['decisions_with_unknown_citations']}", "",
        "## Cost", "",
        f"- {c['usd']} USD ({c['usd_per_call']} per call), {c['input_tokens']} input and "
        f"{c['output_tokens']} output tokens",
        f"- Latency: median {c['latency_median_s']} s, max {c['latency_max_s']} s", "",
        "## Trades (R)", "",
        f"- {t['count']} trades, {t['wins']} winners, mean {t['mean_r']} R, median holding "
        f"{t['holding_minutes_median']} minutes",
        f"- By symbol {t['by_symbol']}, by direction {t['by_direction']}",
        f"- Exit reasons: {t['exit_reasons']}", "",
        "| Comparison | Total R |", "| --- | ---: |",
        *[f"| {name.replace('_', ' ')} | {value} |" for name, value in t["total_r"].items()], "",
        "A small sample shows whether the pipeline works and what the agent does; it is not evidence of an edge.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarise a replay run")
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    summary = summarise(args.run_dir)
    (args.run_dir / "report.json").write_text(json.dumps(summary, indent=1))
    (args.run_dir / "REPORT.md").write_text(markdown(summary))
    print(markdown(summary))


if __name__ == "__main__":
    main()

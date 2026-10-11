import json
from datetime import datetime, timezone
from decimal import Decimal

import duckdb

from ledgerquant.models.generation import Generation, ModelProfile, ToolCall
from ledgerquant.replay.archive import build_symbol
from ledgerquant.replay.run import Budget, Journal, run_symbol
from ledgerquant.replay.snapshot import SNAPSHOT_VERSION
from tests.unit.test_replay_market import export

UTC = timezone.utc
VIEWS = {k: {"stance": "NO_VIEW", "key_points": [], "citations": []} for k in ("news", "sentiment", "chart")}


def empty_snapshot(root):
    target = root / SNAPSHOT_VERSION
    target.mkdir(parents=True)
    con = duckdb.connect()
    con.execute(f"""COPY (SELECT * FROM (VALUES ('gdelt_gkg','x','u','t',NULL,TIMESTAMP '2020-01-01',TIMESTAMP '2020-01-01',
        NULL::TIMESTAMP,true,'v','{{}}')) t(source,source_item_id,url,title,summary,published_at,first_seen_at,
        available_at,backfilled,filter_version,details)) TO '{target}/news_items.parquet' (FORMAT parquet)""")
    con.execute(f"""COPY (SELECT 'CPIAUCSL' series_id, DATE '2020-01-01' observation_date, DATE '2020-01-01' realtime_start,
        '1' AS "value", TIMESTAMP '2020-01-01' AS first_seen_at) TO '{target}/macro_observations.parquet' (FORMAT parquet)""")
    con.execute(f"""COPY (SELECT 10 release_id, 'CPI' release_name, DATE '2020-01-01' release_date,
        TIMESTAMP '2020-01-01' first_seen_at) TO '{target}/macro_release_dates.parquet' (FORMAT parquet)""")


class FakeProvider:
    def __init__(self, answers):
        self.answers, self.calls = answers, 0

    def user_message(self, text):
        return {"role": "user", "content": text}

    def prepare(self, instructions, conversation, tools):
        return {"input": conversation}

    def invoke(self, request):
        answer = self.answers[self.calls]
        self.calls += 1
        return Generation("COMPLETED", {"body": "{}"}, [], (ToolCall("c", "submit_analysis", json.dumps(answer)),),
                          1000, 200)


def profile():
    return ModelProfile(provider="openai", endpoint="https://api.openai.com/v1/responses", model="m",
                        max_output_tokens=256, max_request_bytes=200000, timeout_seconds=5, max_steps_per_agent=1,
                        input_usd_per_million=1, output_usd_per_million=1, max_run_usd=1, price_basis="t",
                        knowledge_exposure="t")


def setup_archive(tmp_path):
    ticks = [(datetime(2026, 3, 2, 9, 59, 59), "1.1000", "1.1001"), (datetime(2026, 3, 2, 10, 30), "1.1010", "1.1011"),
             (datetime(2026, 3, 2, 10, 59, 58), "1.1015", "1.1016"), (datetime(2026, 3, 2, 11, 59, 58), "1.1005", "1.1006")]
    export(tmp_path / "exports", "run_a", "2026-03-02", "2026-03-03", ticks)
    build_symbol(tmp_path / "exports", tmp_path / "archive", "EURUSD")
    empty_snapshot(tmp_path / "archive")
    return tmp_path / "archive"


def read(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_run_opens_closes_and_journals_with_comparisons(tmp_path):
    root = setup_archive(tmp_path)
    answers = [
        {"views": VIEWS, "action": "LONG", "setup": {
            "thesis": "momentum", "citations": ["bar:EURUSD:H1:2026-03-02T09:00:00+00:00"], "stop": "1.0990",
            "target": "1.1040", "max_holding_minutes": 240, "invalidation": "below 1.0990", "uncertainty": "thin data"}},
        {"views": VIEWS, "action": "CLOSE", "reason": "momentum faded"},
        {"views": VIEWS, "action": "NO_SIGNAL"},
    ]
    provider = FakeProvider(answers)
    journal = Journal(tmp_path / "run")
    times = [(datetime(2026, 3, 2, h, tzinfo=UTC), "DEVELOPMENT") for h in (10, 11, 12)]
    run_symbol("EURUSD", times, root, provider, Budget(1, profile()), journal)
    decisions = read(tmp_path / "run" / "decisions.jsonl")
    assert [d["status"] for d in decisions] == ["VALID", "VALID", "VALID"]
    assert decisions[1]["context"]["position"]["direction"] == "LONG"
    trade, = read(tmp_path / "run" / "trades.jsonl")
    # entry at the 10:00 ask 1.1001, closed by the agent at the 11:00 bid 1.1015; risk 0.0011
    assert trade["exit_reason"] == "AGENT_CLOSE" and trade["entry"] == "1.1001" and trade["exit"] == "1.1015"
    assert trade["r"] == "1.2727" and trade["label"] == "DEVELOPMENT"
    assert trade["static"]["exit_reason"] == "MAX_HOLDING_TIME" and trade["mirrored"]["direction"] == "SHORT"


def test_invalid_levels_open_nothing_and_budget_stops_the_run(tmp_path):
    root = setup_archive(tmp_path)
    bad = {"views": VIEWS, "action": "LONG", "setup": {
        "thesis": "x", "citations": ["bar:EURUSD:H1:2026-03-02T09:00:00+00:00"], "stop": "1.2000", "target": "1.3000",
        "max_holding_minutes": 60, "invalidation": "x", "uncertainty": "x"}}
    provider = FakeProvider([bad, bad])
    journal = Journal(tmp_path / "run")
    tight = Budget(0.0001, profile())  # below one worst-case call
    times = [(datetime(2026, 3, 2, 10, tzinfo=UTC), "DEVELOPMENT")]
    run_symbol("EURUSD", times, root, provider, tight, journal)
    assert [d["status"] for d in read(tmp_path / "run" / "decisions.jsonl")] == ["BUDGET_STOP"]
    assert provider.calls == 0
    journal2 = Journal(tmp_path / "run2")
    run_symbol("EURUSD", times, root, FakeProvider([bad]), Budget(1, profile()), journal2)
    assert [d["status"] for d in read(tmp_path / "run2" / "decisions.jsonl")] == ["INVALID_LEVELS"]
    assert not (tmp_path / "run2" / "trades.jsonl").exists()


def test_report_summarises_decisions_cost_and_comparisons(tmp_path):
    from ledgerquant.replay.report import markdown, summarise
    root = setup_archive(tmp_path)
    answers = [
        {"views": VIEWS, "action": "LONG", "setup": {
            "thesis": "m", "citations": ["bar:EURUSD:H1:2026-03-02T09:00:00+00:00"], "stop": "1.0990",
            "target": "1.1040", "max_holding_minutes": 240, "invalidation": "i", "uncertainty": "u"}},
        {"views": VIEWS, "action": "CLOSE"},
    ]
    journal = Journal(tmp_path / "run")
    (tmp_path / "run" / "run.json").write_text(json.dumps({
        "run_id": "r", "kind": "replay", "variant": {"pipeline": "single analyst"},
        "plan": {"start": "2026-03-02", "end_exclusive": "2026-03-03", "symbols": ["EURUSD"], "hours_utc": [10, 11],
                 "labels": ["DEVELOPMENT"]}}))
    times = [(datetime(2026, 3, 2, h, tzinfo=UTC), "DEVELOPMENT") for h in (10, 11)]
    run_symbol("EURUSD", times, root, FakeProvider(answers), Budget(1, profile()), journal)
    summary = summarise(tmp_path / "run")
    assert summary["decisions"]["valid_by_action"] == {"LONG": 1, "CLOSE": 1}
    assert summary["trades"]["count"] == 1 and summary["trades"]["total_r"]["agent_managed"] == "1.2727"
    assert summary["cost"]["usd"] == "0.0024"  # 2 calls x (1000 in + 200 out) at 1 USD per million
    assert "| agent managed | 1.2727 |" in markdown(summary)

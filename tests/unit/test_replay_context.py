import json
from datetime import date, datetime, timezone

import duckdb
import pytest

from ledgerquant.models.generation import ModelProfile
from ledgerquant.replay.context import NewsArchive
from ledgerquant.replay.schedule import PlanError, decision_times, label, plan
from ledgerquant.replay.snapshot import SNAPSHOT_VERSION

UTC = timezone.utc
T = datetime(2025, 11, 12, 14, 0, tzinfo=UTC)


@pytest.fixture
def news(tmp_path):
    root = tmp_path / SNAPSHOT_VERSION
    root.mkdir()
    con = duckdb.connect()
    con.execute("""CREATE TABLE items (source VARCHAR, source_item_id VARCHAR, url VARCHAR, title VARCHAR,
                   summary VARCHAR, published_at TIMESTAMP, first_seen_at TIMESTAMP, available_at TIMESTAMP,
                   backfilled BOOLEAN, filter_version VARCHAR, details VARCHAR)""")
    rows = [
        # backfilled GDELT: batch 13:45 is visible at 14:00 (15 minutes later), batch 13:50 is not
        ("gdelt_gkg", "1", "u1", "Gold prices rise on Fed rate cut hopes", None, "2025-11-12 13:45", "2026-10-10 22:00", None, True),
        ("gdelt_gkg", "2", "u2", "Gold prices slip after strong data", None, "2025-11-12 13:50", "2026-10-10 22:00", None, True),
        ("gdelt_gkg", "3", "u3", "Athlete wins gold medal", None, "2025-11-12 13:30", "2026-10-10 22:00", None, True),
        ("gdelt_gkg", "4", "u4", "Euro falls as ECB holds rates", None, "2025-11-12 13:00", "2026-10-10 22:00", None, True),
        # live central-bank item: visible only from its real available_at
        ("fed_press", "f1", "u5", "FOMC statement", "Rates held", "2025-11-12 12:00", "2025-11-12 12:05", "2025-11-12 12:05", False),
        ("fed_press", "f2", "u6", "Later statement", None, "2025-11-12 13:00", "2025-11-12 14:30", "2025-11-12 14:30", False),
    ]
    for r in rows:
        con.execute("INSERT INTO items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'v1', ?)",
                    [*r, json.dumps({"source_name": "example.com", "tone": "-1.5,2,3"})])
    con.execute(f"COPY items TO '{root}/news_items.parquet' (FORMAT parquet)")
    con.execute("""CREATE TABLE obs AS SELECT * FROM (VALUES
        ('CPIAUCSL', DATE '2025-09-01', DATE '2025-11-11', '324.4', TIMESTAMP '2026-10-10 22:00'),
        ('CPIAUCSL', DATE '2025-09-01', DATE '2025-11-12', '999.9', TIMESTAMP '2026-10-10 22:00'),
        ('CPIAUCSL', DATE '2025-10-01', DATE '2025-11-12', '888.8', TIMESTAMP '2026-10-10 22:00'))
        t(series_id, observation_date, realtime_start, value, first_seen_at)""")
    con.execute(f"COPY obs TO '{root}/macro_observations.parquet' (FORMAT parquet)")
    con.execute("""CREATE TABLE cal AS SELECT * FROM (VALUES
        (10, 'Consumer Price Index', DATE '2025-11-13', TIMESTAMP '2026-10-10 22:00'),
        (18, 'H.15 Selected Interest Rates', DATE '2025-11-13', TIMESTAMP '2026-10-10 22:00'),
        (50, 'Employment Situation', DATE '2025-12-30', TIMESTAMP '2026-10-10 22:00'))
        t(release_id, release_name, release_date, first_seen_at)""")
    con.execute(f"COPY cal TO '{root}/macro_release_dates.parquet' (FORMAT parquet)")
    return NewsArchive(tmp_path)


def test_news_follows_visibility_rules_and_instrument_patterns(news):
    gold = news.news("XAUUSD", T)
    assert [h["title"] for h in gold["headlines"]] == ["Gold prices rise on Fed rate cut hopes"]
    assert [s["title"] for s in gold["central_bank"]] == ["FOMC statement"]
    # EURUSD sees euro news and US dollar drivers such as the Fed, but not gold or sports.
    assert [h["title"] for h in news.news("EURUSD", T)["headlines"]] == [
        "Gold prices rise on Fed rate cut hopes", "Euro falls as ECB holds rates"]


def test_macro_vintage_is_visible_from_the_next_day_only(news):
    cpi = news.macro(T)["series"]["CPIAUCSL"]
    assert cpi == [{"date": "2025-09-01", "value": "324.4", "vintage": "2025-11-11"}]
    later = news.macro(datetime(2025, 11, 13, 9, tzinfo=UTC))["series"]["CPIAUCSL"]
    assert [o["value"] for o in later] == ["999.9", "888.8"]


def test_calendar_lists_scheduled_events_only(news):
    events = news.calendar(T)["events"]
    assert events == [{"release": "US CPI", "date": "2025-11-13", "when": "upcoming"}]


def profile(cutoff):
    return ModelProfile(provider="openai", endpoint="https://api.openai.com/v1/responses", model="m",
                        max_output_tokens=256, max_request_bytes=10000, timeout_seconds=5, max_steps_per_agent=1,
                        input_usd_per_million=1, output_usd_per_million=1, max_run_usd=1, price_basis="t",
                        knowledge_exposure="t", training_data_cutoff=cutoff)


def test_decision_times_are_hourly_on_weekdays():
    times = decision_times(date(2026, 3, 6), date(2026, 3, 10))  # Friday to Monday
    assert len(times) == 28 and {t.weekday() for t in times} == {0, 4}
    assert times[0] == datetime(2026, 3, 6, 7, tzinfo=UTC) and times[13].hour == 20


def test_labels_follow_the_latest_cutoff_and_holdout():
    assert label(datetime(2025, 8, 31, 12, tzinfo=UTC), date(2025, 8, 31)) == "CONTAMINATED"
    assert label(datetime(2025, 9, 1, 7, tzinfo=UTC), date(2025, 8, 31)) == "DEVELOPMENT"
    assert label(datetime(2026, 9, 1, 7, tzinfo=UTC), date(2025, 8, 31)) == "HOLDOUT"
    assert label(datetime(2026, 10, 9, 7, tzinfo=UTC), date(2025, 8, 31)) == "AFTER_HOLDOUT"


def test_plan_guards_holdout_contamination_and_missing_cutoffs():
    gpt, sonnet = profile(date(2025, 8, 31)), profile(date(2026, 6, 30))
    assert {name for _, name in plan(date(2025, 9, 1), date(2025, 9, 8), [gpt])} == {"DEVELOPMENT"}
    with pytest.raises(PlanError, match="training cutoff"):
        plan(date(2025, 9, 1), date(2025, 9, 8), [gpt, sonnet])  # Sonnet 5.5 makes September contaminated
    with pytest.raises(PlanError, match="holdout"):
        plan(date(2026, 8, 31), date(2026, 9, 3), [gpt])
    assert plan(date(2026, 8, 31), date(2026, 9, 3), [gpt], allow_holdout=True)[-1][1] == "HOLDOUT"
    with pytest.raises(PlanError, match="training_data_cutoff"):
        plan(date(2025, 9, 1), date(2025, 9, 8), [profile(None)])

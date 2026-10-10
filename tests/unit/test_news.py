import io
import zipfile
from datetime import datetime, timedelta, timezone

import httpx

from ledgerquant.news.collector import Collector, gkg_grid, gkg_url
from ledgerquant.news.sources import GDELT_FILTER_VERSION, parse_feed, parse_gkg

UTC = timezone.utc


def gkg_row(record_id, url, themes="", organizations="", title=""):
    row = [""] * 27
    row[0], row[1], row[3], row[4] = record_id, "20261009120000", "example.com", url
    row[7], row[13], row[15] = themes, organizations, "-1.5,2,3.5,5.5,20,0,300"
    row[26] = f"<PAGE_TITLE>{title}</PAGE_TITLE>"
    return "\t".join(row)


def gkg_zip(*rows):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("20261009120000.gkg.csv", "\n".join(rows))
    return buffer.getvalue()


def test_gkg_keeps_only_fx_and_gold_scope_with_filter_version():
    archive = gkg_zip(
        gkg_row("1", "https://a.example/fed", themes="ECON_INTEREST_RATES;TAX_X"),
        gkg_row("2", "https://a.example/boe", organizations="bank of england"),
        gkg_row("3", "https://a.example/gold", title="Gold hits record as dollar slides"),
        gkg_row("4", "https://a.example/sport", themes="SPORTS", title="Cup final tonight"),
        gkg_row("5", "not-a-url", themes="ECON_INFLATION"),
    )
    total, items = parse_gkg(archive)
    assert total == 5
    assert [i.source_item_id for i in items] == ["1", "2", "3"]
    assert items[0].details["matched_themes"] == ["ECON_INTEREST_RATES"]
    assert items[2].title.startswith("Gold")
    assert all(i.filter_version == GDELT_FILTER_VERSION for i in items)
    assert items[0].published_at == datetime(2026, 10, 9, 12, tzinfo=UTC)


RSS = b"""<rss version="2.0"><channel><title>Press</title>
<item><title>FOMC statement &amp; rates</title><link>https://www.federalreserve.gov/x.htm</link>
<guid>fed-1</guid><pubDate>Wed, 17 Sep 2025 18:00:00 GMT</pubDate><description>Rates held</description>
<category>Monetary Policy</category></item>
<item><title>No link</title></item>
</channel></rss>"""

ATOM = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>ECB decision</title>
<link href="https://www.ecb.europa.eu/a.html"/><id>ecb-1</id><updated>2025-09-11T12:15:00Z</updated>
<summary>Rates unchanged</summary></entry></feed>"""


def test_rss_and_atom_items_parse_with_times_and_skip_linkless():
    rss = parse_feed("fed_press", RSS)
    assert len(rss) == 1
    assert rss[0].title == "FOMC statement & rates"
    assert rss[0].source_item_id == "fed-1"
    assert rss[0].published_at == datetime(2025, 9, 17, 18, tzinfo=UTC)
    assert rss[0].details["categories"] == ["Monetary Policy"]
    atom = parse_feed("ecb_press", ATOM)
    assert atom[0].url == "https://www.ecb.europa.eu/a.html"
    assert atom[0].published_at == datetime(2025, 9, 11, 12, 15, tzinfo=UTC)


def test_gkg_grid_aligns_to_quarter_hours():
    start = datetime(2026, 10, 9, 12, 7, tzinfo=UTC)
    grid = gkg_grid(start, start + timedelta(minutes=40))
    assert grid == [datetime(2026, 10, 9, 12, 15, tzinfo=UTC), datetime(2026, 10, 9, 12, 30, tzinfo=UTC),
                    datetime(2026, 10, 9, 12, 45, tzinfo=UTC)]
    assert gkg_url(grid[0]).endswith("/20261009121500.gkg.csv.zip")


class FakeStore:
    def __init__(self):
        self.records, self.done = [], set()

    def fetched(self, url):
        return url in self.done

    def record(self, **kwargs):
        self.records.append(kwargs)
        if kwargs["http_status"] in (200, 404) and kwargs["error"] is None:
            self.done.add(kwargs["url"])
        return len(kwargs["parsed"])


def collector(handler):
    clock = iter(datetime(2026, 10, 9, 12, tzinfo=UTC) + timedelta(seconds=i) for i in range(1000))
    return Collector(FakeStore(), httpx.Client(transport=httpx.MockTransport(handler)), lambda: next(clock))


def test_missing_batches_are_recorded_and_not_refetched():
    calls = []
    def handler(request):
        calls.append(str(request.url))
        if request.url.path.endswith("lastupdate.txt"):
            return httpx.Response(200, text="1 x https://data.gdeltproject.org/gdeltv2/20261009120000.gkg.csv.zip")
        if "114500" in request.url.path:
            return httpx.Response(404)
        return httpx.Response(200, content=gkg_zip(gkg_row("9", "https://a.example/x", themes="ECON_INFLATION")))
    c = collector(handler)
    c.poll_gdelt(timedelta(minutes=15))
    statuses = {r["url"].rsplit("/", 1)[1]: r["http_status"] for r in c.store.records}
    assert statuses == {"20261009114500.gkg.csv.zip": 404, "20261009120000.gkg.csv.zip": 200}
    assert c.store.records[-1]["backfill"] is False and len(c.store.records[-1]["parsed"]) == 1
    before = len(calls)
    c.poll_gdelt(timedelta(minutes=15))
    assert len(calls) == before + 1  # only lastupdate.txt


def test_transport_and_parse_failures_are_recorded_as_errors():
    def handler(request):
        if "fed" in request.url.host:
            raise httpx.ConnectTimeout("down", request=request)
        return httpx.Response(200, content=b"<not-xml")
    c = collector(handler)
    c.poll_feeds()
    errors = {r["source"]: r["error"] for r in c.store.records}
    assert errors["fed_press"] == "ConnectTimeout"
    assert errors["ecb_press"].startswith("PARSE_ERROR")
    assert all(r["parsed"] == [] for r in c.store.records)


def test_fred_parsers_read_release_calendar_and_vintages():
    from datetime import date
    from ledgerquant.news.sources import parse_fred_observations, parse_fred_release, parse_fred_release_dates
    assert parse_fred_release(b'{"releases":[{"id":10,"name":"Consumer Price Index"}]}') == (10, "Consumer Price Index")
    dates = parse_fred_release_dates("Consumer Price Index",
                                     b'{"release_dates":[{"release_id":10,"date":"2026-10-14"}]}')
    assert dates[0].release_date == date(2026, 10, 14) and dates[0].release_name == "Consumer Price Index"
    vintages = parse_fred_observations("CPIAUCSL", b'{"observations":['
        b'{"realtime_start":"2025-09-01","realtime_end":"2026-02-12","date":"2025-06-01","value":"321.500"},'
        b'{"realtime_start":"2026-02-13","realtime_end":"9999-12-31","date":"2025-06-01","value":"321.435"}]}')
    assert [(v.realtime_start, v.value) for v in vintages] == [(date(2025, 9, 1), "321.500"),
                                                              (date(2026, 2, 13), "321.435")]
    import pytest
    with pytest.raises(ValueError):
        parse_fred_release(b'{"error_code":400,"error_message":"Bad Request"}')


def test_poll_fred_sends_key_but_never_records_it(monkeypatch):
    import ledgerquant.news.collector as collector_module
    monkeypatch.setattr(collector_module, "FRED_SERIES", ("CPIAUCSL", "CPILFESL"))
    seen = []
    def handler(request):
        seen.append(request.url)
        assert request.url.params["api_key"] == "secret-key"
        path = request.url.path
        assert request.url.params.get("series_id") or request.url.params.get("release_id")
        if path.endswith("series/release"):
            return httpx.Response(200, json={"releases": [{"id": 10, "name": "Consumer Price Index"}]})
        if path.endswith("release/dates"):
            return httpx.Response(200, json={"release_dates": [{"release_id": 10, "date": "2026-10-14"}]})
        return httpx.Response(200, json={"observations": [
            {"realtime_start": "2026-09-11", "realtime_end": "9999-12-31", "date": "2026-08-01", "value": "330.1"}]})
    c = collector(handler)
    c.poll_fred("secret-key")
    sources = [r["source"] for r in c.store.records]
    assert sources.count("fred_series_release") == 2
    assert sources.count("fred_release_dates") == 1  # both series share one release
    assert sources.count("fred_observations") == 2
    assert all("secret-key" not in r["url"] and r["error"] is None for r in c.store.records)
    assert len(seen) == 5

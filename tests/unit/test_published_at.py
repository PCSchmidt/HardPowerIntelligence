"""Source publication-date extraction (D129).

Each adapter stores its date under a different key and format (RSS pubDate, ISO, compact GDELT).
`extract_published_at` normalizes them to an aware datetime, and — per the operator directive —
returns None (never raises, never signals "drop") when there's no usable date.
"""
from datetime import timezone

from engine.brief.rag import _parse_published, extract_published_at


class TestParsePublished:
    def test_iso_date_only(self):
        dt = _parse_published("2026-01-15")
        assert (dt.year, dt.month, dt.day) == (2026, 1, 15)
        assert dt.tzinfo is not None  # naive input gets UTC

    def test_iso_datetime_z(self):
        dt = _parse_published("2026-07-01T12:00:00Z")
        assert (dt.year, dt.month, dt.day, dt.hour) == (2026, 7, 1, 12)

    def test_rfc822_rss_pubdate(self):
        dt = _parse_published("Mon, 28 Jun 2026 12:00:00 GMT")
        assert (dt.year, dt.month, dt.day) == (2026, 6, 28)

    def test_gdelt_compact(self):
        dt = _parse_published("20260628T120000Z")
        assert (dt.year, dt.month, dt.day) == (2026, 6, 28)

    def test_compact_date_only(self):
        assert _parse_published("20260628").day == 28

    def test_unparseable_returns_none(self):
        assert _parse_published("not a date") is None

    def test_empty_and_none(self):
        assert _parse_published("") is None
        assert _parse_published(None) is None


class TestExtractPublishedAt:
    def test_feeds_rss(self):
        dt = extract_published_at("feeds", {"published": "Mon, 28 Jun 2026 12:00:00 GMT"})
        assert dt.month == 6 and dt.day == 28

    def test_arxiv_iso(self):
        assert extract_published_at("arxiv", {"published": "2026-07-01T00:00:00Z"}).month == 7

    def test_usaspending_start_date(self):
        assert extract_published_at("usaspending", {"start_date": "2020-09-18"}).year == 2020

    def test_edgar_file_date(self):
        assert extract_published_at("edgar", {"file_date": "2026-06-30"}).day == 30

    def test_nrc_publication_date(self):
        assert extract_published_at("nrc", {"publication_date": "2026-06-29"}).day == 29

    def test_gdelt_seendate(self):
        assert extract_published_at("gdelt", {"seendate": "20260628T120000Z"}).day == 28

    def test_json_string_structured_data(self):
        dt = extract_published_at("feeds", '{"published": "2026-05-01"}')
        assert dt.month == 5

    def test_unknown_source_uses_fallback_keys(self):
        assert extract_published_at("mystery", {"date": "2026-03-03"}).month == 3

    def test_missing_date_returns_none_not_crash(self):
        assert extract_published_at("usaspending", {"recipient_name": "ACME"}) is None

    def test_non_dict_returns_none(self):
        assert extract_published_at("feeds", None) is None
        assert extract_published_at("feeds", "garbage-not-json") is None

    def test_unparseable_date_value_returns_none(self):
        assert extract_published_at("feeds", {"published": "sometime last week"}) is None

"""Reference entity set parsing (T3.1, D091) — pure, no network/DB."""
from engine.entity.reference import pad_cik, parse_company_tickers

_PAYLOAD = {
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "1": {"cik_str": 936468, "ticker": "LMT", "title": "Lockheed Martin Corp"},
    "2": {"cik_str": 1234, "ticker": "", "title": "No Ticker Co"},          # skipped: no ticker
    "3": {"cik_str": None, "ticker": "NOCIK", "title": "No CIK Inc"},       # skipped: no cik
    "4": {"cik_str": 936468, "ticker": "LMT", "title": "Lockheed Martin Corp"},  # duplicate
}


class TestParseCompanyTickers:
    def test_parses_and_pads_cik(self):
        by_ticker = {r.ticker: r for r in parse_company_tickers(_PAYLOAD)}
        assert by_ticker["AAPL"].cik == "0000320193"     # padded to 10 digits
        assert by_ticker["AAPL"].name == "Apple Inc."

    def test_normalizes_name_for_matching(self):
        lmt = next(r for r in parse_company_tickers(_PAYLOAD) if r.ticker == "LMT")
        assert lmt.name_normalized == "LOCKHEED MARTIN"  # corporate suffix stripped

    def test_skips_rows_without_ticker_or_cik(self):
        refs = parse_company_tickers(_PAYLOAD)
        assert "NOCIK" not in {r.ticker for r in refs}
        assert "No Ticker Co" not in {r.name for r in refs}
        assert all(r.ticker and r.cik for r in refs)

    def test_dedupes_on_ticker_cik(self):
        assert len([r for r in parse_company_tickers(_PAYLOAD) if r.ticker == "LMT"]) == 1

    def test_empty_payload(self):
        assert parse_company_tickers({}) == []
        assert parse_company_tickers(None) == []


class TestPadCik:
    def test_pads_to_ten(self):
        assert pad_cik(320193) == "0000320193"
        assert pad_cik("320193") == "0000320193"

    def test_already_padded(self):
        assert pad_cik("0000320193") == "0000320193"

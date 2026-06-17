"""Tests for EDGAR filing-body extraction (D078) — pure functions, no network."""
from engine.adapters.edgar_body import (
    FilingFacts,
    build_enriched_chunk,
    extract_facts,
    strip_html,
)


class TestStripHtml:
    def test_strips_tags_and_decodes_entities(self):
        html = "<p>Acme &amp; Co awarded <b>$5 million</b></p>"
        assert strip_html(html) == "Acme & Co awarded $5 million"

    def test_drops_script_and_style(self):
        html = "<style>.x{color:red}</style><p>Visible</p><script>evil()</script>"
        assert strip_html(html) == "Visible"

    def test_plain_text_passthrough(self):
        assert strip_html("just  plain   text") == "just plain text"

    def test_empty(self):
        assert strip_html("") == ""


class TestExtractFacts:
    def test_scaled_amounts_normalized_to_usd(self):
        f = extract_facts("contract worth $1.5 billion and a $500,000 option")
        assert 1_500_000_000.0 in f.amounts_usd
        assert 500_000.0 in f.amounts_usd

    def test_compact_scale_suffix(self):
        f = extract_facts("raised $3.2B in funding")
        assert f.max_amount_usd == 3_200_000_000.0

    def test_percentages_and_dates(self):
        f = extract_facts("margin of 12.5% announced on May 7, 2026")
        assert 12.5 in f.percentages
        assert "May 7, 2026" in f.dates

    def test_max_amount(self):
        f = extract_facts("$2 million here, $7 million there")
        assert f.max_amount_usd == 7_000_000.0

    def test_no_facts(self):
        f = extract_facts("a filing with no figures at all")
        assert f.amounts_usd == [] and f.max_amount_usd is None
        assert f.summary() == ""

    def test_summary_is_compact_and_citable(self):
        f = FilingFacts(amounts_usd=[5_000_000.0], percentages=[10.0], dates=["May 7, 2026"])
        s = f.summary()
        assert "$5M" in s and "10%" in s and "May 7, 2026" in s


class TestEnrichedChunk:
    def test_combines_metadata_summary_and_excerpt(self):
        meta = "SEC 8-K filing by Acme (ACME)."
        body = "x" * 500 + " The award is $5 million for grid-scale storage. " + "y" * 500
        facts = extract_facts(body)
        chunk = build_enriched_chunk(meta, body, facts, excerpt_chars=200)
        assert chunk.startswith(meta)
        assert "$5M" in chunk          # facts summary folded in
        assert "grid-scale storage" in chunk   # excerpt centred on the amount

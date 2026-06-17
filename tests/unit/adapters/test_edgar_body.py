"""Tests for EDGAR filing-body extraction (D078) — pure functions, no network."""
from engine.adapters.edgar_body import (
    FilingFacts,
    build_enriched_chunk,
    build_form_d_chunk,
    extract_facts,
    extract_form_d_facts,
    strip_html,
)

_FORM_D_XML = """<?xml version="1.0"?>
<edgarSubmission><offeringData><offeringSalesAmounts>
<totalOfferingAmount>5000000</totalOfferingAmount>
<totalAmountSold>2000000</totalAmountSold>
</offeringSalesAmounts>
<industryGroup><industryGroupType>Other Technology</industryGroupType></industryGroup>
</offeringData></edgarSubmission>"""


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


class TestFormD:
    def test_extracts_offering_sold_industry(self):
        fd = extract_form_d_facts(_FORM_D_XML)
        assert fd.total_offering_usd == 5_000_000.0
        assert fd.total_sold_usd == 2_000_000.0
        assert fd.industry == "Other Technology"
        assert fd.amount_usd == 5_000_000.0   # offering preferred for materiality

    def test_indefinite_offering_falls_back_to_sold(self):
        xml = ("<totalOfferingAmount>Indefinite</totalOfferingAmount>"
               "<totalAmountSold>750000</totalAmountSold>")
        fd = extract_form_d_facts(xml)
        assert fd.total_offering_usd is None
        assert fd.amount_usd == 750_000.0     # falls back to amount sold

    def test_empty_xml_is_all_none(self):
        fd = extract_form_d_facts("")
        assert fd.amount_usd is None and fd.industry is None

    def test_chunk_is_citable(self):
        fd = extract_form_d_facts(_FORM_D_XML)
        chunk = build_form_d_chunk("NuclearCo Inc", "NUKE", fd)
        assert chunk.startswith("SEC Form D private placement by NuclearCo Inc (NUKE):")
        assert "$5M" in chunk and "Other Technology" in chunk

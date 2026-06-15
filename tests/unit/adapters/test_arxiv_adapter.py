"""Tests for the arXiv adapter (D066). Fixture mirrors a real Atom feed — no network.

arXiv differs from the JSON sources: parse() takes an XML *string* (response_format
= "text"), records carry no amount_usd, and the content hash is over intrinsic
paper fields (not the probe theme) so cross-probe matches dedup to one row.
"""
import pytest
from engine.adapters.arxiv import ArxivAdapter

# Two entries: one multi-author with a v2 revision, one single-author. Titles and
# abstracts carry the hard line breaks arXiv really emits, to exercise _clean().
ATOM_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <opensearch:totalResults xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">2</opensearch:totalResults>
  <entry>
    <id>http://arxiv.org/abs/2406.01234v2</id>
    <updated>2026-06-12T10:00:00Z</updated>
    <published>2026-06-10T09:00:00Z</published>
    <title>Scaling Laws for
  Foundation Models</title>
    <summary>  We study how foundation model performance
scales with compute and data, deriving updated scaling laws.  </summary>
    <author><name>Ada Lovelace</name></author>
    <author><name>Alan Turing</name></author>
    <author><name>Grace Hopper</name></author>
    <author><name>John von Neumann</name></author>
    <arxiv:primary_category term="cs.LG"/>
    <category term="cs.LG"/>
    <category term="cs.AI"/>
    <link rel="alternate" type="text/html" href="http://arxiv.org/abs/2406.01234v2"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2406.05678v1</id>
    <updated>2026-06-11T10:00:00Z</updated>
    <published>2026-06-11T08:00:00Z</published>
    <title>Autonomous Swarm Control</title>
    <summary>A reinforcement learning approach to multi-agent autonomy.</summary>
    <author><name>Katherine Johnson</name></author>
    <arxiv:primary_category term="cs.RO"/>
    <category term="cs.RO"/>
  </entry>
</feed>"""


@pytest.fixture
def atom_feed() -> str:
    return ATOM_FEED


class TestParse:
    def test_record_count(self, atom_feed):
        assert len(ArxivAdapter().parse(atom_feed)) == 2

    def test_source_and_type(self, atom_feed):
        for r in ArxivAdapter().parse(atom_feed):
            assert r.source_id == "arxiv"
            assert r.record_type == "research_paper"

    def test_native_id_strips_version(self, atom_feed):
        # native_id is the stable paper identity; the version lives in structured_data.
        recs = ArxivAdapter().parse(atom_feed)
        assert recs[0].native_id == "2406.01234"
        assert recs[0].structured_data["version"] == "v2"

    def test_url_points_to_abs(self, atom_feed):
        assert ArxivAdapter().parse(atom_feed)[0].url == "https://arxiv.org/abs/2406.01234"

    def test_whitespace_collapsed_in_title_and_abstract(self, atom_feed):
        sd = ArxivAdapter().parse(atom_feed)[0].structured_data
        assert sd["title"] == "Scaling Laws for Foundation Models"
        assert "\n" not in sd["abstract"]
        assert sd["abstract"].startswith("We study how foundation model")

    def test_structured_data_categories(self, atom_feed):
        sd = ArxivAdapter().parse(atom_feed)[0].structured_data
        assert sd["primary_category"] == "cs.LG"
        assert sd["categories"] == ["cs.LG", "cs.AI"]
        assert sd["authors"][0] == "Ada Lovelace"

    def test_text_chunk_is_substantive(self, atom_feed):
        chunk = ArxivAdapter().parse(atom_feed)[0].text_chunk
        assert "Scaling Laws for Foundation Models" in chunk
        assert "Abstract:" in chunk
        assert "Ada Lovelace" in chunk
        assert "et al." in chunk          # >3 authors → truncated with et al.

    def test_lead_author_mention_is_person(self, atom_feed):
        m = ArxivAdapter().parse(atom_feed)[0].entity_mentions[0]
        assert m["mention"] == "Ada Lovelace"
        assert m["entity_type"] == "person"

    def test_no_amount_usd(self, atom_feed):
        # arXiv records have no dollar magnitude — they score on novelty + authority.
        assert "amount_usd" not in ArxivAdapter().parse(atom_feed)[0].structured_data

    def test_empty_feed(self):
        empty = ('<?xml version="1.0" encoding="UTF-8"?>'
                 '<feed xmlns="http://www.w3.org/2005/Atom"></feed>')
        assert ArxivAdapter().parse(empty) == []


class TestContentHash:
    def test_deterministic_and_hex(self, atom_feed):
        a = ArxivAdapter().parse(atom_feed)
        b = ArxivAdapter().parse(atom_feed)
        assert a[0].content_hash == b[0].content_hash
        assert len(a[0].content_hash) == 64

    def test_hash_excludes_probe_theme(self, atom_feed):
        # Same paper matched by two different probes must dedup → identical hash,
        # so the probe theme cannot be part of the hash basis.
        a = ArxivAdapter()
        a.build_request_payload(None, page=1)   # AI scaling probe
        b = ArxivAdapter()
        b.build_request_payload(None, page=3)   # autonomy probe (different theme)
        ra = a.parse(atom_feed)[0]
        rb = b.parse(atom_feed)[0]
        assert ra.structured_data["theme"] != rb.structured_data["theme"]
        assert ra.content_hash == rb.content_hash

    def test_new_version_changes_hash(self, atom_feed):
        original = ArxivAdapter().parse(atom_feed)[0]
        bumped = ArxivAdapter().parse(atom_feed.replace("2406.01234v2", "2406.01234v3"))[0]
        assert original.native_id == bumped.native_id   # same paper
        assert original.content_hash != bumped.content_hash  # but new version


class TestProbesAndDesks:
    def test_default_probe_is_ai(self, atom_feed):
        # Without build, parse uses the first probe (frontier AI → ai).
        assert set(ArxivAdapter().parse(atom_feed)[0].desk) == {"ai"}

    def test_autonomy_probe_is_defense_ai(self, atom_feed):
        adapter = ArxivAdapter()
        adapter.build_request_payload(None, page=3)   # autonomy & robotics
        assert set(adapter.parse(atom_feed)[0].desk) == {"defense", "ai"}

    def test_energy_probe_is_ai_energy(self, atom_feed):
        adapter = ArxivAdapter()
        adapter.build_request_payload(None, page=4)   # AI applied to energy
        assert set(adapter.parse(atom_feed)[0].desk) == {"ai", "energy"}

    def test_build_payload_shape_and_cycling(self):
        adapter = ArxivAdapter()
        p1 = adapter.build_request_payload(None, page=1)
        assert "large language model" in p1["search_query"]
        assert p1["sortBy"] == "submittedDate"
        assert p1["sortOrder"] == "descending"
        assert "submittedDate:[" in p1["search_query"]
        p3 = adapter.build_request_payload(None, page=3)
        assert "cs.RO" in p3["search_query"]

    def test_build_payload_uses_cursor_date(self):
        p = ArxivAdapter().build_request_payload({"last_date": "2026-06-01"}, page=1)
        assert "202606010000" in p["search_query"]

    def test_next_cursor_walks_probes_then_advances_date(self):
        adapter = ArxivAdapter()
        assert adapter.next_cursor("", current_page=1) == {"page": 2}
        terminal = adapter.next_cursor("", current_page=adapter.probe_count)
        assert "last_date" in terminal

    def test_response_format_is_text(self):
        assert ArxivAdapter().response_format == "text"

    def test_headers_include_user_agent(self):
        assert "User-Agent" in ArxivAdapter().headers

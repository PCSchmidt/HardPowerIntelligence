# Data Sources (wired)

**Auto-generated — do not edit by hand.** Regenerate with `uv run python scripts/dump_sources.py` whenever a source is added or removed; the source of truth is `engine/adapters/registry.py` + `engine/adapters/feeds.py`. For the *candidate* universe and phased roadmap (not the live list), see `SOURCE_LANDSCAPE.md`. Live per-feed health is a runtime signal (the `feed_yielded_zero` ingest log), not tracked here.

## Structured / API adapters

Each is one `source_id` with its own adapter.

| `source_id` | Tier | What it pulls |
|---|---|---|
| `usaspending` | Confirmed — primary public record (claims citation-supported) | USASpending.gov awards adapter — federal contract & grant awards (the federal-money leg). |
| `edgar` | Confirmed — primary public record (claims citation-supported) | SEC EDGAR full-text search adapter (D055 §10, D060). |
| `arxiv` | Confirmed — primary public record (claims citation-supported) | arXiv API adapter — the technology-advancement leg of a brief (D063, D066). |
| `nrc` | Confirmed — primary public record (claims citation-supported) | NRC adapter via the Federal Register API — the regulatory leg of the Energy desk (D095). |
| `gdelt` | Speculative — raw / un-vetted signal | GDELT-as-story adapter — worldwide news radar across all three desks (D101). |
| `feeds` | Reported — attributed named third-party | Generic RSS/Atom feed adapter — the scale lever for breadth (D104). |
| `sam_gov` | Confirmed — primary public record (claims citation-supported) | SAM.gov contract-opportunities adapter (D105) — Phase 2 structured federal veins. |

## Feed outlets — `source_id="feeds"` (38 total)

One generic RSS/Atom adapter drives a registry of named outlets. Tier: Reported — attributed named third-party. Each carries a single home desk (D097).

### Defense (11)

- **Breaking Defense** — <https://breakingdefense.com/feed/>
- **DefenseScoop** — <https://defensescoop.com/feed/>
- **Defense One** — <https://www.defenseone.com/rss/all/>
- **The War Zone** — <https://www.twz.com/feed>
- **Naval News** — <https://www.navalnews.com/feed/>
- **SpaceNews** — <https://spacenews.com/feed/>
- **CSIS** — <https://www.csis.org/rss.xml>
- **War on the Rocks** — <https://warontherocks.com/feed/>
- **Defense News** — <https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml>
- **C4ISRNET** — <https://www.c4isrnet.com/arc/outboundfeeds/rss/?outputType=xml>
- **Atlantic Council** — <https://www.atlanticcouncil.org/feed/>

### AI (16)

- **Data Center Dynamics** — <https://www.datacenterdynamics.com/en/rss/>
- **IEEE Spectrum** — <https://spectrum.ieee.org/feeds/feed.rss>
- **HPCwire** — <https://www.hpcwire.com/feed/>
- **The Register** — <https://api.theregister.com/api/v1/article?orderBy=published&site_id=2&remapper=rss>
- **Tom's Hardware** — <https://www.tomshardware.com/feeds.xml>
- **SemiAnalysis** — <https://semianalysis.com/feed/>
- **CSET (Georgetown)** — <https://cset.georgetown.edu/feed/>
- **The Next Platform** — <https://www.nextplatform.com/feed/>
- **Import AI** — <https://importai.substack.com/feed>
- **SemiWiki** — <https://semiwiki.com/feed/>
- **TechCrunch AI** — <https://techcrunch.com/category/artificial-intelligence/feed/>
- **VentureBeat AI** — <https://venturebeat.com/category/ai/feed/>
- **MIT Technology Review AI** — <https://www.technologyreview.com/topic/artificial-intelligence/feed/>
- **Hugging Face** — <https://huggingface.co/blog/feed.xml>
- **OpenAI** — <https://openai.com/news/rss.xml>
- **The Gradient** — <https://thegradient.pub/rss/>

### Energy (11)

- **Utility Dive** — <https://www.utilitydive.com/feeds/news/>
- **World Nuclear News** — <https://www.world-nuclear-news.org/rss>
- **POWER Magazine** — <https://www.powermag.com/feed/>
- **pv magazine** — <https://www.pv-magazine.com/feed/>
- **RMI** — <https://rmi.org/feed/>
- **Energy Storage News** — <https://www.energy-storage.news/feed/>
- **Latitude Media** — <https://www.latitudemedia.com/feed>
- **Power Engineering** — <https://www.power-eng.com/feed/>
- **ESS News** — <https://www.ess-news.com/feed/>
- **Carbon Tracker** — <https://carbontracker.org/feed/>
- **Nuclear Newswire (ANS)** — <https://www.ans.org/news/feed/>

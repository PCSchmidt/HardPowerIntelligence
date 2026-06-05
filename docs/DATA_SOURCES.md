# Data Sources

The source map for Hard Power Intelligence. The strategic fact that shapes everything:
**the sources that make this product credible — government, regulatory, defense, and
energy data — are overwhelmingly free and public.** The expensive licensed data
(prices, estimates, transcripts) is the *commodity* layer, bought cheaply or deferred.
The moat (synthesis + provenance over free strategic data) and the low cost point the
same way.

Legend: **🟢 Free** · **🟡 Cheap (<$50/mo)** · **🔴 Paid/Enterprise**

---

## Source categories

### A. Reference / entity data — the spine 🟢
The free crosswalks that the entity graph hangs on: SEC `company_tickers.json`
(ticker↔CIK), OpenFIGI (ticker/CUSIP↔FIGI), GLEIF LEI (legal-entity parent/child),
SAM.gov / USAspending recipient hierarchy (UEI↔parent), sector-ETF holdings as a GICS
proxy.

### B. Market & pricing 🟢→🟡
Finnhub (free 60 calls/min), Alpha Vantage (free 25/day). **Best value: Financial
Modeling Prep ~$19/mo flat** — prices + 30yr fundamentals + ratios + transcripts.
Polygon.io for real-time depth only if ever needed.

### C. SEC / regulatory filings 🟢 — core moat
EDGAR full-text + submissions + company-facts APIs (free; requires a User-Agent).
10-K/10-Q/8-K, S-1/424B, DEF 14A, Form 4 (insiders), 13F (institutions), 13D/G
(activist stakes).

### D. Earnings 🟢→🟡
Calendars (Finnhub/FMP). Transcripts via FMP (bundled), earningscalls.dev, API Ninjas,
Quartr, or an Apify scraper (~$0.04/transcript). Estimates/guidance are licensed
(Benzinga/FMP/Zacks).

### E. Analyst & market-structure 🟢→🔴
Analyst ratings/price targets (Benzinga 🔴, FMP). Short interest (FINRA, free,
bi-monthly). Options/IV (ORATS/CBOE 🔴 — deferred).

### F. Macro / economic 🟢
FRED (master macro API), BLS (CPI/PPI/jobs), BEA (GDP), Treasury FiscalData, Census,
Fed (FOMC statements — scrape), World Bank / IMF.

### G. Government / Defense 🟢 — the richest free vein
USAspending API (all federal contract awards, no auth), SAM.gov (opportunities +
awards + entity registry), DoD daily contracts (>$7.5M, scrape), Congress.gov
(NDAA/appropriations), DSCA (Foreign Military Sales), GAO/CRS reports, DoD Comptroller
budget docs, **BIS Entity List / OFAC sanctions** (export-control catalysts — huge for
chips and defense).

### H. Energy 🟢→🔴
EIA Open Data API (free; enormous — electricity, nuclear & uranium prices/contracts,
oil, gas, capacity), NRC (reactor status, licensing, SMR applications), FERC
(interconnection, rate filings), ISO/RTO grid data (PJM/ERCOT/CAISO — load/queue =
data-center power-demand signal), EPA. Uranium spot price (UxC/TradeTech 🔴 — the one
notable energy paywall; EIA gives contract/lagged prices free).

### I. AI infrastructure 🟢→🔴 — hardest to source (no single API)
Hyperscaler capex extracted from MSFT/GOOGL/AMZN/META filings (free via EDGAR — the
demand engine), SIA/WSTS semiconductor sales, data-center supply (Data Center Dynamics;
CBRE/JLL 🔴), power interconnection queues (LBNL + ISO, free), USPTO PatentsView (free),
chip export controls (BIS), GPU supply/pricing news.

### J. News & trade press 🟢→🔴
GDELT (massive, free), Google News RSS, company IR RSS, sector trade press (Breaking
Defense, Defense News, Utility Dive, Data Center Dynamics, World Nuclear News),
financial news APIs (Benzinga 🔴, Marketaux 🟡, Finnhub 🟢).

### K. Smart money / political 🟢→🟡
Form 4 insiders (EDGAR), 13F institutions (EDGAR; WhaleWisdom/13F.info for clean
parsing), 13D/G activist, congressional trading (Capitol Trades / Quiver 🟡).

### L. Alternative data / proxies 🟢→🔴
Google Trends, USPTO patents, job-posting counts (free); Revelio/LinkUp (hiring),
Similarweb (web traffic), satellite/shipping, social sentiment (🔴 — deferred). Treat
all as proxies, not predictions.

### M. Geopolitical 🟢
GDELT, ACLED (conflict), sanctions/entity lists — feed the Defense and Energy-security
narratives.

---

## Tiered source stack

### Tier 0 — Free-first MVP (≈$0 data cost, ~80% of the deliverable)
EDGAR · USAspending · SAM.gov · DoD daily contracts · Congress.gov · EIA · NRC ·
FRED · BLS · BEA · Treasury · FINRA · USPTO PatentsView · GDELT · Google News + IR RSS
· Finnhub free · Google Trends. **Start here.**

### Tier 1 — One cheap upgrade (~$19–70/mo)
FMP (~$19) for clean prices + fundamentals + transcripts; optionally Quiver (~$10–50)
for congressional trades.

### Tier 2 — Revenue-funded adds
Benzinga (ratings/estimates), paid transcripts at scale, uranium spot, select
alt-data, CBRE/JLL data-center reports.

### Tier 3 — Avoid early (margin killers)
Bloomberg / AlphaSense / FactSet / Refinitiv terminals, real-time licensed feeds,
satellite, premium social-sentiment.

---

## Licensing & legal posture

Each adapter declares a **`license_class`** that routes how its data may be used:

| Class | Sources | Usage rule |
|-------|---------|-----------|
| `public_domain` | All government/regulatory data | Store, synthesize, redistribute; cite the agency |
| `licensed` | FMP, Benzinga, paid vendors | Synthesize + cite derived insight; **never republish raw feeds** |
| `scrape_gray` | Paywalled press | **Link + short quote only**; never copy full articles |

Operational rules: respect `robots.txt`, rate limits, and required headers (EDGAR
mandates a descriptive User-Agent); store links + short excerpts + synthesis, not full
copyrighted text. Government data being both free *and* freely redistributable is why
the free-first stack is also the safe stack.

---

## Build sequence

Launch **Defense first** — the richest free government data (USAspending / SAM / DoD /
Congress / DSCA / BIS) — then graft on Energy (EIA / NRC / FERC) and AI-Infrastructure
(capex / SIA / interconnection queues). Build the Tier-0 stack + the entity-resolution
spine before spending a dollar on data.

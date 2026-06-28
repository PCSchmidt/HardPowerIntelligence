# Source Landscape

The full universe of information sources for the Defense / AI / Energy desks — what is
**searched today**, what is **queued**, and the **complete map of what we are missing**,
organized by source *type* so coverage gaps are visible by category, not just by name.

This is the living counterpart to [`DATA_SOURCES.md`](DATA_SOURCES.md) (which catalogues a
narrower Tier-0 federal-data stack). It exists because the binding constraint on HPI today is
**coverage breadth**, not engineering — 5 adapters cannot give "a thorough picture of the
state of the domain." Treat this file as a **build backlog**: it is non-exhaustive and meant
to be extended as fronts move (operator directive, 2026-06-28).

## Framing (read first)

- **The moat is the entity graph + synthesis over a wide intake — not access to any one feed.**
  So the goal is wide, *graded* intake, not a curated few. The [epistemic flip](../DECISIONS.md)
  (D098/D099) is what makes categories C–G below newly *admissible*: they enter the brief carrying
  a confidence **label** (Reported / Speculative), no longer excluded for not being a primary record.
- **License class** routes usage (per `DATA_SOURCES.md`): `public_domain` (gov/regulatory — store,
  synthesize, redistribute), `licensed` (paid vendors — synthesize + cite, never republish raw),
  `scrape_gray` (third-party press — **title + link + short quote only**, never full text).
- **Confidence tier** (D098): `confirmed` (primary record, cited) · `reported` (named third-party
  reporting) · `analysis` (HPI inference) · `speculative` (early/weak signal).
- **The scaling unlock:** most of categories C–G are **RSS/Atom feeds**. The right build is **one
  configurable feed adapter** driven by a registry of `{url, desk, license_class, reliability_tier}`
  rows — onboarding 50+ sources with a single adapter — not one bespoke adapter per outlet.

Legend — **Status:** ✅ built · 🟡 queued (named, unbuilt) · ⬜ missing (not yet on any list).
**Priority:** P1 (next) · P2 · P3 (later).

---

## 1. Currently searched (5 adapters)

| Source | Type | Desks | License | Tier |
|---|---|---|---|---|
| USAspending | Federal contract awards | all | public_domain | confirmed |
| SEC EDGAR | SEC filings (full-text) | all | public_domain | confirmed |
| arXiv | Research preprints | ai, def∩ai | public_domain | confirmed |
| NRC (via Federal Register) | Nuclear regulatory | energy | public_domain | confirmed |
| GDELT | Worldwide news (D101) | all | scrape_gray | speculative |
| **Feeds** (RSS/Atom, ~21 outlets) | Trade press / think tanks / IR (D104) | all | scrape_gray | reported |

---

## 2. The full universe by source type

### A. Government — agencies, programs, regulators (public_domain · confirmed)

| Source | Desk | Status | Priority |
|---|---|---|---|
| SAM.gov (opportunities + awards + entity registry) | all | 🟡 | P1 |
| DoD daily contracts (>$7.5M announcements) | defense | 🟡 | P1 |
| Congress.gov (NDAA, appropriations, hearings, bills) | all | 🟡 | P1 |
| DSCA (Foreign Military Sales notifications) | defense | ⬜ | P2 |
| DARPA / DIU / SDA / MDA (solicitations, awards, news) | defense | ⬜ | P2 |
| Service labs — AFRL, ARL, ONR, NRL | defense | ⬜ | P3 |
| SBIR/STTR awards (DoD + DOE + others) | all | ⬜ | P2 |
| DoD Comptroller budget docs (R-docs / P-docs) | defense | ⬜ | P3 |
| GAO / CRS reports | all | ⬜ | P2 |
| FERC (orders, interconnection, rate filings) | energy | 🟡 | P1 |
| DOE — Loan Programs Office, ARPA-E, Grid Deployment | energy | ⬜ | P2 |
| National labs — INL, NREL, ORNL, PNNL, Sandia, LBNL (queue reports) | energy | ⬜ | P2 |
| ISO/RTO open data — PJM, ERCOT, CAISO, MISO, SPP, ISO-NE, NYISO | energy | ⬜ | P2 |
| NERC (reliability) / BOEM / BLM (leases) / state PUCs | energy | ⬜ | P3 |
| EIA Open Data (electricity, nuclear, oil/gas, capacity) | energy | 🟡 | P1 |
| BIS Entity List / OFAC sanctions (export-control catalysts) | ai, defense | ⬜ | P1 |
| NIST (AI standards, CHIPS Program Office) + CHIPS Act awards | ai | ⬜ | P2 |
| USPTO PatentsView (patents) | all | 🟡 | P2 |
| Regulations.gov (rulemaking dockets) · Federal Register (all agencies) | all | ⬜ | P3 |
| FRED / BLS / BEA / Treasury / FINRA (macro + market structure) | all | 🟡 | P2 |

### B. Quasi-governmental & international bodies (mixed · confirmed/reported)

| Source | Desk | License | Priority |
|---|---|---|---|
| SIPRI (arms transfers) · IISS (Military Balance) · NATO | defense | reported | P2 |
| IAEA (+ PRIS reactor DB) · IEA · World Nuclear Association · OECD-NEA · OPEC | energy | reported | P2 |
| OECD AI Observatory · Stanford HAI AI Index · Epoch AI (compute trends) | ai | reported | P1 |
| ENTSO-E (EU grid) · World Bank / IMF | energy/cross | public_domain | P3 |

### C. Think tanks & policy research (scrape_gray/reported) — **entirely absent today**

| Source | Desk | Priority |
|---|---|---|
| CSIS, RAND, CNAS, Hudson, CSBA, Mitchell Institute, ISW, Atlantic Council, War on the Rocks | defense | P2 |
| RMI, Breakthrough Institute, ClearPath, Nuclear Innovation Alliance, EPRI, Columbia Global Energy, Lazard (LCOE) | energy | P2 |
| CSET (Georgetown), Epoch AI, Stanford HAI, MITRE, AI2, lab research blogs (OpenAI/Anthropic/DeepMind) | ai | P2 |
| CFR, Carnegie Endowment, Brookings | cross | P3 |

### D. Research universities & national labs (public_domain/reported)

| Source | Desk | Priority |
|---|---|---|
| MIT Lincoln Lab, JHU APL, Georgia Tech GTRI, CMU Robotics/SEI | defense | P3 |
| MIT Energy Initiative, INL, NREL, Stanford geothermal | energy | P3 |
| Stanford, MIT CSAIL, Berkeley BAIR + arXiv (✅), Papers with Code, Hugging Face, Semantic Scholar | ai | P2 |
| Aggregators — EurekAlert!, ScienceDaily | cross | P3 |

### E. Industry trade press (scrape_gray · reported) — **the big breadth lever**

| Outlet | Desk | Feed | Priority |
|---|---|---|---|
| Breaking Defense, Defense News, Defense One, Defense Daily, DefenseScoop, Defense Industry Daily, Defense-Update | defense | RSS | P1 |
| The War Zone, Janes, Aviation Week, SpaceNews, C4ISRNET, Naval News, Inside Defense, National Defense (NDIA) | defense | RSS | P1 |
| Army/Naval/Airforce Technology (Verdict Media) | defense | RSS | P2 |
| Data Center Dynamics, The Information, SemiAnalysis, IEEE Spectrum, EE Times, HPCwire, The Next Platform | ai | RSS/paywall | P1 |
| Tom's Hardware, The Register, Datacenter Knowledge, Blocks & Files, Manufacturing Dive, Stratechery, Import AI | ai | RSS | P2 |
| Omdia, TrendForce, Yole Group, Mercury Research (analyst notes) | ai | mostly licensed | P3 |
| Utility Dive, World Nuclear News, POWER Magazine, RTO Insider, ANS Nuclear News/Newswire | energy | RSS | P1 |
| E&E News, Canary Media, Heatmap, pv-magazine, Recharge, S&P Commodity Insights | energy | RSS/paywall | P2 |

### F. Industry associations & standards bodies (scrape_gray/reported)

| Body | Desk | Priority |
|---|---|---|
| NDIA, AIA, AUVSI | defense | P3 |
| NEI, EEI, SEIA, ACP, ESA, NHA, World Nuclear Association | energy | P2 |
| SIA, SEMI, WSTS, Open Compute Project, Ultra Ethernet Consortium, MLCommons (MLPerf) | ai | P2 |

### G. Corporate primary — beyond EDGAR (mixed)

| Source | Desk | License | Priority |
|---|---|---|---|
| Press-release wires — PR Newswire, Business Wire, GlobeNewswire | all | scrape_gray | P1 |
| Company IR / newsroom RSS — NVIDIA, AMD, TSMC, hyperscalers, primes (LMT/RTX/GD/NOC), new-defense (Anduril, Palantir, Shield AI, Saronic), nuclear (Oklo, NuScale) | all | scrape_gray | P2 |
| SEC Form D (private funding) · Form 4 · 13F — EDGAR extensions | all | public_domain | P2 |
| Earnings-call transcripts | all | licensed | P3 |
| Crunchbase / PitchBook (private funding) | ai | licensed/paid | P3 |

### H. Patents & technical disclosure (public_domain · confirmed)

| Source | Desk | Priority |
|---|---|---|
| USPTO PatentsView | all | P2 |
| Google Patents (BigQuery) · EPO / WIPO / Espacenet (global) | all | P3 |

### I. Alternative / signal data (mixed · speculative)

| Source | Desk | Priority |
|---|---|---|
| GitHub (release/star velocity) · Hugging Face (model velocity) · Google Trends | ai | P2 |
| Satellite imagery (fab / data-center / reactor construction) | all | P3 (paid) |
| Shipping / customs (chip tools, uranium) · ACLED (conflict) | all | P3 |
| GDELT (✅) · BigQuery GKG/Events backend (entity-spike → entity_edges) | all | P2 |

### J. International / allied government (public_domain/reported)

| Source | Desk | Priority |
|---|---|---|
| UK MOD/DASA · EU EDA · allied MoD contract announcements | defense | P3 |
| UK NESO/ONR · Japan METI · IAEA PRIS | energy | P3 |
| EU AI Act/Commission · Taiwan MOEA · Netherlands (ASML export) | ai | P2 |

---

## 3. Systematic build plan

Sequenced by **coverage-per-engineering-hour**, not by category order.

**Phase 1 — the generic feed adapter (unlocks C–G at scale). ✅ SHIPPED (D104).** ONE configurable
RSS/Atom/sitemap adapter driven by a `feed_registry` of `{url, desk, license_class,
reliability_tier}` rows. This single adapter onboards trade press (E), think tanks (C),
company IR + PR wires (G), associations (F), and university feeds (D). Per-feed
`reliability_tier` drives the Speculative→Reported promotion (D101 follow-up). **This is the
single highest-leverage build** — it converts "60 adapters" into "1 adapter + a config list."

**Phase 2 — structured federal veins (bespoke adapters, confirmed tier).** The non-feed
primary sources that the feed adapter can't handle, in priority order: **SAM.gov, DoD daily
contracts, Congress.gov, EIA, FERC, BIS Entity List**. These mirror the existing
USAspending/EDGAR/NRC adapter pattern and add `confirmed`-tier depth per desk.

**Phase 3 — analyst/aggregate & alt-signal.** Epoch AI / HAI AI Index, USPTO PatentsView,
GitHub/Hugging Face velocity, the BigQuery GKG backend for GDELT (entity-spike → `entity_edges`),
SBIR/STTR, GAO/CRS. International/allied (J) and paid alt-data (satellite, customs) last.

**Cross-cutting:** every new feed/source declares `license_class` + `source_reliability` at
registration (enforced, not hardcoded — extends the D101 citation-license fix); the significance
gate (D085) and the 25-item cap (D100) keep volume bounded regardless of intake size.

## 4. Known gaps in *this* document

Non-exhaustive by design. Categories likely still thin: allied/international defense procurement
portals; state-level energy (PUC dockets, ISO queue feeds per RTO); AI supply-chain (customs,
equipment makers — ASML/AMAT/LAM/TEL); biomanufacturing/synthetic-bio sources; and newsletter-only
analysts (Import AI, SemiAnalysis free tier). Validate per-category before each build phase.

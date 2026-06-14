## Possible Data Sources for HardPowerIntelligence

The sources available are many and since we want this application to provide cutting edge content and analysis I compilede the results of some queries to Gemini, Claude, OpenAI, ... .

### A. Query with Gemini

**1. Initial Prompt:**

What non-profits or other orgs extract and make available GDELT data for public use? I'm building a sophisticated app with front end in vercel, backend in fly.io and supabase and I'm looking for free sources of reporting data from around the globe so GDELT and government data is a idea to pursue aling with other approaches. Specifically as it relates financial/investing/technology advances relate to 1. Defense tech broadly, 2. AI build out broadly, Energy tech broadly. I am building an app with a dashboard for those areas to generate reports and highlight current and useful information for decision makers. I would like a very broad net on current information sources, not just limited to US but global in scope. I want a very high quality and highly relevant to new and changing events sets of analysis.  I will be using openriuter and/or equivalent to all flexibility in llm used for parsing data and generated the best and most comprehensive  reports on daily events in those arenas. This aims to be a low cost subscription based app.

**Response 1**

Building an intelligence dashboard for global macro trends like **Defense Tech, AI Build-out, and Energy Tech** using a modern stack (Vercel + Fly.io + Supabase + OpenRouter) is a brilliant approach. It lets you keep fixed infrastructure costs incredibly low while leaning into the pay-as-you-go flexibility of LLMs.

However, when it comes to GDELT, there is a common misconception: **you do not need a third-party non-profit or intermediary to extract it.**

The GDELT Project itself is an open-access initiative supported by Google Jigsaw, and the raw data is entirely public and free. Here is how organizations host it, how to query it cheaply, and the alternative global datasets you should layer in to get the deep, decision-maker-grade analysis you are looking for.

---

## 1. Accessing GDELT (The Cheap & Direct Way)

Because GDELT updates every 15 minutes and processes terabytes of data, trying to ingest the raw files directly into Supabase will quickly blow past your storage limits. Instead, leverage the platforms that host it for free or near-free.

### The Google BigQuery Public Dataset

Google hosts the entirety of GDELT 2.0 in their BigQuery Public Datasets program.

* **The Cost:** Google gives you **1 TB of free query processing per month**.
* **The Strategy:** Instead of pulling everything, run a cron job from your Fly.io backend every morning. Query BigQuery using targeted SQL to filter only for specific themes relevant to your verticals (e.g., `WB_137_WATER_ENERGY_NEXUS`, `TAX_FNCACT_DEFENSE_MINISTER`, `TECH_ARTIFICIAL_INTELLIGENCE`). Pull just the matching URLs, titles, and event tones, and insert *that* filtered subset into your Supabase database.

### The GDELT Live JSON APIs

If you don't want to touch BigQuery, GDELT provides its own completely free, live JSON APIs (specifically the **GDELT DOC API**). You can hit this API directly from your backend via standard HTTP requests.

* **How to use it:** You can pass complex query strings combining themes and locations (e.g., `sourcelang:eng (theme:ARMEDCONFLICT OR theme:INNOVATION)`) and receive a clean JSON payload of matching global news articles, completely free of charge.

---

## 2. Complementary Global Data Sources

GDELT is incredible for volume and tracking *where* things are happening, but its machine-translation and automated tagging can sometimes lack the deep financial or technical nuance required by high-level decision-makers. To build a robust app, layer in these other open-access and government datasets:

### Vertical 1: AI Build-out & Technology

* **arXiv API (Free):** The absolute gold standard for tracking foundational AI breakthroughs before they hit commercial media. You can poll their free API daily for papers matching specific subfields (e.g., `cs.CL` for computation and language) to highlight what tech shifts are coming next.
* **CSET (Center for Security and Emerging Technology):** A non-profit think tank that regularly releases open data and high-quality analysis on global AI pipelines, semiconductor supply chains, and tech talent flows.

### Vertical 2: Energy Tech & Infrastructure

* **IEA (International Energy Agency) Data Services:** Offers extensive public tracking of global energy investments, clean energy deployment statistics, and policy shifts.
* **EIA API (U.S. Energy Information Administration):** Don't let the name fool you—the EIA tracks comprehensive international energy production, grid capacities, and global trade flows via a highly reliable, free API.
* **ENTSO-E Transparency Platform:** If you want granular data on European power grids, electricity pricing, and renewable generation trends, this platform provides a massive, open API.

### Vertical 3: Defense Tech

* **SIPRI (Stockholm International Peace Research Institute):** A world-renowned non-profit that maintains completely open databases tracking international arms transfers, military expenditures, and defense industry trends. It is the premier source for non-US global defense insights.
* **The United Nations Register of Conventional Arms (UNROCA):** A public, global reporting platform tracking the import and export of defense platforms across member states.

---

## 3. Optimizing Your Tech Stack Architecture

To keep your app highly performant and under a "low-cost subscription" model, your data pipeline should be strictly separated into **Aggregation**, **Vectorization**, and **Synthesis**.

```
[Global Data Sources] (GDELT, arXiv, EIA, SIPRI)
         │
         ▼  (Daily Cron Job / Edge Function)
   [Fly.io Backend] ──> [OpenRouter] (Extract key metrics & sentiment via cheap LLMs)
         │
         ▼
  [Supabase DB] ──────> (Store structured metrics + pgvector embeddings)
         │
         ▼
[Vercel Front End] ───> (Fast, cached dashboard delivery to users)

```

### Architectural Tips for Cost Efficiency:

1. **Never pass raw GDELT text blocks to high-tier LLMs:** Use cheap, fast models on OpenRouter (like Meta's Llama-3-8B or Mistral-7B) to do the initial screening: *"Is this article highly relevant to AI infrastructure or defense tech? Respond Yes or No."*
2. **Only synthesize the winners:** Once the cheap model filters the daily haul down to the top 20 most impactful global stories per vertical, pass *those* curated texts to your premium reasoning models on OpenRouter to generate the sophisticated, decision-maker-grade executive reports.
3. **Utilize `pgvector` in Supabase:** Store the summaries of these key global events as vector embeddings right inside your Supabase database. This will allow your subscription users to ask your dashboard conversational questions (RAG) over past historical events without you needing a separate vector database instance.

**2. Second Prompt as Follow Up**

Can you show me a sample BigQuery SQL query to extract global news links and tones from GDELT specifically filtered for AI infrastructure and clean energy themes?

**Response 2**

To pull highly targetable global news from GDELT, you will want to query the **Global Knowledge Graph (GKG) table** rather than the events table. The GKG table analyzes the actual text of articles, extracts millions of contextual themes, and records advanced tone metrics.

Here is a highly efficient, production-ready BigQuery SQL script designed for your daily Fly.io backend cron job. It targets clean energy, AI infrastructure, and computing themes, applies a strict language filter, and extracts clean URLs, timestamps, and emotional tones.

```sql
WITH filtered_gkg AS (
  SELECT
    -- Parse out the distinct publication date and time
    PARSE_TIMESTAMP('%Y%m%d%H%M%S', CAST(DATE AS STRING)) AS event_timestamp,
    DocumentIdentifier AS url,
    V2Themes AS themes,
    -- V2Tone is a comma-delimited string: Tone, Positivity, Negativity, Polarity, Activity, Density
    -- We split it to extract the base 'Tone' score (index 0) and 'Polarity' (index 3)
    SPLIT(V2Tone, ',')[OFFSET(0)] AS tone_score,
    SPLIT(V2Tone, ',')[OFFSET(3)] AS emotional_polarity,
    -- Capture what source type this is (e.g., 1 = WEB)
    SourceCollectionIdentifier AS source_type
  FROM 
    `gdelt-bq.gdeltv2.gkg`
  WHERE
    -- 1. Partition filter: Crucial for keeping BigQuery costs free/minimal. 
    -- Change this dynamically in your backend script to fetch the last 1 or 2 days.
    _PARTITIONTIME >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 2 DAY)
    
    -- 2. Ensure it is a web article with a valid URL
    AND SourceCollectionIdentifier = 1 
    AND DocumentIdentifier IS NOT NULL
)

SELECT
  event_timestamp,
  url,
  CAST(tone_score AS FLOAT64) AS tone_score,
  CAST(emotional_polarity AS FLOAT64) AS emotional_polarity,
  
  -- Create boolean flags for your specific dashboard verticals based on GDELT system themes
  EXISTS(SELECT 1 FROM UNNEST(SPLIT(themes, ';')) AS t WHERE t IN (
    'TECH_ARTIFICIAL_INTELLIGENCE', 
    'WB_3020_ARTIFICIAL_INTELLIGENCE',
    'COMPUTING',
    'INNOVATION'
  )) AS is_ai_infra,

  EXISTS(SELECT 1 FROM UNNEST(SPLIT(themes, ';')) AS t WHERE t IN (
    'WB_137_WATER_ENERGY_NEXUS',
    'WB_525_RENEWABLE_ENERGY',
    'RENEWABLE_ENERGY',
    'ENERGY_INFRASTRUCTURE',
    'POWER_GENERATION'
  )) AS is_clean_energy

FROM 
  filtered_gkg
WHERE
  -- Filter down the results so you only ingest matching rows into Supabase
  (
    REGEXP_CONTAINS(themes, r'(TECH_ARTIFICIAL_INTELLIGENCE|WB_3020_ARTIFICIAL_INTELLIGENCE|COMPUTING)')
    OR REGEXP_CONTAINS(themes, r'(WB_137_WATER_ENERGY_NEXUS|WB_525_RENEWABLE_ENERGY|RENEWABLE_ENERGY|ENERGY_INFRASTRUCTURE)')
  )
  -- Optional: Use GDELT's multi-lingual processing but filter for English articles 
  -- if your initial OpenRouter parsing logic works best in English.
  AND REGEXP_CONTAINS(themes, r'TAX_WORLDLANGUAGES_ENGLISH')
ORDER BY 
  event_timestamp DESC
LIMIT 1000;

```

### Why this query keeps your costs low

* **The Partition Filter Strategy:** GDELT is massive. If you run a query across the entire `gkg` table, you will burn through your 1 TB free monthly BigQuery tier in a single click. The line `_PARTITIONTIME >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 2 DAY)` forces BigQuery to only scan the last 48 hours of data, keeping the bytes processed to a fraction of a gigabyte per run.
* **The `V2Tone` Parsing:** GDELT calculates a default tone from -100 (extremely negative) to +100 (extremely positive). By parsing `SPLIT(V2Tone, ',')[OFFSET(0)]`, you give your app a numerical filter to immediately flag high-tension or highly favorable global shifts before routing the URLs to OpenRouter.

### How to tie this to OpenRouter

When your backend fires this query via the Google Cloud SDK and pulls the structured URLs into Supabase, you have an ideal framework for an LLM parsing pipeline. You can use a lightweight, inexpensive model to read the headline and metadata first to ensure it fits your dashboard's standard for high-quality decision-making, and then escalate the top results to a larger model for deep, strategic summary generation.

## B. Query with ChatGPT

**1. Initial Prompt**

What non-profits or other orgs extract and make available GDELT data for public use? I'm building a sophisticated app with front end in vercel, backend in fly.io and supabase and I'm looking for free sources of reporting data from around the globe so GDELT and government data is a idea to pursue aling with other approaches. Specifically as it relates financial/investing/technology advances relate to 1. Defense tech broadly, 2. AI build out broadly, Energy tech broadly. I am building an app with a dashboard for those areas to generate reports and highlight current and useful information for decision makers. I would like a very broad net on current information sources, not just limited to US but global in scope. I want a very high quality and highly relevant to new and changing events sets of analysis.  I will be using openriuter and/or equivalent to all flexibility in llm used for parsing data and generated the best and most comprehensive  reports on daily events in those arenas. This aims to be a low cost subscription based app.

**2. Initial Prompt Response**

You’re thinking in the right direction. For a low-cost “daily intelligence dashboard” across **defense tech, AI buildout, and energy tech**, I’d treat GDELT as a **global early-warning/news-discovery layer**, not as the only source of truth. Pair it with procurement, research, patent, energy-market, conflict, trade-policy, and government datasets.

## 1. Who makes GDELT available for public use?

The core public sources are:

| Source                                          | What it gives you                                                                             | Best use in your app                                                                 |
| ----------------------------------------------- | --------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| **GDELT Project**                               | Near-real-time global news/event/knowledge graph data; event database, GKG, DOC APIs, TV APIs | Global monitoring, event detection, narrative tracking, country/company/topic alerts |
| **Google BigQuery Public Datasets**             | Hosted GDELT tables queryable in BigQuery; Google hosts storage, you pay for queries          | Heavy analytics, joins, trend queries, rapid prototyping                             |
| **AWS Open Data Registry**                      | GDELT listed as an open dataset on AWS                                                        | S3/Athena-style pipelines, cheaper batch processing                                  |
| **Open-source clients: `gdeltPyR`, `gdeltdoc`** | Python libraries that simplify GDELT retrieval                                                | Backend ingestion jobs into Supabase/Postgres                                        |
| **Academic / research mirrors and examples**    | Universities and researchers publish notebooks, derived datasets, and dashboards              | Methods, validation, query patterns—not usually production-grade feeds               |

GDELT itself describes the project as a real-time open data “global graph” of world events as seen through global news media, and its Event Database covers 300+ categories of physical activity worldwide, georeferenced and updated every 15 minutes. ([GDELT Project][1]) Google BigQuery has hosted the GDELT event dataset as a public dataset, and GDELT 2.0 tables have historically included Event, Mentions, and GKG tables updated every 15 minutes. ([Google Cloud Blog][2]) AWS also lists GDELT in the Registry of Open Data on AWS, with terms pointing back to GDELT’s own terms of use. ([Open Data on AWS][3])

The practical answer: **there are not many nonprofits that “extract GDELT and repackage it” as a clean commercial-ready feed for free.** Most serious users either query GDELT directly, use BigQuery/AWS, or build their own derived tables. That is actually an opportunity for your product: your value is not “access to GDELT,” but **curation, entity resolution, topic filtering, deduplication, citations, and decision-grade summaries.**

## 2. Strong adjacent global news / event sources

| Source                            | Type                                | Why it matters                                                                              |
| --------------------------------- | ----------------------------------- | ------------------------------------------------------------------------------------------- |
| **Media Cloud**                   | Open-source media research platform | Alternative/complement to GDELT for studying global news attention and information flows    |
| **Common Crawl News / web crawl** | Nonprofit web crawl corpus          | Useful for broad web/news discovery if you can process large archives                       |
| **ReliefWeb / OCHA**              | UN humanitarian reports API         | Excellent for conflict, disaster, infrastructure, sanctions-adjacent, fragile-state context |
| **ACLED**                         | Global conflict/protest event data  | High-quality conflict/protest layer for defense/geopolitical risk                           |
| **Global Trade Alert**            | Trade policy database               | Industrial policy, subsidies, export controls, tariffs, reshoring, geoeconomic competition  |

Media Cloud is an open-source media research project administered by a consortium involving UMass Amherst and Northeastern, originally incubated at Harvard and MIT; it focuses on studying news and information flow globally. ([Media Cloud][4]) ReliefWeb provides a developer-friendly API for humanitarian reports, jobs, and training data, with archives of curated humanitarian information from many sources. ([ReliefWeb][5]) ACLED describes itself as an independent, impartial conflict monitor providing real-time data and analysis on violent conflict and protest across all countries and territories. ([ACLED][6]) Global Trade Alert provides a data center and API access for trade-policy interventions, with free use noted for non-commercial users and licensing for commercial/geographic/policy packages. ([Global Trade Alert][7])

For your app, I’d use **GDELT + Media Cloud + ReliefWeb + ACLED + Global Trade Alert** as the “global current-events spine.”

## 3. Defense tech / defense industrial base data

| Source                                     | Geography                | Use case                                                                  |
| ------------------------------------------ | ------------------------ | ------------------------------------------------------------------------- |
| **USAspending API**                        | U.S.                     | Defense awards, grants, contracts, agency spending                        |
| **SAM.gov APIs / GSA Open APIs**           | U.S.                     | Opportunities, entity data, exclusions, contract awards                   |
| **EU TED Developer Portal**                | EU / EEA                 | European public procurement, tenders, contract awards                     |
| **UK Contracts Finder API**                | UK                       | Public-sector opportunities and contracts                                 |
| **SIPRI databases**                        | Global                   | Military expenditure, arms transfers, arms industry                       |
| **World Bank military indicators**         | Global                   | Normalized country-level defense spending / arms import-export indicators |
| **NATO, EU Defence Agency, national MoDs** | Mostly regional/national | Budgets, strategy docs, procurement announcements                         |
| **Sanctions/export-control lists**         | U.S., EU, UK, UN, others | Entity risk, semiconductor/export-control relevance                       |

USAspending is the official open-data source for U.S. federal spending, and its API currently exposes endpoints that do not require authorization. ([USAspending][8]) GSA’s open API catalog includes SAM.gov APIs for entity/exclusion extracts, contract awards, entity management, and exclusions. ([GSA Open Technology][9]) TED is the EU’s official Tenders Electronic Daily portal for European public procurement, and the TED Developer Portal provides developer access. ([TED Developer Portal][10]) SIPRI’s open-access databases cover arms transfers, arms industry, and military expenditure; the Military Expenditure Database includes country spending time series from 1949–2025. ([SIPRI][11])

For defense tech, the most valuable signal will often be **procurement + GDELT + patents + company/entity matching**. Example: “new drone swarm procurement in Poland” should connect a TED notice, a local-language article, relevant vendors, NATO/EU policy context, and comparable awards in the U.S. or UK.

## 4. AI buildout / compute / model / research sources

| Source                                            | Use case                                                                       |
| ------------------------------------------------- | ------------------------------------------------------------------------------ |
| **arXiv API**                                     | Daily AI, robotics, autonomy, energy, chip, quantum, defense-adjacent research |
| **OpenAlex API / snapshot**                       | Global scholarly metadata, institutions, funders, topics                       |
| **Semantic Scholar API**                          | Paper relevance, citation graph, abstracts, author/institution signal          |
| **Hugging Face models / papers / datasets**       | Open model releases, trending models, datasets, demos                          |
| **OECD.AI**                                       | AI policy, AI investments, AI jobs, AI compute, AI models/datasets, AI patents |
| **Papers with Code historical / alternatives**    | Benchmark tracking; check current maintenance before relying on it             |
| **GitHub API**                                    | Open-source velocity, repo stars, releases, contributors                       |
| **Cloud provider blogs / status / pricing pages** | AI infrastructure buildout, GPUs, data centers, model deployment trends        |
| **SEC EDGAR / company filings**                   | Capex, data centers, GPU supply, AI revenue, risk disclosures                  |

OpenAlex describes itself as a fully open catalog of the global research system, with API and full data snapshot access. ([OpenAlex Developers][12]) arXiv provides an API for programmatic access to its e-print corpus. ([arXiv Info][13]) Semantic Scholar is a free AI-powered scientific literature tool from Ai2 and offers API documentation. ([Semantic Scholar][14]) OECD.AI provides access to 900+ national AI policies and initiatives and live data across AI research, jobs, software development, compute, models/datasets, news, and patents. ([OECD.AI][15])

For AI buildout, the high-value dashboard views are probably:

**Research velocity:** arXiv/OpenAlex/Semantic Scholar.
**Model velocity:** Hugging Face/GitHub.
**Commercial buildout:** SEC filings, company blogs, procurement, data-center energy interconnect queues.
**Policy/regulatory risk:** OECD.AI, EU AI Act sources, NIST, national AI offices.
**Compute supply chain:** export controls, semiconductor filings, hyperscaler capex, chip foundry news.

## 5. Energy tech / grid / electrification sources

| Source                                               | Geography                          | Use case                                                                |
| ---------------------------------------------------- | ---------------------------------- | ----------------------------------------------------------------------- |
| **EIA API**                                          | U.S. + international energy series | Oil, gas, electricity, prices, generation, capacity                     |
| **Ember Energy API / datasets**                      | Global                             | Electricity generation, demand, emissions, carbon intensity             |
| **IEA data and reports**                             | Global                             | Authoritative global energy statistics, but some datasets are paid      |
| **Our World in Data Grapher API**                    | Global                             | Clean CSV/JSON access to many processed energy indicators               |
| **ENTSO-E Transparency Platform**                    | Europe                             | Power generation, load, transmission, outages                           |
| **Open Power System Data**                           | Europe-heavy                       | Grid, generation, time-series datasets                                  |
| **World Bank / Data Commons**                        | Global                             | Macro, energy access, emissions, development indicators                 |
| **National grid operators / interconnection queues** | Country/regional                   | Data-center power demand, renewables, storage, transmission bottlenecks |

EIA says it makes free and open energy data available through an API, with a free API key required for API calls. ([U.S. Energy Information Administration][16]) Ember provides open electricity datasets through an API and covers yearly/monthly electricity generation, demand, emissions, and carbon-intensity data. ([Ember Energy][17]) IEA describes its Energy Data Centre as a comprehensive global energy data source, though its documentation distinguishes free and paid datasets. ([IEA][18]) Our World in Data’s Grapher API exposes chart data programmatically, and its energy datasets often include CSV/metadata downloads. ([OWID Documentation][19])

For energy tech, I’d prioritize **Ember + EIA + OWID + grid/operator data**. IEA is excellent for analysis and citation, but less ideal as a free automated backend if the data you need sits behind paid products.

## 6. Patents, innovation, and technology signals

| Source                                     | Use case                                                      |
| ------------------------------------------ | ------------------------------------------------------------- |
| **USPTO Open Data Portal / bulk datasets** | U.S. patent applications, grants, assignments, file wrappers  |
| **WIPO PATENTSCOPE**                       | PCT and international patent collections                      |
| **EPO Open Patent Services**               | European/global patent metadata                               |
| **The Lens**                               | Excellent patent/scholar graph, but commercial use needs care |
| **OpenAlex + patents via OECD.AI**         | AI patent trend analysis                                      |
| **GitHub + package registries**            | Open-source implementation signal                             |

USPTO’s Open Data Portal lets users search and download publicly available bulk datasets, and its API supports bulk-data search/download. ([USPTO Data][20]) WIPO’s PATENTSCOPE gives access to published international PCT applications and patent documents from participating national/regional offices, with programmatic access options described for some document access. ([WIPO][21])

Patents are slower than news, but they’re excellent for **strategic trend detection**: autonomy, directed energy, battery chemistries, grid storage, AI accelerators, radar, EW, satellites, drones, nuclear, fusion, and cybersecurity.

## 7. My recommended data architecture for your app

Given **Vercel frontend + Fly.io backend + Supabase**, I’d build this as a staged intelligence pipeline:

### Layer A — Raw ingestion

Use scheduled Fly.io workers or GitHub Actions to pull:

| Cadence         | Sources                                                                                              |
| --------------- | ---------------------------------------------------------------------------------------------------- |
| Every 15–60 min | GDELT DOC/GKG, RSS feeds, selected government press releases, Hugging Face trending, GitHub releases |
| Daily           | arXiv, OpenAlex deltas, USAspending/SAM/TED/Contracts Finder, ReliefWeb, ACLED, Ember/EIA            |
| Weekly/monthly  | SIPRI, patent bulk updates, IEA/OWID/Data Commons, company filings                                   |

Store raw records in Supabase tables or object storage:

`raw_items`
`source_runs`
`documents`
`entities`
`events`
`signals`
`citations`
`reports`

### Layer B — Normalization

Normalize every item into a common schema:

```text
title
summary
source_name
source_url
published_at
retrieved_at
language
country
region
sector: defense | ai | energy | cross-sector
subsector
entities: companies, agencies, people, countries, technologies
event_type
confidence
novelty_score
importance_score
source_reliability_score
```

### Layer C — Entity resolution

This is where your app becomes valuable. Match:

Company names → tickers, subsidiaries, contractors, CAGE/UEI, LEI, OpenCorporates IDs
Government buyers → agencies, ministries, military branches
Technologies → taxonomy terms
Locations → country/region/grid zone/conflict zone
Research → institutions/funders/companies
Procurement → vendor, buyer, CPV/NAICS/PSC codes

### Layer D — Signal scoring

For each candidate item, score:

**Novelty:** Is this actually new, or just a reprint?
**Materiality:** Could this affect budgets, supply chains, investment, regulation, or strategic advantage?
**Confidence:** Is it confirmed by multiple sources?
**Decision relevance:** Does it matter to a policymaker, investor, executive, or analyst?
**Time sensitivity:** Is this a “today” item or background context?

### Layer E — LLM report generation

Use OpenRouter or an equivalent model router for flexibility. I’d use a cheap model for extraction/classification and a stronger model for final synthesis.

A good pattern:

1. **Cheap model:** classify, tag, extract entities, produce 5-bullet summaries.
2. **Embedding model:** deduplicate and cluster related stories.
3. **Stronger model:** generate executive report with citations.
4. **Validation pass:** check every claim against stored citations.
5. **Final report:** dashboard cards + long-form daily brief.

## 8. Suggested MVP source stack

For a strong low-cost MVP, I’d start with this:

### Core global events

1. **GDELT DOC 2.0 / GKG**
2. **Media Cloud**
3. **ReliefWeb**
4. **ACLED**, depending on licensing/commercial use
5. **Global Trade Alert**, likely licensing review needed for commercial subscription use

### Defense

6. **USAspending**
7. **SAM.gov / GSA APIs**
8. **EU TED**
9. **UK Contracts Finder**
10. **SIPRI**

### AI

11. **arXiv**
12. **OpenAlex**
13. **Semantic Scholar**
14. **Hugging Face models/datasets/papers**
15. **OECD.AI**

### Energy

16. **EIA**
17. **Ember**
18. **Our World in Data**
19. **Data Commons**
20. **Grid/operator data where available**

Data Commons is useful as a general statistical layer because it provides REST, Python, and Pandas APIs over a knowledge graph that aggregates many public datasets. ([Data Commons][22])

## 9. Product positioning idea

Your product should not be “a GDELT dashboard.” That will sound too commodity. I’d position it more like:

> **A decision-intelligence dashboard for defense, AI infrastructure, and energy transition events—combining global media, procurement, research, patents, policy, conflict, and energy data into cited daily briefings.**

The moat is:

1. **Cross-domain synthesis:** defense + AI + energy are increasingly one system.
2. **Global coverage:** not just U.S. sources.
3. **Cited reports:** every claim traceable.
4. **Entity intelligence:** companies, agencies, technologies, contracts, geographies.
5. **Timeliness:** daily or intraday signal detection.
6. **Low-cost automation:** cheap models for extraction, premium models only for synthesis.

## 10. Important caution

For a paid subscription app, check licenses carefully. “Free to access,” “open data,” “non-commercial,” and “redistributable in a paid product” are not the same thing. GDELT, USAspending, EIA, OWID, and many government APIs are generally friendly starting points, but sources like Global Trade Alert, ACLED, some patent services, IEA datasets, and commercial news APIs may require explicit commercial licensing depending on how you display, store, summarize, or redistribute the data.

[1]: https://www.gdeltproject.org/?utm_source=chatgpt.com "The GDELT Project"
[2]: https://cloudplatform.googleblog.com/2014/05/worlds-largest-event-dataset-now-publicly-available-in-google-bigquery.html?utm_source=chatgpt.com "World's largest event dataset now publicly available in BigQuery"
[3]: https://registry.opendata.aws/gdelt/?utm_source=chatgpt.com "Global Database of Events, Language and Tone (GDELT)"
[4]: https://www.mediacloud.org/?utm_source=chatgpt.com "Media Cloud"
[5]: https://reliefweb.int/help/api?utm_source=chatgpt.com "ReliefWeb API"
[6]: https://acleddata.com/?utm_source=chatgpt.com "ACLED"
[7]: https://globaltradealert.org/?utm_source=chatgpt.com "Global Trade Alert - Monitoring Policy Changes That Affect ..."
[8]: https://www.usaspending.gov/?utm_source=chatgpt.com "USAspending: Government Spending Open Data"
[9]: https://open.gsa.gov/api/?utm_source=chatgpt.com "APIs | GSA Open Technology"
[10]: https://developer.ted.europa.eu/?utm_source=chatgpt.com "TED Developer Portal - European Union"
[11]: https://www.sipri.org/research/armament-and-disarmament/arms-and-military-expenditure?utm_source=chatgpt.com "Arms and military expenditure"
[12]: https://developers.openalex.org/?utm_source=chatgpt.com "OpenAlex API"
[13]: https://info.arxiv.org/help/api/user-manual.html?utm_source=chatgpt.com "arXiv API User's Manual"
[14]: https://www.semanticscholar.org/?utm_source=chatgpt.com "Semantic Scholar | AI-Powered Research Tool"
[15]: https://oecd.ai/?utm_source=chatgpt.com "OECD.AI: The OECD Artificial Intelligence Policy Observatory"
[16]: https://www.eia.gov/opendata/?utm_source=chatgpt.com "Opendata - U.S. Energy Information Administration (EIA)"
[17]: https://ember-energy.org/data/?utm_source=chatgpt.com "Data - Ember Energy"
[18]: https://www.iea.org/data-and-statistics?utm_source=chatgpt.com "Data and statistics"
[19]: https://docs.owid.io/projects/etl/api/chart-api/?utm_source=chatgpt.com "Grapher Chart API - OWID's Technical Documentation"
[20]: https://data.uspto.gov/?utm_source=chatgpt.com "Open Data Portal - USPTO"
[21]: https://www.wipo.int/en/web/patentscope?utm_source=chatgpt.com "PATENTSCOPE"
[22]: https://docs.datacommons.org/?utm_source=chatgpt.com "How to use Data Commons - Docs - Data Commons"

**Follow Up Prompt to ChatGPT 5.5**

Can you show me a sample BigQuery SQL query to extract global news links and tones from GDELT specifically filtered for AI infrastructure and clean energy themes?

**Response 2 From ChatGPT 5.5**

Below is a solid **BigQuery Standard SQL** starter query against **GDELT 2.0 GKG**. I’d use the **GKG table** for this because it has article links, source names, themes, locations, people/org fields, and tone fields. GDELT’s GKG 2.0 updates every 15 minutes, and GDELT’s own sample BigQuery docs use fields like `V2Themes`, `V2Persons`, and the GKG table for thematic filtering. ([GDELT Project][1])

```sql
-- GDELT 2.0 GKG: global AI infrastructure + clean energy news links + tone
-- BigQuery Standard SQL

DECLARE start_ts TIMESTAMP DEFAULT TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY);
DECLARE end_ts   TIMESTAMP DEFAULT CURRENT_TIMESTAMP();

WITH gdelt AS (
  SELECT
    PARSE_TIMESTAMP('%Y%m%d%H%M%S', CAST(DATE AS STRING)) AS published_ts,
    SourceCommonName AS source,
    DocumentIdentifier AS url,
    V2Themes,
    V2Locations,
    V2Organizations,
    V2Persons,
    V2Tone
  FROM `gdelt-bq.gdeltv2.gkg_partitioned`
  WHERE
    -- Use partition pruning to control cost.
    _PARTITIONTIME BETWEEN TIMESTAMP_TRUNC(start_ts, DAY)
                       AND TIMESTAMP_TRUNC(end_ts, DAY)

    -- Optional extra safety on actual GDELT DATE field.
    AND PARSE_TIMESTAMP('%Y%m%d%H%M%S', CAST(DATE AS STRING))
        BETWEEN start_ts AND end_ts

    AND DocumentIdentifier IS NOT NULL
),

parsed AS (
  SELECT
    published_ts,
    source,
    url,
    V2Themes,
    V2Locations,
    V2Organizations,
    V2Persons,

    -- V2Tone is comma-separated:
    -- Tone, PositiveScore, NegativeScore, Polarity, ActivityRefDensity,
    -- SelfGroupRefDensity, WordCount
    SAFE_CAST(SPLIT(V2Tone, ',')[SAFE_OFFSET(0)] AS FLOAT64) AS tone,
    SAFE_CAST(SPLIT(V2Tone, ',')[SAFE_OFFSET(1)] AS FLOAT64) AS positive_score,
    SAFE_CAST(SPLIT(V2Tone, ',')[SAFE_OFFSET(2)] AS FLOAT64) AS negative_score,
    SAFE_CAST(SPLIT(V2Tone, ',')[SAFE_OFFSET(3)] AS FLOAT64) AS polarity,
    SAFE_CAST(SPLIT(V2Tone, ',')[SAFE_OFFSET(6)] AS INT64) AS word_count
  FROM gdelt
),

classified AS (
  SELECT
    *,
    REGEXP_CONTAINS(
      LOWER(CONCAT(
        IFNULL(V2Themes, ''), ' ',
        IFNULL(V2Organizations, ''), ' ',
        IFNULL(url, '')
      )),
      r'(artificial_intelligence|ai\b|machine_learning|generative ai|large language model|llm\b|gpu|nvidia|semiconductor|chip|data center|datacenter|cloud computing|hyperscale|compute|accelerator|h100|h200|b200|blackwell|inference|training cluster|supercomputer)'
    ) AS is_ai_infrastructure,

    REGEXP_CONTAINS(
      LOWER(CONCAT(
        IFNULL(V2Themes, ''), ' ',
        IFNULL(V2Organizations, ''), ' ',
        IFNULL(url, '')
      )),
      r'(renewable|clean energy|solar|wind power|offshore wind|battery storage|energy storage|grid|transmission|hydrogen|electrolyzer|nuclear|small modular reactor|smr\b|geothermal|carbon capture|ccus|heat pump|ev charging|lithium|critical minerals|rare earth|uranium|fusion)'
    ) AS is_clean_energy
  FROM parsed
)

SELECT
  published_ts,
  source,
  url,
  CASE
    WHEN is_ai_infrastructure AND is_clean_energy THEN 'AI infrastructure + clean energy'
    WHEN is_ai_infrastructure THEN 'AI infrastructure'
    WHEN is_clean_energy THEN 'Clean energy'
  END AS theme_bucket,
  tone,
  positive_score,
  negative_score,
  polarity,
  word_count,
  V2Locations AS locations_raw,
  V2Organizations AS organizations_raw,
  V2Themes AS themes_raw
FROM classified
WHERE
  is_ai_infrastructure OR is_clean_energy
ORDER BY published_ts DESC
LIMIT 500;
```

A couple of notes:

The query uses `gdelt-bq.gdeltv2.gkg_partitioned`, which is preferable for cost control because you can prune by `_PARTITIONTIME`; people working with GDELT in BigQuery commonly recommend the partitioned table for cheaper queries. ([quaintitative][2])

`DocumentIdentifier` is the article URL. `SourceCommonName` is the normalized source domain. `V2Tone` is a comma-separated tone vector, so the query splits it into usable numeric fields. `V2Themes`, `V2Locations`, and `V2Organizations` are still raw semicolon-delimited fields; for production, I’d explode those into child tables.

For your app, I’d probably split this into two queries: one cheap **ingestion query** that pulls raw GDELT records into Supabase, and one **classification/enrichment step** in your Fly.io backend that applies your own taxonomy and LLM-assisted tagging. BigQuery regex is fine for initial filtering, but your product quality will come from cleaner entity resolution and better theme scoring.

[1]: https://www.gdeltproject.org/data.html?utm_source=chatgpt.com "Data: Querying, Analyzing and Downloading"
[2]: https://writing.quaintitative.com/extract_gdelt_gkg_bigquery/?utm_source=chatgpt.com "Extracting and Processing GDELT GKG datasets from BigQuery"

## Prompt to Claude Sonnet 4.6

**1. Initial Prompt**

What non-profits or other orgs extract and make available GDELT data for public use? I'm building a sophisticated app with front end in vercel, backend in fly.io and supabase and I'm looking for free sources of reporting data from around the globe so GDELT and government data is a idea to pursue aling with other approaches. Specifically as it relates financial/investing/technology advances relate to 1. Defense tech broadly, 2. AI build out broadly, Energy tech broadly. I am building an app with a dashboard for those areas to generate reports and highlight current and useful information for decision makers. I would like a very broad net on current information sources, not just limited to US but global in scope. I want a very high quality and highly relevant to new and changing events sets of analysis.  I will be using openriuter and/or equivalent to all flexibility in llm used for parsing data and generated the best and most comprehensive  reports on daily events in those arenas. This aims to be a low cost subscription based app.

**Initial Response**

Here's a broad-net rundown organized by layer, with an eye toward your Fly.io/Supabase/Vercel + OpenRouter stack.

## GDELT itself and orgs that repackage it

GDELT is already free and public — no intermediary nonprofit is strictly required, but a few make it easier to consume:

- **GDELT Project (gdeltproject.org)** — the source. The DOC 2.0 API and GEO API are queryable in near real-time (15-min update cycle), and the GKG (Global Knowledge Graph) gives you entity/theme/tone extraction per article, which is genuinely useful for auto-tagging articles into your defense/AI/energy buckets.
- **Google BigQuery public dataset (`gdelt-bq`)** — full Events + GKG tables, queryable with BigQuery's free monthly tier (1TB queries/month free). Good for backtesting and building your initial entity-theme taxonomy.
- **AWS Registry of Open Data** mirrors the same data on S3, useful if you want to avoid BigQuery egress costs.
- **gdeltdoc / gdelt Python packages** — community wrappers that make the DOC API easier to hit on a schedule from a Fly.io worker.

There isn't really a separate "GDELT nonprofit middleman" ecosystem beyond this — most serious users (Our World in Data, academic groups, OSINT shops) just hit the raw feeds directly.

## General global news layer

- **GNews, NewsData.io, Currents API, Mediastack** — all have free tiers (typically 100–200 requests/day) with multi-language, multi-country coverage. Good for breadth but you'll hit rate limits fast at scale; treat as supplementary.
- **Direct RSS from primary outlets** — Reuters, AP, Defense News, Breaking Defense, Defense One, The War Zone, Janes, Ars Technica, Tom's Hardware, Semafor, Rest of World (for non-US tech coverage) all publish RSS. Zero cost, no rate limits, and often higher signal-to-noise than aggregator APIs for your specific verticals.
- **Common Crawl** — petabyte-scale web crawl on S3, free to query via Athena. Overkill for daily ops but useful if you ever want to backfill historical context or train a classifier.

## Defense tech vertical

- **USAspending.gov API** — no key required, covers all US federal contract awards. Filter by PSC/NAICS codes for defense-relevant procurement (you'll know these codes well from your HII/F-35 work).
- **SAM.gov API** — free key (takes ~10 business days), gives open solicitations/opportunities — pairs with USAspending for "what's being bid" vs "what got awarded."
- **SBIR.gov award database** — 220k+ awards, searchable by agency/keyword, great signal for emerging defense tech companies before they're widely known.
- **DoD daily contract announcements (defense.gov/News/Contracts)** — RSS-able, gives you same-day notice of major defense awards.
- **SIPRI** — free downloadable datasets on arms transfers and military expenditure by country, good for the global (non-US) angle.
- **Think tank RSS feeds** — CSIS, RAND, Atlantic Council's Forward Defense, IISS all publish analysis that's effectively free expert commentary on defense tech trends.

## AI buildout vertical

- **arXiv API** — free, no key, query cs.AI/cs.LG/cs.CL daily for new papers — useful both as content and as a signal of which labs/topics are heating up.
- **Hugging Face API** — trending papers, models, and the Open LLM Leaderboard/Chatbot Arena data via public Gradio endpoints.
- **Epoch AI** — free datasets tracking compute trends, notable model releases, and training cost estimates — strong for "AI buildout" framing specifically.
- **Artificial Analysis** — model benchmark leaderboards plus capex tracking for major AI labs, sourced largely from SEC filings.
- **SEC EDGAR full-text search (efts.sec.gov)** — free, no key, lets you search all filings for terms like "AI infrastructure," "data center," "GPU capacity" — a good proxy for hyperscaler capex commitments as they're disclosed.
- **OpenRouter's own `/api/v1/models` endpoint** — public, no auth — model availability and pricing churn is itself a weak signal of competitive dynamics worth tracking.

## Energy tech vertical

- **EIA API (eia.gov/opendata)** — free key, deep US energy data (electricity, generation capacity, natural gas, renewables) updated regularly.
- **IEA free datasets** — most IEA data is paywalled (there's an active open-data advocacy campaign about this from Our World in Data), but the World Energy Outlook free dataset and several trackers (EV Data Explorer, etc.) are open.
- **Our World in Data energy datasets** — free CSV/API access, good global coverage where IEA itself is locked down.
- **Global Energy Monitor** — free databases tracking power plants, LNG terminals, coal/gas/renewable project pipelines globally — excellent for "what's being built where" at a project level.
- **DOE/ARPA-E press releases and award announcements** — RSS-able, useful for US energy tech funding signal.

## Financial/markets layer

- **OpenBB SDK** — open-source, aggregates FRED, SEC EDGAR, Tiingo, and others through one Python interface; free tier covers a lot of fundamental data (earnings, balance sheets) that would otherwise require separate API keys.
- **FRED API** — free, macro indicators (rates, inflation, etc.) for framing the "why now" in your reports.
- **SEC EDGAR** (structured XBRL + full-text search) — both free and keyless, core for company-level financial signal across all three verticals.

## Pipeline thoughts for your stack

Given Fly.io for backend, I'd structure this as scheduled workers (cron-triggered Fly machines or a lightweight queue) that pull from each source on its own cadence — GDELT every 15 min, news RSS hourly, government data daily, SEC/EIA/SIPRI weekly — normalizing everything into a few Supabase tables (raw_items, entities, themes, source_metadata). The GDELT GKG's entity/theme extraction is genuinely useful here as a free pre-classifier to route incoming items into your three verticals before they hit the LLM stage. For OpenRouter, a two-tier approach probably makes sense: a cheap/fast model for triage and dedup classification across the firehose, and a stronger model for the actual daily synthesis report generation per vertical — keeps your per-report cost low while reserving quality for the output users actually pay for.

One thing worth flagging: IEA's best global energy data is paywalled, and EIA covers US only well — for a genuinely global energy picture you may end up leaning more on Global Energy Monitor and Our World in Data than on IEA directly unless you budget for an IEA subscription later.

**Follow Up Prompt**

Here's a starting query against `gdelt-bq.gdeltv2.gkg_partitioned` (the partitioned table is much cheaper to query than `gkg`, since it lets BigQuery skip data outside your date range).

## Core extraction query

```sql
SELECT
  DATE,
  SourceCommonName AS source,
  DocumentIdentifier AS url,
  CAST(SPLIT(V2Tone, ',')[OFFSET(0)] AS FLOAT64) AS tone,
  V2Themes,
  V2Organizations
FROM
  `gdelt-bq.gdeltv2.gkg_partitioned`
WHERE
  _PARTITIONTIME BETWEEN TIMESTAMP("2026-06-01") AND TIMESTAMP("2026-06-13")
  AND (
    V2Themes LIKE '%ARTIFICIAL_INTELLIGENCE%'
    OR V2Themes LIKE '%TECH_AUTOMATION%'
    OR V2Organizations LIKE '%nvidia%'
    OR V2Organizations LIKE '%openai%'
    OR V2Organizations LIKE '%data center%'
  )
  AND (
    V2Themes LIKE '%ENV_SOLAR%'
    OR V2Themes LIKE '%ENV_WINDPOWER%'
    OR V2Themes LIKE '%ENV_NUCLEARPOWER%'
    OR V2Themes LIKE '%ENV_HYDRO%'
    OR V2Themes LIKE '%ENV_GEOTHERMAL%'
    OR V2Themes LIKE '%ENV_CARBONCAPTURE%'
    OR V2Themes LIKE '%ENV_GREEN%'
  )
ORDER BY DATE DESC
LIMIT 200
```

A few things worth knowing about this:

`V2Tone` is a comma-separated list of seven values (overall tone, positive score, negative score, polarity, activity reference density, self/group reference density, word count). The split above pulls just the overall tone, which runs roughly -100 to +100 with most articles clustering near 0.

The `AND` between the two theme groups means you're getting the **intersection** — articles that mention both AI/tech *and* clean energy in the same piece. That's actually the more interesting query for your use case right now, since it surfaces the "AI data centers driving nuclear/solar/grid demand" story cluster specifically, rather than just two unrelated firehoses. If you want broader separate feeds for each vertical, just split this into two queries with only one `WHERE` group each (use `OR` between them instead of `AND` if you want either-topic coverage).

## Caveat on theme codes

GDELT's core GKG theme taxonomy (~a few thousand codes) doesn't have a single canonical "AI infrastructure" tag — `ARTIFICIAL_INTELLIGENCE`-style themes exist but coverage is uneven, especially for newer terms like "AI data center" or "GPU cluster." That's why I added `V2Organizations`/keyword matching alongside theme matching above — it catches articles that mention the relevant companies/infrastructure even when the theme tagger missed it.

If you want to see exactly what theme codes are actually firing for your topics before locking in filters, run a discovery query like this over a sample window:

```sql
WITH nested AS (
  SELECT SPLIT(RTRIM(REGEXP_REPLACE(V2Themes, r',\d+;', ';'), ';'), ';') AS themes
  FROM `gdelt-bq.gdeltv2.gkg_partitioned`
  WHERE _PARTITIONTIME BETWEEN TIMESTAMP("2026-06-01") AND TIMESTAMP("2026-06-08")
    AND length(V2Themes) > 1
    AND (V2Organizations LIKE '%nvidia%' OR V2Organizations LIKE '%openai%')
)
SELECT theme, COUNT(1) AS cnt
FROM nested, UNNEST(themes) AS theme
GROUP BY theme
ORDER BY cnt DESC
LIMIT 50
```

That'll show you the actual co-occurring theme codes for AI-related articles, which you can then fold into your production filter — same trick works for your energy-side queries to find the codes that actually correlate with the stories you care about. The full GKG 2.0 theme codebook (linked from gdeltproject.org/data.html) is the reference for the canonical list if you want to browse it directly.

On cost: a 7–13 day window on the partitioned table is typically in the tens of GB, well within BigQuery's 1TB/month free tier — but if you eventually run this daily as a Fly.io cron job, cache results in Supabase rather than re-querying historical ranges each time.

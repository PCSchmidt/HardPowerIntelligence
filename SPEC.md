# Spec — Hard Power Intelligence, Cycle 1

Feature list for the Defense desk, web-only build. Section headers (##) become
FEATURES.json entries via `features-init.sh`. One section = one trackable feature.

Cycle 1 acceptance criteria live in CONTRACT.md. Scope boundaries live in
docs/SCOPE.md.

---

## Data Ingestion — USAspending Adapter

Fetch DoD contract awards from the USAspending API on a daily cadence.
Parse into immutable `RawRecord` objects (url + fetched_at + content_hash + payload).
Dedup by `(source_id, native_id)` + `content_hash` — re-running is always safe.
Store raw records in Supabase `raw_records` table.
Test suite covers fetch (mocked network), parse (golden fixtures), and dedup logic.

## Data Ingestion — SAM.gov Adapter

Fetch SAM.gov contract opportunities and entity registry records.
Same `RawRecord` contract as the USAspending adapter.
Daily cadence; incremental fetch via per-source watermark cursor.

## Data Ingestion — DoD Daily Contracts Adapter

Scrape the DoD daily contracts page (awards > $7.5M).
`license_class: public_domain`. Respect robots.txt and rate limits.
Parse press-release text into structured fields: awardee name, amount, program,
contracting office.

## Data Ingestion — EDGAR Adapter

Fetch 8-K, 10-K, 10-Q, Form 4 (insiders), and DEF 14A filings for defense-sector
entities. Use the EDGAR EDGAR full-text + submissions + company-facts REST APIs.
Required User-Agent header: `HardPowerIntelligence/1.0 contact@hardpowerintel.com`.

## Data Ingestion — Scheduler

Source registry table (`source_registry`) drives per-source fetch cadence.
APScheduler + Postgres job queue (`FOR UPDATE SKIP LOCKED`) executes due jobs.
Token-bucket rate limiting, exponential backoff, and a circuit breaker per source.
Budget guard pauses paid sources if daily spend exceeds cap.
Supabase `pg_cron` enqueues due jobs.

## Entity Resolution — Crosswalk Spine

Load free identifier crosswalks into Supabase:
- SEC `company_tickers.json` (ticker ↔ CIK)
- OpenFIGI (ticker / CUSIP ↔ FIGI)
- GLEIF LEI (legal-entity parent / child)
- SAM.gov / USAspending recipient hierarchy (UEI ↔ parent)
Deterministic lookup resolves most defense contractor mentions O(1).

## Entity Resolution — Mention Disambiguation

For mentions not resolved by deterministic crosswalk:
1. Normalize name (uppercase, strip Inc/Corp/LLC, expand abbreviations).
2. Candidate generation: `pg_trgm` fuzzy match + pgvector semantic match.
3. Score candidates: high → auto-link; medium → cheap-LLM disambiguation;
   low → human review queue.
4. Cache resolved mappings so future mentions are deterministic.
Bitemporal edges (`valid_from` / `valid_to`) handle renames and reorganizations.

## Brief Generation — Change Detection

Diff the entity graph since the last brief: new edges, new records, numeric series
moves past materiality threshold.
Score each candidate event: source authority + novelty + magnitude + entity
importance + corroboration.
Drop low-materiality noise before any LLM spend.

## Brief Generation — RAG Synthesis

Graph-grounded hybrid retrieval:
- Structured facts from the entity graph (amounts, dates, resolved tickers,
  1–2 hop neighbors) — the non-hallucinable spine.
- Unstructured passages from text chunks (color, quotes via pgvector), each
  carrying a citation id.
Waterfall synthesis: cheap models cluster and select candidates; strong model writes
final prose constrained to cited facts and passages only.

## Brief Generation — Citation Eval Gate

Every claim in the generated brief carries a citation id.
A verifier (entailment check for prose; exact-match for numbers) confirms each
claim against its source record before the brief is marked publish-ready.
A brief below the citation-faithfulness threshold does not ship.
The eval score is a published product metric.

## Brief Delivery — Web Cards and PDF

One `Brief` JSON renders to:
- Web cards (Defense desk reader, streamed from Supabase / cached)
- PDF export (Pro tier only; Puppeteer or WeasyPrint)
`citations[]` array becomes the source-citation drawer on the web reader.
`license_class` on each record controls full-quote vs. link-only rendering.

## Web — Defense Desk Reader

Next.js App Router. Defense desk landing page with the current brief.
Brief cards: BLUF headline → key items → citations drawer (source links).
"What changed" diff banner between today's brief and yesterday's.
Catalyst calendar (upcoming scheduled events: NDAA markup, earnings, FOMC).
Responsive; no mobile app in Cycle 1 — mobile-friendly web is sufficient.

## Web — Entity 360 Page

Per-entity page: canonical name, ticker, CIK, related programs, recent contract
awards, recent filings, insider transactions.
Data sourced from the entity graph — no external API calls at render time.
Available to Pro subscribers.

## Web — Auth (Supabase)

Email + password auth via Supabase Auth. Row-level security on all user data tables.
Free tier: read the weekly brief.
Pro tier: daily brief, PDF export, archive, entity 360 pages.

## Web — Stripe Subscriptions

Web-first reader model: subscriptions sold and managed on web (avoids app-store
commissions). Stripe Checkout for Pro subscription. Stripe webhooks update
`subscriptions` table in Supabase. Test-mode validation before going live.

## Web — Marketing and SEO

Next.js static home page: product description, sample brief, pricing, about.
Open Graph + structured data for brief pages (SEO for sector-specific searches).

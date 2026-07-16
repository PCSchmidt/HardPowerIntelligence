# GDELT via BigQuery — Adapter Plan

Status: **PROPOSED — Phase 1 validated 2026-07-16, build PARKED (demand-pulled).**
Context: DECISIONS D110 (UA) → D116 (persistent IP) → D117 (patient backoff) all failed —
GDELT's DOC 2.0 REST API blocks HPI's cloud egress IPs (GitHub Actions, Fly IAD) by
reputation. BigQuery is GDELT's **sanctioned, authenticated** bulk-access channel, which
removes the IP variable entirely.

> **Phase 1 validation result (2026-07-16) — two findings, one good one sobering.**
> Ran the go/no-go query from a reopened GCP project (`adept-watch-456712-t5`), BigQuery Studio.
> **(1) The mechanism works.** Rows returned instantly, no auth/IP error, trivial bytes — the IP
> wall is genuinely gone, and the sources are genuinely global (philstar.com/PH, arynews.tv/PK,
> nationnews.com/BB, themoscowtimes.com, dw.com/DE, itbrief.co.nz). So the breadth that RSS misses
> is real and reachable. **(2) The catch — GKG's theme taxonomy is far noisier than the DOC API's
> full-text phrase search.** `V2Themes LIKE '%TAX_MILITARY%'` matched `TAX_MILITARY_TITLE_OFFICER`,
> which fires on the *word* "officer" — so the top results were a Houston neglect case, a Memphis
> shooting, a Philippine impeachment trial, a Colorado school-budget editorial, a Catholic bishop
> profile, and a G.I. Joe movie. Almost zero investment-grade defense signal. The DOC API let us
> search the exact phrase "hypersonic missile"; GKG makes us match broad NLP category codes, and
> the precision loss is severe. Extracting on-thesis signal would need real theme-engineering
> (curated GKG code sets + entity/organization filters + probably keyword co-occurrence) with
> uncertain payoff. **Access was never the hard part; the data model is.**
>
> **Decision:** feeds (786 records/wk, 0 fail, precise because outlets are curated) remains the
> news workhorse. BigQuery's global breadth is a real but *nice-to-have* for a mostly-Western
> investment nexus, and the theme-engineering cost is non-trivial. **Park the adapter build;
> revisit only if testers specifically ask for emerging-market / non-Western coverage** (demand-
> pulled, per the phase plan). The door is proven open — reopening it later is cheap.
>
> **NOTE — table name correction:** the partitioned GKG table is `gdelt-bq.gdeltv2.gkg_partitioned`
> (has `_PARTITIONTIME`); plain `gdelt-bq.gdeltv2.gkg` is NOT partitioned and errors on that pseudo-
> column. The queries below have been corrected.

---

## 0. Reality check — is it worth it? (decide first)

With the RSS registry now at 30 on-thesis feeds (2026-07-02), the Western trade-press news
backbone is solid and rate-limit-free. GDELT's *unique* marginal value is **global /
local-language breadth** (SITREP uses it precisely for LatAm / Africa / SE Asia coverage that
RSS misses). For HPI's Defense∩AI∩Energy **investment** nexus that is "valuable breadth," not a
critical gap. So: build this if international/emerging-market signal matters; otherwise the
feeds may already be enough. This plan assumes we proceed.

---

## 1. Phase 0 — Operator GCP setup (one-time, ~15 min)

You (not the agent — it's your billing account) do this once:

1. Create/choose a GCP project (e.g. `hpi-ingest`). BigQuery API is on by default on new projects;
   if not, enable it.
2. Create a **service account** (e.g. `gdelt-bq-reader@…`) with role **`roles/bigquery.jobUser`**
   (run query jobs, billed to the project). No dataset grant needed — `gdelt-bq` is a *public*
   dataset, readable by anyone who can run a job.
3. Create a **JSON key** for that service account. This is one new secret.
4. Store it as a CI/Fly secret. Two options:
   - `GOOGLE_APPLICATION_CREDENTIALS_JSON` = the key file contents (a string secret), which the
     adapter writes to a temp file / loads at runtime; **or**
   - the raw file mounted at a path + `GOOGLE_APPLICATION_CREDENTIALS` = that path.
   Recommend the string-secret form (matches how DATABASE_URL etc. are handled).
5. **Billing guardrail (do this):** set a project-level BigQuery **billing budget/alert**, and the
   adapter sets **`maximum_bytes_billed`** on every query (Phase 2) so a runaway query fails
   instead of billing.

Access model note: we only ever *read* a public dataset and write results to Supabase — so no
row/column security, authorized views, or dataset ACLs are relevant. One read/run role, one key.

---

## 2. Phase 1 — Validation-first (prove it BEFORE building the adapter)

Do not write the adapter until a single query returns rows. A throwaway script:

```python
from google.cloud import bigquery
client = bigquery.Client()  # uses the service-account creds
sql = """
  SELECT DATE, DocumentIdentifier, SourceCommonName, V2Themes
  FROM `gdelt-bq.gdeltv2.gkg_partitioned`
  WHERE _PARTITIONTIME >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
    AND V2Themes LIKE '%TAX_MILITARY%'
  LIMIT 25
"""
job = client.query(sql, job_config=bigquery.QueryJobConfig(maximum_bytes_billed=2_000_000_000))
for row in job:
    print(row.DATE, row.SourceCommonName, row.DocumentIdentifier)
print("bytes billed:", job.total_bytes_billed)
```

Success criteria: rows return, `total_bytes_billed` is small (< ~1 GB), no auth/IP errors. This
is the go/no-go for the whole effort — it either works (BigQuery removes the IP wall) or it
doesn't, cheaply, before any adapter investment. **This is the 4th GDELT approach; treat Phase 1
as the hypothesis test, per the D110/D116/D117 track record.**

---

## 3. Phase 2 — Adapter implementation

### 3a. Execution path — a custom fetch hook (small runner change)

BigQuery is a SQL client call, not an httpx GET, so it doesn't fit `HttpFetcher`. Add one clean
extension point in `engine/ingest/runner.py`:

```python
if hasattr(adapter, "fetch_records"):
    records = await adapter.fetch_records()   # adapter owns its own I/O (BigQuery client)
else:
    ... existing HTTP fetch_json + parse path ...
```

Everything downstream (dedup, `merge_by_native_id`, embed, persist, circuit breaker) is unchanged
— the adapter just returns `list[NormalizedRecord]` like `parse()` does today. The BigQuery client
call is sync; wrap it with `asyncio.to_thread` so it doesn't block the loop.

### 3b. The query (theme-scoped, cost-guarded)

Key difference from the DOC API: the DOC API does **full-text** search; GKG does **structured
theme/entity** search. So we match on `V2Themes` (GDELT's theme taxonomy) and/or
`V2Organizations` / `AllNames`, not free-text phrases. A design task: map our Defense/AI/Energy
probes to GDELT **theme codes** (e.g. `TAX_MILITARY`, `WB_*` energy/economics themes,
`EPU_POLICY_*`, tech/AI themes) — curate a per-desk theme set the way `_PROBES` curate phrases
today. Query shape:

```sql
SELECT DATE, DocumentIdentifier, SourceCommonName, V2Themes, V2Organizations, V2Persons, V2Tone
FROM `gdelt-bq.gdeltv2.gkg_partitioned`
WHERE _PARTITIONTIME >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)  -- partition prune = cost control
  AND SourceCollectionIdentifier = 1                                       -- web news only
  AND ( <per-desk theme LIKE clauses> )
LIMIT <cap>
```

Always: partition filter (`_PARTITIONTIME`), minimal columns, `maximum_bytes_billed` cap, English
filter if needed (`V2Themes`/tone don't carry language; use `TranslationInfo` if we want
translated-only). One query per desk (3 total) keeps it simple and cheap.

### 3c. The title problem (GKG has no headline)

GKG gives URL + domain + themes + entities + tone — **no title**. Options:
- **(A) Fetch the title** — a cheap HTTP GET per URL, scrape `<title>` (article sites are NOT
  IP-blocked like GDELT; this is what SITREP does). Best reader quality; adds N small fetches +
  a scrape step. Reuse the feeds `enrich` isolation pattern (one bad fetch never aborts the run).
- **(B) Theme-derived descriptor** — no title fetch; text_chunk = "`{domain}` — themes: {top
  themes}, orgs: {top orgs}". Lighter, uglier, less reader-friendly.
Recommend **(A)** for the reader, with **(B)** as the fallback when a title fetch fails. This
keeps GDELT items at the same `scrape_gray` / `reported` tier as feeds.

### 3d. Data mapping (GKG row → NormalizedRecord)

- `source_id` = `"gdelt"` (keeps the epistemics tier + registry entry; or `"gdelt_bq"` if we want
  to distinguish — prefer keeping `"gdelt"`).
- `record_type` = `"news"`; `desk` = `[home_desk]` (from the matching theme set, D097).
- `native_id` = `DocumentIdentifier` (URL); `content_hash` = sha256(url + title).
- `structured_data` = {url, domain, title, themes, orgs, tone, seendate}.
- `text_chunk` = `f'{domain} reported: "{title}".'` (title from 3c) — mirrors the current adapter.
- `url` = DocumentIdentifier.

### 3e. Dependencies

Add `google-cloud-bigquery` to `engine/pyproject.toml` (it's a moderately heavy dep; it lands in
the CI image and, if kept, the API/worker images — check image-size impact). Regenerate `uv.lock`.

---

## 4. Phase 3 — Wire-up, teardown, rollout

- **Runs in CI** (no worker needed — BigQuery is authenticated, not IP-blocked). Re-include gdelt
  in the CI ingest (revert the D116 `--exclude gdelt`), OR keep it a distinct `gdelt_bq` source.
- **Tear down `hpi-worker`** (`fly apps destroy hpi-worker`) — D116's reason to exist is gone.
- Registry: the BigQuery adapter replaces (or sits beside) the DOC-API `GDELTAdapter`. If we keep
  both, the DOC-API one stays dormant (still 429s from CI) — cleaner to swap.
- Add `GOOGLE_APPLICATION_CREDENTIALS_JSON` to GitHub Actions secrets (+ Fly if ever needed).

## 5. Testing

- Adapter parse/mapping: unit-test GKG-row → NormalizedRecord on an inline fixture (no network),
  mirroring `test_gdelt_adapter.py` (desk routing, hash stability, title fallback).
- Query builder: assert the SQL has a `_PARTITIONTIME` filter and `maximum_bytes_billed` is set
  (cost-guard regression tests — the "$62 SELECT *" trap).
- Runner hook: `fetch_records` path returns records without touching the HTTP fetcher.
- Title fetch: isolated per-URL failure → falls back to descriptor, never aborts.

## 6. Cost & guardrails (recap)

- On-demand $6.25/TiB; **first 1 TiB/month free**; storage $0 (public dataset).
- Date-partitioned + minimal-column daily queries scan ~0.5–2 GB → ~15–60 GB/month → **$0**.
- `maximum_bytes_billed` per query + a project billing budget make a surprise bill impossible.

## 7. Open decisions for the operator

1. Proceed at all, or is the 30-feed backbone enough? (§0)
2. Title fetch (A) vs theme descriptor (B)? (§3c)
3. Keep `source_id="gdelt"` (swap the adapter) vs new `gdelt_bq` source? (§3d/4)
4. Confirm the GCP project + who owns billing (§1).

---

*When approved, this becomes a DECISIONS entry (D-TBD) and a gated build: Phase 1 validation →
Phase 2 adapter → Phase 3 rollout + worker teardown.*

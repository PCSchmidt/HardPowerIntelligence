# HPI Phase Plan — from content-complete to validated & monetized

**Status:** ADOPTED 2026-07-05 · **Current phase:** Phase A — all workstreams (A1–A5) shipped 2026-07-05 (D126/D127); **exit gate pending: 7 clean unattended days — counter reset 2026-07-15** (Defense dark two consecutive days: 7/14 citation collapse → D139, 7/15 `item_type` CheckViolation → D140; both fixed, clean-day count restarts at the next green run) · B0/B5 draft groundwork pulled forward 2026-07-09 (no-run-dependency work during the wait)
**Owner:** operator · **Companion docs:** [ARCHITECTURE.md](ARCHITECTURE.md), [SOURCES.md](SOURCES.md), [SOURCE_LANDSCAPE.md](SOURCE_LANDSCAPE.md), `../DECISIONS.md` (D125)

## Where we are (macro state, 2026-07-05)

The engine reliably publishes high-quality, cited, convergence-framed briefs across three
desks (Defense / AI / Energy) on live data. After the 7/5 fixes (D121–D124) the obvious
content defects are gone; the backend is sound (bounded 21-day hot window, durable provenance
record, bitemporal entity graph, RLS). **The product is content-complete but
validation-incomplete:** it still runs *attended*, the revenue loop is TEST-mode/dark, "Pro"
isn't defined, the entity graph doesn't surface in the UI, and no real target user reads it yet.

**The binding constraint has shifted** from "are the briefs good?" (they are) to "can anyone
rely on it unattended, does anyone want it, and does it look like a product worth paying for?"
So this plan moves from *build* mode to *harden + validate* mode.

## Governing principles

- **Gated.** Each phase has an entry gate, a measurable exit gate, and a kill/continue
  decision. Don't start the next phase's expensive work until the prior exit gate is green.
- **Optionality first.** Cheap, reversible bets before expensive irreversible ones; one hero
  surface, not a suite; keep a permanent free teaser that serves income + portfolio +
  acquisition simultaneously.
- **Two cohorts, never conflated.** Warm contacts (~20–30) are a *feedback* asset; the blind
  LinkedIn cohort is the clean *willingness-to-pay* signal. Relationship pressure contaminates
  conversion — keep the funnels separate.
- **Personas as the ranking engine.** With a thin real-feedback pool you can't A/B your way to
  Phase C priorities; synthetic personas rank the options, triangulated against the real
  conversations.
- **Success is multi-modal.** Income OR portfolio/JHU-masters OR acquisition optionality. The
  A→B→C spine is robust across all three; the *emphasis* tilts once the primary mode is fixed.

---

## PHASE A — Autonomous Reliability & Observability

**Entry:** now. **Objective:** the pipeline runs unattended and alerts you; you stop being the monitor.

- [x] **A1 — Run-health alerting.** ✅ 2026-07-05 (D126). Pure evaluator
  (`engine/engine/ops/health.py`) + `scripts/run_health.py` + a scheduled-only `health` job in
  `daily-brief.yml` that inspects `briefs` / `ingestion_runs` / `source_registry` and exits
  non-zero (→ GitHub failure email, no new infra) on silent degradation: total shutout, stuck/
  absent brief rows, failed ingest source, open circuit breaker, or a stale source. Correctly
  treats a thin-day skip (`status='failed'`) as INFO, not an alert. 16 tests.
- [x] **A2 — Output-quality canary.** ✅ 2026-07-05 (D126 item-count/faithfulness + D127). Adds a
  **confidence-mix** check (`confidence_collapsed` — a published brief with zero confirmed/reported
  items) and a **content-leak** canary (`content_leak` — catches a D118 JSON-leak regression in
  prod via `looks_like_content_leak`). Extended **2026-07-14 (D139)** with `brief_items_collapsed`:
  a `status='failed'` brief that has a headline but **0 items** (synthesis produced a full brief the
  citation gate stripped to nothing — the 7/14 Defense dark, where a near-miss `[CITE:N]` format
  deleted every sentence) now **warns/pages**, distinct from a genuine thin-day INFO. Fix also made
  citation parsing tolerant (`normalize_citations`) so the drift can't dark a desk in the first place.
- [x] **A3 — Daily self-digest.** ✅ 2026-07-05 (D127). `HealthReport.digest` — always-shown run
  picture: per-desk published item count + attribution mix, per-source ingest volume, and the
  run's LLM token/cost total. Emitted to stdout + the GitHub step summary alongside the anomalies.
- [x] **A4 — Cost observability.** ✅ 2026-07-05 (D127). Process-level token accumulator in the LLM
  client (`usage_snapshot`); `run_brief.py` prints per-desk usage and stamps it onto the brief
  metadata; the health check aggregates it into the digest and warns (`cost_anomaly`) above
  `llm_run_token_budget`. *Deferred (revisit after runs):* anomaly detection vs. a rolling baseline
  (current guard is an absolute per-run ceiling).
- [x] **A5 — Dead-man's switch.** ✅ 2026-07-05 (D126). Realized as the `no_brief_published`
  *critical* in the A1 health check — a total publish shutout goes red regardless of exit codes.

**Exit gate:** 7 consecutive unattended days where every degradation surfaced an alert *before*
you noticed manually, and you've stopped opening the PDFs to check health. Cost/run known and bounded.
**Optionality:** pure asset across all success modes; cleanest engineering-craft showcase (observability).
**Effort:** small–medium; mostly wiring existing telemetry.

---

## PHASE B — Validation: Feedback + Willingness-to-Pay

**Entry:** A green. **Objective:** a ranked, evidence-backed Phase C option list + an initial commercial read.

- [ ] **B0 — Synthetic persona framework (do first; it's the ranking engine).** See the persona
  table below. The Phase C option list *is* the union of the surfaces it points to, ranked by
  which personas the real 8–10 conversations most resemble.
  **Drafted 2026-07-09 → [PERSONAS.md](PERSONAS.md)** — the 5 personas as interview-ready instruments
  (JTBD, aha, kill-signal, probes) + a ranking worksheet. Still `[ ]`: the exit gate is *validation
  against the real conversations*, not the draft.
- [ ] **B1 — Instrumentation (light, privacy-respecting).** Page views per desk, wire clicks,
  return visits, trial start/end, plus a one-click in-product feedback affordance.
- [ ] **B2 — Warm cohort (~20–30) = "Founding Readers."** Permanent/extended comp in exchange
  for a 15-min structured interview (script from B0). Goal = qualitative depth + persona
  validation, explicitly NOT a conversion metric.
- [ ] **B3 — Cold cohort (blind LinkedIn) = clean commercial signal.** Standard 30-day trial, no
  relationship. Their trial-start → engagement → conversion is the real willingness-to-pay read.
  Funnel instrumented separately from B2.
- [ ] **B4 — Public teaser (zero-budget top-of-funnel).** One representative brief / "yesterday's
  convergence read," shareable + SEO-able. Doubles as founder-led distribution and a
  portfolio/acquisition artifact; a permanent free surface serving all three success modes.
- [ ] **B5 — Design *discovery* (low-fidelity, disposable).** Mockup the top 2–3 persona-ranked
  Phase-C surfaces (`MOCKUPS.md` / Figma / even ASCII) and show them in the interviews — a concrete
  mockup gets far better feedback than an abstract "convergence graph." These are throwaway
  validation instruments, NOT committed spec. Committed design *spec* is deferred to Phase C entry
  (see the note under C1 and `FRONTEND_SPEC.md` §9 Tier 3–4).
  **Drafted 2026-07-09 → [MOCKUPS.md](MOCKUPS.md)** — a low-fi wireframe deck of the 3 archetypes
  (Convergence Map / Capital & Catalyst Dashboard / Narrative Homepage), built ahead during the
  Phase-A wait. Still `[ ]`: these carry no weight until shown in the real conversations (B2/B3).

### Target personas (Phase C drivers)

| Persona | Job-to-be-done | Pays for | Phase C surface it drives |
|---|---|---|---|
| Thematic hedge-fund analyst | Spot cross-sector inflections before consensus (AI power demand → nuclear/utilities) | Convergence signal + provenance to defend a thesis internally | Convergence graph + entity timeline |
| Energy/infra PE / project-finance associate | Track capital formation, awards, FIDs, policy affecting deployment | Structured capital-flow + regulatory tracking | Capital-flow Sankey + asset/geo map + follow-alerts |
| Corp-dev / strategy at a prime or energy major | Competitive intel, M&A radar, supply-chain moves | Entity-centric monitoring of competitors/targets | Entity360 + competitor watch + alerts |
| Policy / think-tank / gov-BD researcher | Authoritative, cited tracking of programs/appropriations | Provenance + primary-source linkage | Provenance-forward view + policy timeline + catalyst calendar |
| Generalist macro / family-office investor | A trustworthy daily read on the hard-power complex without drowning | The curated convergence narrative + "so what" | Polished convergence homepage + dashboard tiles (least graph, most narrative) |

**Exit gate:** personas validated/adjusted against ≥8–10 real conversations; a ranked Phase C
list with evidence; baseline warm-cohort return rate + an initial cold-cohort funnel.
**Decision gate:** enough pull to justify the Phase C build — **continue / pivot-the-surface / kill**.
**Effort:** mostly outreach + light instrumentation; low code.

---

## PHASE C — Differentiated Surface (Pro anchor) + Trial Economics

**Entry:** B decision-gate = "go." **Objective:** one hero differentiator behind a trial, with a measured conversion read.

- [ ] **C0 — Payments/trial go-live.** Flip Lemon Squeezy live; trial mechanics: grant on signup
  → auto-revoke to free at day 30 without conversion → permanent "Founding Reader" comp for the
  warm cohort. Define Pro's boundary: **free = daily briefs + wire (as today); Pro = the
  differentiated surface + retention features.**
- [ ] **C1 — Build ONE hero differentiator** (top-ranked surface from B — likely the convergence
  view). Minimum that's genuinely *wow + substance*, provenance-preserving, mobile-degrading.
  The trial carrot. Resist building the whole viz suite.
- [ ] **C2 — Conversion instrumentation.** Trial→paid %, which surface converters used, where
  non-converters dropped.

**Trial length = 30 days (decided).** HPI is a *daily* product: the trial must form a daily-read
habit AND let cross-day convergence value accrue. 2 weeks is too short for both; 90 days delays
the revenue signal a full quarter and kills urgency. 30 days does both and returns a conversion
read within a quarter. Warm cohort = permanent founding comp (they pay in feedback).

**Exit gate:** trial mechanics work end-to-end (grant→revoke→convert); a measured trial→paid %
on the *cold* cohort (directional even at small N); hero surface used by a majority of trial users.
**Decision gate:** conversion viable → **expand (C2/D) / pivot pricing or surface / hold**.
**Effort:** medium–large (viz + payments live + trial mechanics).

---

## PHASE D — Depth & Retention (demand-pulled, steady-state)

**Entry:** C shows a viable conversion signal. Coverage sources (EIA/NRC, DoD contracts, FERC,
Congress — see [SOURCE_LANDSCAPE.md](SOURCE_LANDSCAPE.md)), entity-level convergence, delivery
channels (email digest, entity-follow alerts — the `follows` table already exists and is unused),
saved-search "desk radar." Prioritized by what converters/personas actually pulled toward. No
fixed exit — this is the operate/grow loop.

---

## Marketing posture (woven through, not a phase)

- **Zero-to-thin spend until Phase C yields a conversion %.** Founder-led/organic only: the B4
  teaser, operator posting convergence reads on LinkedIn/X (free, doubles as portfolio), warm
  network as seed.
- **Hard spend gate:** do NOT spend acquisition dollars until cold-cohort conversion % is known —
  else you're buying users into a leaky bucket. When you do, start with a tiny test budget against
  the known funnel.

---

## Sequence & decision gates at a glance

```
A (reliability) ──exit: 7 unattended days──▶ B (validate)
B ──gate: enough pull?──▶ C (hero surface + 30-day trial)
C ──gate: conversion viable?──▶ D (depth/retention) + first paid-marketing test
        │                        │
        └── pivot surface        └── pivot pricing / hold
```

**Where optionality is banked:** A is a universal asset; the B4 teaser is a permanent free
surface serving income+portfolio+acquisition; two-cohort design keeps the commercial read clean;
C builds *one* hero (not a suite); trial-gating learns willingness-to-pay without locking a pricing
model; paid spend stays optional until it's provably multiplicative.

## Open input that sharpens emphasis

Which success mode is **primary right now** — near-term income, the JHU-masters/portfolio artifact,
or acquisition optionality? Income → compress toward C-as-conversion. Portfolio → deepen A's
observability + C polish. Acquisition → the working+differentiated+used product (A+B+C) carrying the
provenance+graph moat is the story. The sequence is unchanged; only the emphasis tilts.

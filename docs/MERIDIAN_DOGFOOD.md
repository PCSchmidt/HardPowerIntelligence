# Meridian Dogfood Findings — Memory subsystem

Hard Power Intelligence is a dogfooding exercise for [Meridian](https://github.com/PCSchmidt/meridian).
This file logs findings about Meridian surfaced by using it on a real project, so they can be
ported back to the framework. Scope so far: the **three-tier memory subsystem**
(`.meridian/memory/` — `semantic.json`, `episodic.jsonl`, `corrections.jsonl`).

Exercised 2026-06-15 (session `6a2fe7f5`): started a session, backfilled 7 episodic events,
wrote 4 semantic patterns, validated both against `memory-schema.json`, ran `memory-doctor`.

---

## What works (keep)

- **Validation + doctor are solid.** `validate-memory.sh` (jq-based field checks, no heavy
  deps) and `memory-doctor.sh` handled both the empty state (graceful "will be created") and
  the populated state (validated 4 patterns / 7 events, flagged the 1 error event, warned on
  LOW-confidence patterns). The doctor also normalized/deduped `semantic.json` on its pass.
- **`write-reflexion.sh` and `log-event.sh`** are clean, write-ahead-validated writers for
  their tiers.

## Findings (port to Meridian)

### F1 — `corrections` tier is hard-wired to hour estimation *(highest impact)*
`corrections.jsonl` *requires* `predicted_hours` / `actual_hours` / `delta_ratio`, and
`write-reflexion.sh` takes `--predicted/--actual`. Semantic patterns in the examples are time
multipliers ("frontend >8 components → 1.5×"). This assumes a `VERSION_ROADMAP.md` (hour
estimates) → `TIMELOG.md` (actuals) → reflexion workflow. **HPI runs gate-by-gate with no hour
estimates**, so the corrections tier had no inputs and stayed empty — i.e. the schema encodes a
workflow this real project doesn't follow.
**Fork:** (i) projects adopt per-gate hour estimates so the loop has data, or (ii) broaden
`corrections` to support **non-time reflexions** — `root_cause` / `action_next` *without*
hours (e.g. "predicted HS256 auth; actual ES256 → 401s; action: smoke-test real cloud auth").
**Recommendation: (ii).** The technical-reflexion form is the more broadly useful kind and is
what HPI actually generates; keep hours optional for projects that estimate.

### F2 — `episodic.jsonl` is schema-without-writer
There is a schema, a doctor, and skill references for episodic memory, but **no producer
script emits episodic events.** `session.sh start` logs to `telemetry.jsonl` (via
`log-event.sh`), not to `episodic.jsonl`; `write-reflexion.sh` writes `corrections.jsonl`.
Nothing writes the episodic tier — it had to be hand-written to dogfood it.
**Recommendation:** add a `log-episodic.sh` (or extend `log-event.sh` to dual-write) wired to
hooks for `session_start` / `gate_passed` / `gate_blocked` / `feature_complete` / `stop_event`,
so episodic memory populates automatically the way telemetry does.

### F3 — session lifecycle isn't auto-started
The installed `session.json` had **no `session_id`** (just `project` + `installed_at`);
`session.sh start` was never invoked at real session starts, so even telemetry `session_start`
events were missing until run manually this session.
**Recommendation:** the `SessionStart` hook should call `session.sh start` so every session
gets an id and a logged start event without manual action.

### F4 — semantic patterns can't reach HIGH confidence from one project
By design, a fresh pattern is `confidence: LOW` (`validated_count: 1`) and only matures to
MEDIUM/HIGH via `global-memory-sync.sh` across multiple projects. Correct, but it means a
**solo operator with few projects** accumulates only LOW-confidence patterns. Worth noting; a
possible mitigation is allowing within-project re-validation to bump confidence, or documenting
that HIGH confidence requires N distinct `source_projects`.

---

## HPI's stance (dogfood decision)

For now HPI **does** exercise `semantic.json` (4 patterns, ready to `/memory sync push` to the
global store) and `episodic.jsonl` (backfilled). It does **not** force the `corrections` tier
with fabricated hours — that tier stays empty pending the F1 fork. DECISIONS.md remains HPI's
primary durable decision record; the Meridian memory tiers are exercised alongside it to test
the framework, not to replace it.

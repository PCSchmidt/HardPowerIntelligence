# Talking Points — Prep for Explaining HPI Live

*This is for you, not for sharing. Pair it with [EXPLAINER.md](EXPLAINER.md). It's a
rehearsal doc — answers to the questions an interviewer will actually ask, keyed back to
the decision/commit that backs each answer so you can go deeper on demand.*

---

### "Walk me through what happens when a brief actually generates."

A GitHub Actions cron job fires at 06:00 UTC. It runs the ingestion adapters (one per
data source — EDGAR, USAspending, NRC, arXiv, GDELT, RSS feeds), each of which does a
network fetch, then a *pure* parse step that turns raw responses into normalized records
with entity mentions and vector embeddings. Entity resolution runs next: each mention
gets matched to a canonical entity through a cascade — exact crosswalk lookup first
(ticker/CIK/LEI/UEI), then fuzzy/semantic candidate matching, then an LLM disambiguation
call only if the cheap tiers didn't resolve it confidently. Once entities are resolved,
each of the three desks (Defense/AI/Energy) runs brief generation in parallel: a
materiality score filters which candidate events are even worth spending an LLM call on,
retrieval pulls both hard facts from the entity graph and supporting text passages from
pgvector, an LLM synthesizes the brief with inline `[CITE:N]` markers, and a second LLM
call checks every claim for entailment against its citation before anything publishes.
*Reference: `docs/ARCHITECTURE.md`, DECISIONS.md D028–D041.*

### "Why LiteLLM instead of calling provider SDKs directly?"

LiteLLM gave a single interface across OpenRouter and Fireworks so the 5-role model
waterfall (extraction/disambiguation/synthesis/eval/fallback) could swap providers and
models per role without rewriting call sites. But it wasn't a free abstraction — its
built-in `fallbacks=` mechanism turned out to collapse distinct error types into one
untyped exception, which silently skipped the last-resort fallback exactly when it
mattered (a real production outage exposed this). The fix was to walk the provider chain
manually instead of trusting the library's fallback logic. That's a good example to give
if asked "when do you trust a library vs. write it yourself" — trust it for the
interface, verify the behavior you depend on, especially failure paths.
*Reference: CHANGELOG.md D158.*

### "What would you do differently if you started over?"

Two honest answers: (1) the faithfulness threshold started as a hard publish gate and
had to be walked back to a confidence label once real output showed it was suppressing
true information that was just thinly cited — that's a design choice I'd try to reach
faster by testing on real data earlier rather than deciding the threshold policy
up-front. (2) the original plan was a persistent worker process (`procrastinate` on
Fly.io) for ingestion scheduling; it got retired because GDELT's API blocks Fly's IP
ranges, so ingestion moved to GitHub Actions cron instead — a reminder that external
dependency constraints you don't control can outweigh an otherwise-good architecture
choice, and it's worth spiking against the flakiest external dependency earlier.
*Reference: DECISIONS.md D098/D099; D004 vs. the worker retirement noted in CHANGELOG.*

### "How do you know the entity resolution actually works?"

It's checked against a golden evaluation set with a measured precision/recall, not just
spot-checked by eye — `scripts/eval_resolver.py` runs this. That's the same pattern used
for the brief-generation faithfulness score: don't ship a nondeterministic component
without a repeatable eval you re-run before any change that could regress it (e.g. a
model swap requires beating the last-30-briefs baseline first).
*Reference: DECISIONS.md D027, D091–D096; EVAL_BASELINE.md.*

### "What's the actual cost to run this, and how did you control it?"

The 5-role model waterfall (cheap models for high-volume roles like extraction, a
stronger model only for synthesis and eval) brought per-brief cost down roughly 4x versus
using one frontier model everywhere. On top of that, after the July outage work, a
per-run circuit breaker (`llm_run_budget_usd`, ~$3 ceiling) caps worst-case spend from a
runaway loop or glitch, independent of the daily/monthly soft targets — because those
soft targets were "defined but never enforced" until this was added.
*Reference: DECISIONS.md D006; CHANGELOG.md D159.*

### "Tell me about a bug you found and fixed that mattered."

The paywall could be bypassed by querying Supabase's PostgREST endpoint directly,
skipping the FastAPI layer that was supposed to be the only path to gated data — found
during a structured security review, not by accident. Fixed with a Row-Level-Security
migration that makes the database itself enforce the access boundary, so it doesn't
depend on every client going through the API correctly. That's the version of "defense
in depth" I'd cite if asked about security posture: the API being the intended path isn't
enough if the database allows direct access.
*Reference: SECURITY_AUDIT.md.*

### "Is this thing making money / does anyone use it?"

Be direct: no. It's live, it runs unattended, it publishes real daily briefs — but it's
pre-revenue and pre-subscriber. Payments are fully wired (Lemon Squeezy, webhook-verified)
but deliberately not turned on while distribution/validation is still ahead. This is a
demonstrated production system, not a validated business, and framing it that way is more
credible than overselling traction that doesn't exist yet.

### "Did you build this alone?"

Yes — solo, over about 7 weeks part-time alongside a full-time ML Engineer role, using
Claude Code as a coding collaborator throughout. Be ready to say plainly what that meant
in practice: you made the architecture and tradeoff decisions (the DECISIONS.md log is
the paper trail), and used LLM tooling to accelerate implementation — not to make
decisions for you. If asked to prove that, the outage-response arc (D155–D159) is the
best evidence: it required diagnosing a live failure, forming a hypothesis, and verifying
a fix under real failure conditions — judgment calls, not autocomplete.

---

## Gaps to close before you rely on this in an interview

- If asked for hard numbers (actual $/brief, actual latency, actual infra spend), the
  docs give *targets*, not audited actuals — pull real numbers from your billing
  dashboards / Sentry / Fly.io metrics before quoting a number you'd be asked to defend.
- If asked about legal/compliance review of the "publisher not advisor" posture, the docs
  flag it as "not legal advice, get real review" — confirm whether that ever happened
  before claiming a compliance posture as settled.

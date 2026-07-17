# Tester recruiting worksheet (B2 warm cohort)

**Fill this in.** It's the operational front-end of Phase B: map the real people you'd invite to
the five personas, track each from invite → signup → interview, then score resemblance into the
ranking worksheet in [PERSONAS.md](PERSONAS.md). Companion: [TESTER_ONBOARDING.md](TESTER_ONBOARDING.md)
(the mechanics — signup link, comp grants, limits) and [PERSONAS.md](PERSONAS.md) (the personas +
interview probes + the ranking engine this feeds).

---

## Persona quick-reference (who to look for)

| # | One-liner | Recruit if they… | Kill-signal to listen for | Votes |
|---|---|---|---|---|
| **P1** | Thematic hedge-fund analyst | make cross-sector calls before consensus, cover AI-power→nuclear/grid | "I already saw this on Bloomberg/The Diff" | A — Convergence Map |
| **P2** | Energy/infra-PE, project finance | track capital formation — awards, FIDs, financings | "projections dressed as committed capital" | B — Capital & Catalyst |
| **P3** | Corp-dev / strategy at a prime or major | run competitive intel / M&A radar on named companies | "coverage gaps on *my* entities; alerts on noise" | A — Convergence Map |
| **P4** | Policy / think-tank / gov-BD | need authoritative, cited program & appropriations tracking | "one uncited claim is disqualifying" | B — Capital & Catalyst |
| **P5** | Generalist / family-office / exec | want one trustworthy daily read with the "so what" | "feels like homework; no better than a free newsletter" | C — Narrative Homepage |

Full JTBD, aha moments, and the three interview probes per persona live in [PERSONAS.md](PERSONAS.md).

---

## The recruit list (fill in)

Aim for **coverage across personas, not headcount** — five people spread P1–P5 teaches more than
twenty P5s. Target ~20–30 total, but the *spread* matters more than the number.

| Name | Persona (P1–P5) | How you know them | Wave | Invited | Signed up | Comp'd | Interviewed | Notes |
|------|-----------------|-------------------|------|:-------:|:---------:|:------:|:-----------:|-------|
|      |                 |                   |      |    ☐    |     ☐     |   ☐    |      ☐      |       |
|      |                 |                   |      |    ☐    |     ☐     |   ☐    |      ☐      |       |
|      |                 |                   |      |    ☐    |     ☐     |   ☐    |      ☐      |       |
|      |                 |                   |      |    ☐    |     ☐     |   ☐    |      ☐      |       |
|      |                 |                   |      |    ☐    |     ☐     |   ☐    |      ☐      |       |
|      |                 |                   |      |    ☐    |     ☐     |   ☐    |      ☐      |       |
|      |                 |                   |      |    ☐    |     ☐     |   ☐    |      ☐      |       |
|      |                 |                   |      |    ☐    |     ☐     |   ☐    |      ☐      |       |

### Coverage tracker (tally as you fill the list)

```
P1 hedge-fund : ____     P2 infra-PE : ____     P3 corp-dev : ____
P4 policy     : ____     P5 generalist: ____
Gap to fill (which persona has zero?): ______________________________
```

---

## Per-person workflow

1. **Invite** → send them **https://hardpowerintel.com/signup** (open signup, no code). A short
   personal note beats a form: what it is, why you thought of *them*, one line asking for 15 minutes.
2. **They sign up** → they get the branded confirmation email, click it, land on the Defense desk.
3. **Grant comp** (optional, for "Founding Reader" status):
   `python scripts/grant_comp.py --email them@example.com`
4. **Let them use it a few days** — behavioral data (PostHog `desk_viewed`, `item_sources_opened`,
   `wire_item_clicked`, and for the graph `convergence_graph_viewed` / `convergence_node_clicked`)
   accrues on its own. Note whether they came back unprompted, and whether they *clicked through* the
   graph (used) vs merely opened it (admired) — see the demo flow in [TESTER_ONBOARDING.md](TESTER_ONBOARDING.md).
5. **Interview, 15 min**, using that persona's probes from [PERSONAS.md](PERSONAS.md).
6. **Score resemblance (0–3 per persona)** into the ranking worksheet in PERSONAS.md — that's the
   output that decides the Phase-C hero surface.

---

## Two disciplines that decide whether this is worth doing

**Warm = feedback asset, NOT willingness-to-pay.** Everyone on this list knows you, so they'll be
encouraging. That tells you which surfaces *resonate*; it does **not** tell you anyone will pay
$19.99/mo. Willingness-to-pay comes only from the cold cohort (B3), which is blocked until payments
ship. Keep the two reads in separate buckets from conversation one — a contaminated read feels
exactly like traction.

**Ask what they DID, not what they WANT.** Accomplished people give fluent, convincing feature
roadmaps for a product they've used for six minutes — they're designing, not reporting, and the
fluency makes it *more* misleading. Anchor every conversation on behavior:

- *What did you actually read? What did you skip?*
- *What would you have missed today if this hadn't arrived?*
- *Where did you stop trusting it?*
- *Would you have noticed if it hadn't shown up tomorrow?*

Collect their feature ideas — but log them as **symptoms of an unmet job**, not specifications.
The kill-signals above matter more than polite validation: a persona disconfirmed is worth more
than a persona nodded-along-with.

---

## Recommended rollout (waves, not a blast)

- **Wave 0 — pilot (3–5 people, one per persona if you can):** validates the whole flow with real
  users — email lands, confirmation works, events fire — before you spend the rest of your list.
  If something's broken, you find it at 3 people, not 25.
- **Wave 1 — the rest of the batch:** once Wave 0 confirms the flow is clean.
- Interview on a rolling basis as people accrue a few days of use; you don't need all interviews
  before you start scoring.

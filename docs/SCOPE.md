# Scope

What Hard Power Intelligence will and will not be, by build cycle. Scope boundaries
here are deliberate: they are the line the build is held to, and the line a drift
sensor guards against scope creep.

---

## The three desks

HPI organizes everything around three sector "desks" at the convergence of strategic
power:

| Desk | Coverage |
|------|----------|
| **Defense** | Drones & autonomy, space, directed energy, EW, the defense-industrial base; contract awards, budgets, FMS |
| **Energy** | Nuclear (incl. SMRs), alternatives, the grid, R&D, energy-security/dominance trends |
| **AI Infrastructure** | Chips, data centers, hyperscaler capex, power demand, interconnection queues |

Cross-cutting layers: **Macro** (rates, inflation, policy) and **Smart Money** (insider
+ institutional + congressional flow).

---

## Cycle 1 — In scope

**One vertical deep: the Defense desk, web-only.**

| Area | Cycle 1 includes |
|------|------------------|
| Desk | **Defense only** |
| Platform | **Web only** (Next.js) — no app stores |
| Brief | Daily cited BLUF Defense brief; "what changed" diff; PDF export |
| Engine | Entity-resolution graph + scheduler + 5–8 Tier-0 free adapters |
| Quality | Citation-faithfulness eval harness meeting a defined target |
| UI | Defense desk, citation drawer, catalyst calendar, entity 360 page |
| Accounts | Auth + free→Pro subscription via Lemon Squeezy (reader model) |
| Data | Free public Tier-0 sources + one market-data vendor (FMP ~$19/mo) |

**Cycle 1 acceptance criteria:**
1. A cited daily Defense brief renders on web, every claim linked to a source.
2. The eval harness reports citation-faithfulness at or above target before publish.
3. A user can subscribe (Lemon Squeezy test → live) and read gated content.
4. Infrastructure runs within the ~$80–230/mo envelope.

---

## Out of scope for Cycle 1 (explicitly deferred)

These are good and planned — just **not now**. Naming them protects the cycle:

- **Energy and AI-Infrastructure desks** (Cycle 2).
- **Mobile reader app** + Apple App Store / Google Play submission (Cycle 2).
- **Second-order `SUPPLIES` supply-chain synthesis** (Cycle 2).
- **Personalized portfolio / Plaid integration** — out of scope indefinitely
  (breaks the cost model and the non-advice posture).
- **Buy/sell recommendations, trading signals, robo-advisor** — never.
- **Paid/enterprise data** (Bloomberg/AlphaSense/FactSet, real-time feeds, satellite,
  alt-data) — deferred until revenue funds it.
- **Creator/RIA/Team tiers** — after the base product has paying users.

---

## Cycle 2 — Planned next

- Add the **Energy** and **AI-Infrastructure** desks.
- Ship the **Expo reader app**; reintroduce the app-store submission gates
  (reader-app model, web-billed subscriptions, Google's 20-tester closed-test gate).
- **Second-order supply-chain** synthesis via `SUPPLIES`/`PARENT_OF` edges.
- Revenue-funded data adds (analyst ratings/estimates, transcripts at scale,
  uranium spot, select alt-data).

---

## Monetization scope

- **Web-first Lemon Squeezy subscriptions** (Merchant of Record; reader-app model —
  sold/managed on web to avoid app-store commissions).
- Tiers: **Free** (daily brief, current day only) → **Pro** ($19/mo or $179/yr —
  90-day archive, entity 360, PDF export, follows) → deep-dive reports in later cycles (D019).
- Deferred: Creator/RIA/Team tiers.

---

## Success criteria (beyond Cycle 1)

| Dimension | Target |
|-----------|--------|
| Trust | Published citation-faithfulness score; zero uncited claims |
| Habit | Daily "what changed" that subscribers open repeatedly |
| Cost | Stay inside the low monthly run-cost envelope |
| Profitability | Break-even at a small number of subscribers |
| Differentiation | Coverage + provenance no commodity tool matches for these sectors |

---

## Governance note

Scope is enforced through Meridian's gate model. Cycle boundaries map to gate cycles;
the Cycle-2 deferrals above are the boundary the drift sensor is configured to guard.
See [`.meridian/gates.yaml`](../.meridian/gates.yaml) once installed.

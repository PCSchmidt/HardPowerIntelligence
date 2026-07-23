# Hard Power Intelligence — Demo Guide

A scripted 5–7 minute walk-through of the live product for a demo, screenshare,
investor conversation, or technical interview. HPI is live at
**[hardpowerintel.com](https://hardpowerintel.com/)** and today's briefings are
free to read — no account required — so the whole demo runs in a browser.

---

## Demo Objective

Demonstrate:

- **The product thesis** — one intelligence engine tracking the convergence of three build-outs: AI infrastructure, defense, and energy.
- **Source-attributed, confidence-graded briefings** — every claim links to a primary record and is labeled by how certain it is.
- **The moat made visible** — an entity-resolution graph that connects a raw event to the investable company behind it, and surfaces companies sitting at the intersection of two or more sectors.
- **A real production system** — live end-to-end (web → API → database), publishing daily from live data on a cron.

---

## Quick View (No Setup Required)

Everything is live in a browser — nothing to install:

- **Home / today's briefs:** [hardpowerintel.com](https://hardpowerintel.com/)
- **A live cited brief (Defense desk):** [hardpowerintel.com/desk/defense](https://hardpowerintel.com/desk/defense)
- **The interactive Convergence Graph:** [hardpowerintel.com/graph](https://hardpowerintel.com/graph)
- **The full thesis:** [docs/PHILOSOPHY.md](docs/PHILOSOPHY.md)
- **System design:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

> **Note:** Paid subscriptions are coming soon — the checkout code is built but
> not yet wired to a payment processor — so for now every brief on the site is
> open to read.

---

## Demo Script

### 1. The one-sentence pitch (0:00 – 0:45)

Open [hardpowerintel.com](https://hardpowerintel.com/).

**Say:** "Hard Power Intelligence is an intelligence officer for the industries
rebuilding national power. It reads the boring-but-important public record — defense
contract awards, SEC filings, nuclear licensing, chip and data-center news — every
day across three sectors, and turns it into a short briefing that leads with the
point, shows its sources, and connects each event to the companies it affects. The
name is a triple play on *power*: hard power is defense, electrical power is energy,
compute power is AI — and increasingly those three overlap."

### 2. Read a brief — Bottom Line Up Front (0:45 – 2:15)

Open [the Defense desk](https://hardpowerintel.com/desk/defense).

**Say:** "Each desk publishes a BLUF brief — Bottom Line Up Front, borrowed from
military reporting. You get the takeaway first, then an at-a-glance ledger, then the
cited facts." Scroll through the structure:

- **BLUF** — the conclusion, up top.
- **At-a-glance ledger** — the day's items in a scannable list.
- **Cited facts** — each item pairs the fact with a source link and a confidence label.

**Say:** "This is the trust model. Every item shows its basis — confirmed primary
record, reported news, HPI analysis, or clearly-labeled speculation — so you always
know whether you're reading a hard fact or an interpretation. Click any source and
it takes you to the original document. Nothing has to be taken on faith."

### 3. The analyst layer — read and watch (2:15 – 3:15)

Expand an item's **"Analysis — HPI interpretation"** drill-down.

**Say:** "Under each cited fact is a grounded interpretation: a *read* — why it's
material — and a *watch* — the forward catalyst to track. This is held to a
grounding gate: if the analysis can't be supported, it's regenerated or omitted
rather than fabricated. It adds judgment without breaking the trust model."

### 4. The moat — the Convergence Graph (3:15 – 5:00)

Open [the Convergence Graph](https://hardpowerintel.com/graph).

**Say:** "This is the core asset — the transmission layer. Behind every brief is an
entity-resolution graph that links a raw event to the investable security. A contract
to 'Lockheed Martin Rotary and Mission Systems' resolves to the ticker LMT, its
segment, its program, and the second-order suppliers most tools miss."

Point out the visual:
- **Nodes** are companies; those recurring together across sectors cluster.
- **Gold nodes** are convergence entities — a single company appearing on two or more desks (AI ∩ Defense ∩ Energy).
- **Gradient edges** blend the two sectors a connection bridges; hovering an edge surfaces the **cited stories behind the link**.
- Toggle the **federal-funding overlay** to see award edges from USAspending.

**Say:** "The resolver is held to an accuracy gate — precision and recall of 1.0 on
a golden set, zero false links — because a wrong link is worse than no link. A
company sitting at the intersection of defense and energy, or AI and defense, is the
signal this whole product is built to surface."

### 5. It's a real, live system (5:00 – 6:00)

**Say:** "This isn't a mockup. It's live end-to-end — a Next.js reader on Vercel, a
FastAPI engine, a Supabase Postgres database with pgvector. A cron runs at 6am UTC:
ingest fresh data once, publish all three desks. Four live source adapters feed it —
USAspending, SEC EDGAR, arXiv, and NRC licensing — and reliability gates keep daily
publishing trustworthy, including a novelty check so tomorrow's brief isn't a
re-summary of today's."

### 6. Close — what it is and isn't (6:00 – 6:45)

**Say:** "HPI produces informational research, not investment advice, and it's not a
stock-picker. It tells you what happened and why it might matter — the judgment about
what to do with that stays with the reader. What's next is turning on subscriptions,
deepening the AI and Energy desks, and shipping the flagship cross-domain convergence
brief. And the whole thing was built under Meridian, an agent-harness framework I
also wrote — HPI was its main dogfooding project."

---

## Talking Points for Q&A

- **"How is this different from a news aggregator?"** Aggregators summarize headlines.
  HPI resolves each event to the investable entity, grades its confidence, links its
  source, and detects what *changed* — the entity graph is the differentiator.
- **"How do you handle hallucination?"** An eval gate flags fabricated specifics
  before publish and grades each item's attribution. Grounding is transparency the
  reader can check, not a filter — and analysis that can't be grounded is dropped.
- **"Is it expensive to run?"** No — the free primary-source backbone plus cheap
  model routing puts brief generation around $0.09 each; infrastructure runs roughly
  $80–230/month, designed to break even at a small number of subscribers.
- **"Where's payment?"** Built but not yet live — the checkout and webhook code
  exists; it needs account credentials and config, not more engineering.

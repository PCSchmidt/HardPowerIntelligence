# Tester onboarding — how to put HPI in front of a real reader

**Status:** live as of 2026-07-15 (D141 — before this date the signup funnel was one-way and
recovery didn't exist). **Companion docs:** [PERSONAS.md](PERSONAS.md) (who to recruit and what to
ask), [PHASE_PLAN.md](PHASE_PLAN.md) (why the two cohorts must stay separate),
[AUTH_EMAIL_TEMPLATES.md](AUTH_EMAIL_TEMPLATES.md).

---

## The short version

Send them **<https://hardpowerintel.com/signup>**. That's the whole mechanism.

Signup is open — no invite codes, no allowlist, no action required from you. A stranger with the
link has a working account in about sixty seconds.

## What the reader experiences

1. Enters an email and password at `/signup` (minimum 8 characters).
2. Sees *"Check your email to confirm your account."*
3. Receives a mail from **Hard Power Intelligence** `<noreply@hardpowerintel.com>`.
4. Clicks it → `/auth/callback` exchanges the code for a session → lands on the **Defense desk**,
   reading today's brief.

Steps 3–4 were broken for every user before 2026-07-15. `kwarlick@gmail.com` signed up on
2026-06-18 and never got in. If a tester says "I never got the email," that's a real failure mode
with a real precedent — check Resend → Emails before assuming they mistyped.

## What they get

The free/Pro line is exactly **"today is free, history is Pro."** That is the *only* difference in
the codebase (`api/app/routers/briefs.py`).

| | Free (any signup) | Pro |
|---|---|---|
| Today's brief, all three desks — BLUF, items, citations, analysis, convergence | ✅ complete | ✅ |
| The wire (overflow items) | ✅ | ✅ |
| Entity pages, calendar | ✅ | ✅ |
| Archive before today | ❌ `403 pro_required` | ✅ rolling 90 days |

**A free signup sees the complete product as it exists that day.** Nothing is held back or teased.
For a demo this is ideal — you're not showing a crippled version.

## Granting Pro (comp)

They must **sign up first** — a comp is a `subscriptions` row referencing `auth.users`.

```bash
python scripts/grant_comp.py --email them@example.com
python scripts/grant_comp.py --email them@example.com --until 2026-12-31
python scripts/grant_comp.py --email them@example.com --revoke
```

`resolve_tier` treats a comp identically to a paying subscriber. This is the "Founding Reader"
lever for the warm cohort (B2).

## Limits worth knowing

- **~100 signups/day** — Resend's free tier. This, not Supabase's rate limit, is the ceiling.
  Irrelevant for 30 people; relevant if a link ever goes public.
- **Nobody can buy Pro.** Lemon Squeezy is dark; upgrade surfaces read "coming soon" (D088).
  Expect **zero conversion data** from any cohort until payments go live.
- **First-contact spam risk.** `hardpowerintel.com` began sending 2026-07-15. It's SPF/DKIM/DMARC
  clean and landed in Gmail's inbox on the first try, but a new domain has no reputation. If a
  tester reports nothing arrived, have them check spam before you debug anything.

---

## The discipline that matters most

**Everyone you personally invite is the warm cohort (B2). They are a feedback asset, not a demand
signal.** [PHASE_PLAN.md](PHASE_PLAN.md) is explicit about why: relationship pressure contaminates
the commercial read. People who know you will be encouraging. That tells you which surfaces land —
it does not tell you anyone will pay $19.99/mo.

Willingness to pay comes only from **B3**: the blind cohort who owe you nothing. Keep the two reads
in separate buckets from the first conversation. This is the easiest mistake in Phase B to make and
the most expensive, because a contaminated read feels exactly like traction.

### Recruit against personas, not headcount

Aim for coverage across [PERSONAS.md](PERSONAS.md) — P1 thematic hedge-fund analyst, P2 infra-PE,
P3 corp-dev, P4 policy/think-tank, P5 generalist. Five readers across five personas teaches you
more than twenty of the same one. Each persona ships with a JTBD, an aha moment, a kill-signal, and
probe questions.

### Ask what they did, not what they want

Accomplished people give confident, articulate, well-argued feature suggestions for products they
have used for six minutes. They are designing, not reporting — and their fluency makes the output
*more* persuasive without making it more predictive.

They are reliable witnesses to their own experience. Prefer:

- *What did you actually read? What did you skip?*
- *What would you have missed today if this hadn't arrived?*
- *Where did you stop trusting it?*
- *What did you already know before you got here?*
- *Would you have noticed if it hadn't shown up tomorrow?*

over *"what features would you like?"* Collect their feature ideas anyway — but treat them as
**symptoms pointing at an unmet job**, not as specifications. "I want a chart of contract awards"
usually means "I couldn't tell what mattered" — and the chart is their guess at the fix, not the
diagnosis.

The kill-signals in PERSONAS.md exist because a persona disconfirmed is worth more than a persona
politely validated.

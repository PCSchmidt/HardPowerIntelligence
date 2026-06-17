# Frontend Specification — Hard Power Intelligence

Web reader and marketing site. Next.js App Router on Vercel. Defense desk, Cycle 1.

Gate 3 artifact. Pass `FRONTEND APPROVED` to close Gate 3 and unlock Gate 6.

---

## 1. Tech Stack (locked)

| Concern | Choice | Notes |
|---------|--------|-------|
| Framework | Next.js 14+ App Router | SSR, RSC, edge middleware |
| Styling | Tailwind CSS + shadcn/ui | D020 |
| Icons | lucide-react | Via shadcn dependency |
| Fonts | next/font | Playfair Display, Lora, Inter — D021 |
| Auth client | @supabase/ssr | NOT auth-helpers-nextjs (deprecated) |
| Mutations | TanStack Query v5 | D022 |
| Analytics | PostHog | `'use client'` provider in root layout |
| Errors | Sentry | `instrumentation.ts` |
| Payments | Lemon Squeezy (MoR) | Hosted checkout redirect/overlay; D050. Merchant of Record handles global tax |

---

## 2. Global Architecture

### Rendering rules (D022)

**Server Components** (default — no `'use client'` directive):
- All pages where content is the primary load
- Fetch from FastAPI using `FASTAPI_INTERNAL_URL` (server-to-server, no CORS)
- No loading spinners for initial paint; content arrives rendered
- SEO-ready by default

**Client Components** (`'use client'` required):
- `NavBar` — auth state, search dropdown, user menu
- `CitationsDrawer` — open/close state, filtered citation list
- `FollowButton` — optimistic mutation
- `TrialBanner` — subscription countdown
- `PasswordInput` — Eye/EyeOff toggle
- `EntitySearch` — autocomplete, keyboard navigation
- Auth forms — all form interaction
- `TimestampDisplay` — live relative time ("3 hours ago")
- `ErrorBoundary` — must be client for React error boundaries

**TanStack Query** (mutations + invalidation only):
- `POST /users/follows` and `DELETE /users/follows/{id}`
- Subscription status revalidation after Lemon Squeezy checkout `success` redirect
- Wrap in `QueryClientProvider` in root layout (client component wrapper)

### Directory structure

```
web/
  app/
    layout.tsx                    # Root layout: fonts, PostHog, QueryClient, NavBar
    page.tsx                      # / — Marketing home (static)
    desk/
      defense/
        page.tsx                  # /desk/defense — Brief reader (Server)
    brief/
      [id]/
        page.tsx                  # /brief/[id] — Archive detail (Server)
    entity/
      [id]/
        page.tsx                  # /entity/[id] — Entity 360 (Server)
    subscribe/
      page.tsx                    # /subscribe — Pricing (Server + Client CTA)
      success/
        page.tsx                  # /subscribe/success — Post-checkout (Server)
      cancel/
        page.tsx                  # /subscribe/cancel — Cancelled checkout (static)
    login/
      page.tsx                    # /login (Client)
    signup/
      page.tsx                    # /signup (Client)
    forgot-password/
      page.tsx                    # /forgot-password (Client)
    account/
      page.tsx                    # /account — Settings (Server + Client)
    admin/
      page.tsx                    # /admin — Stub (Server, is_admin gate)
  components/
    layout/                       # AppShell, NavBar, Footer, DeskLayout, Sidebar
    brief/                        # BriefHeader, BriefItem, CitationsDrawer, etc.
    entity/                       # EntitySearch, EntityHeader, FollowButton, etc.
    calendar/                     # CatalystCalendar, CalendarEventRow
    auth/                         # LoginForm, SignupForm, PasswordInput, OAuthButton
    subscription/                 # PricingTable, TrialBanner, UpgradePrompt, ArchiveLock
    common/                       # DeskBadge, ProBadge, EmptyState, ErrorBoundary, etc.
  lib/
    supabase/
      client.ts                   # Browser Supabase client (singleton)
      server.ts                   # Server Component Supabase client (cookies)
    api/
      briefs.ts                   # FastAPI fetch helpers (Server)
      entities.ts
      calendar.ts
      auth.ts
    query/
      brief-queries.ts            # TanStack Query keys + mutation fns
      entity-queries.ts
  middleware.ts                   # Supabase updateSession() on every request
```

### Next.js middleware

`middleware.ts` runs on every request except `/_next/static`, `/_next/image`, `/favicon.ico`.

Responsibilities:
1. Call `supabase.auth.updateSession()` to refresh the cookie-based session
2. Redirect unauthenticated users away from auth-required routes to `/login`
3. Redirect authenticated users away from `/login` and `/signup` to `/desk/defense`
4. Check `is_admin` claim for `/admin/*` routes; redirect to `/` if absent

Auth-required routes: `/desk/*`, `/brief/*`, `/entity/*`, `/account`
Admin-required routes: `/admin/*`
Public routes: `/`, `/subscribe/*`, `/login`, `/signup`, `/forgot-password`

---

## 3. NavBar (global)

Appears on all pages. Client Component.

**Desktop layout (lg+):**
- Left: HPI logotype (wordmark + small shield/chevron mark)
- Center: Desk tabs — `Defense` (active) | `Energy` (grayed, "Coming soon" tooltip) | `AI Infrastructure` (grayed, "Coming soon")
- Right: `EntitySearch` icon button → command palette | `UserMenu` (avatar + dropdown)

**UserMenu dropdown contents:**
- User email (truncated)
- Tier badge: `Free` / `Pro` / `Trial: N days`
- `Account settings` → `/account`
- `Upgrade to Pro` → `/subscribe` (shown only to Free and lapsed Trial users)
- `Sign out`

**Mobile layout (<lg):**
- Left: HPI logo
- Right: hamburger → full-screen sheet with desk tabs + user menu items stacked

**Trial banner integration:** Rendered inside NavBar (below the main nav bar, full-width) when `subscription.status === 'trialing'`. Single line: "Trial: N days remaining · [Upgrade now]". Disappears when Pro. See D024.

---

## 4. Page Specifications

---

### `GET /` — Marketing Home

**Auth:** Public
**Render:** Static with ISR (`revalidate: 3600`)
**FastAPI calls:** None (static content + hardcoded sample brief excerpt)

**Sections (top to bottom):**

1. **Hero** — Full-width. Headline in Playfair Display (`text-display-xl`): "Intelligence that cites its sources." Subheadline in Inter: one sentence on the product. Two CTAs: "Start 14-day free trial" (primary, navy fill) + "See a sample brief" (secondary, outlined). Background: parchment-equations backdrop (`web/public/textures/parchment-equations.png`) dimmed behind a `#FAFAF8`/navy scrim so type meets contrast targets — see DESIGN_SYSTEM.md §11 / D051.

2. **Sample Brief Preview** — Truncated, ungated excerpt of a real Defense brief item (static, hardcoded for launch). Shows: item type badge, headline, first sentence of body, one citation chip `[1]`, citation source label. Fade-out at the bottom with "Sign up to read the full brief →". Signals the product's format.

3. **Differentiators** — Three-column grid (single column on mobile). Each: icon, heading, 2-sentence description.
   - "Every claim cites its source" — citation-faithfulness eval gate
   - "Government data, synthesized" — free public sources, no paywalled feeds
   - "Defense, Energy, AI Infrastructure" — sector specificity, not generic finance news

4. **How It Works** — Three steps with connecting line: Ingest → Resolve → Synthesize. Brief icon-driven diagram. No technical jargon — subscriber-facing language.

5. **Pricing Table** — `PricingTable` component. Free vs Pro columns. 14-day trial CTA. See subscription section.

6. **Footer** — `Footer` component. Logo, tagline, links (Terms, Privacy, Contact), disclaimer ("HPI is a general publication, not investment advice."). Carries a low-opacity parchment-equations hint as a chrome accent (DESIGN_SYSTEM.md §11 / D051), persisting the motif onto authenticated pages where reading surfaces stay clean white.

**SEO:**
- `title`: "Hard Power Intelligence — Defense, Energy & AI Infrastructure Briefings"
- `description`: "Daily cited intelligence briefs for defense, energy, and AI infrastructure investors and analysts. Every claim links to its source."
- OG image: static — HPI logo + tagline on navy background
- Structured data: `Organization` schema (JSON-LD)
- `robots`: index, follow

---

### `GET /desk/defense` — Defense Desk Reader

**Auth:** Required (redirect to `/login` if unauthenticated)
**Render:** Server Component fetches brief; Client Components for drawer and trial banner
**FastAPI calls:** `GET /briefs/latest?desk=defense`, `GET /calendar?desk=defense&from=today&to=today+14d`

**Layout (D023):**
- Mobile/tablet (<lg): single column, full-width
- Desktop (lg+): `DeskLayout` — content column (`max-w-[72ch]`) + right sidebar (`w-80`)

**Main content column (top to bottom):**

1. **BriefHeader** — Desk label ("Defense"), brief date, time published, `FaithfulnessScore` badge. Headline in `text-display-lg` Playfair Display. BLUF paragraph in `text-body-lg` Lora, slightly indented, visually distinct.

2. **StalenessIndicator** — Shown only when `staleness_indicator` is non-null (D013 fallback active). Amber strip: "Today's brief is being prepared. Showing brief from [date]. Last updated [relative time]." Client Component for live relative time.

3. **ChangeBanner** — Shown when new items exist vs. yesterday's brief. "N new items since yesterday." Navy strip with subtle animation on first render.

4. **BriefItems** — Ordered by `display_order` (descending materiality). Each `BriefItem`:
   - `MaterialityBadge` (high/medium/low) — subtle, top-right of card
   - Item type badge (Award / Filing / Policy / Macro / Signal) — color-coded
   - Headline in `text-display-sm` Playfair Display SemiBold
   - Body in `text-body-md` Lora Regular
   - `EntityChip` components inline in body for resolved entities (link to `/entity/[id]` for Pro, tooltip only for Free)
   - Citation chips `[1]` `[2]` — click to open `CitationsDrawer` filtered to this item's citations
   - Thin separator between items

5. **Brief footer** — Small metadata row: "Generated [time] · Synthesis: [model short name] · Eval score: [score]" in `text-ui-sm` Inter muted.

**Sidebar (lg+ only):**
- `CatalystCalendar` widget — next 14 days of defense catalyst events
- (Pro) Followed entities quick-list — top 5 followed entities with link to entity 360
- (Pro) "Download PDF" button → triggers `GET /briefs/{id}/pdf`

**States:**
- **Normal**: brief renders fully server-side, no spinners
- **Pending/Failed (D013)**: `StalenessIndicator` shown, previous brief rendered
- **Loading skeleton**: `BriefItemSkeleton` × 4 (used only if client-side revalidation is in flight)
- **No brief exists (first deploy)**: `EmptyState` — "Today's brief is being prepared. Check back at 5:30am ET."

**SEO:** `robots: noindex` (auth-gated). `title`: "Defense Desk — Hard Power Intelligence"

---

### `GET /brief/[id]` — Brief Archive Detail

**Auth:** Required
**Render:** Server Component
**FastAPI calls:** `GET /briefs/{id}`

**Tier gate:** If `brief.date < today` and `user.tier === 'free'`:
- Render `ArchiveLock` full-page gate instead of brief content
- Shows brief headline + date (teaser), then gate: "Access the 90-day archive with Pro. 14-day free trial."
- CTA → `/subscribe`

**Layout:** Same as desk reader, single column. No sidebar.

**Archive navigation:** `← Previous brief` | `Next brief →` links above and below the brief. Server-rendered with `date - 1` and `date + 1` lookups. "Next brief" is hidden if viewing today's brief.

**States:** Same as desk reader plus the `ArchiveLock` tier gate.

**SEO:** `robots: noindex`

---

### `GET /entity/[id]` — Entity 360

**Auth:** Required
**Render:** Server Component
**FastAPI calls:** `GET /entities/{id}`

**Tier gate:** If `user.tier === 'free'`:
- Render `ArchiveLock` full-page gate (same component, different copy)
- "Entity 360 pages are available to Pro subscribers."
- CTA → `/subscribe`

**Layout:** Single column with tabbed sections.

**EntityHeader (top):**
- Canonical name in `text-display-lg` Playfair Display
- `EntityIdentifiers` row: ticker chip, CIK chip, FIGI chip, LEI chip, UEI chip (shown only if values exist)
- Desk badge(s), entity type badge
- `FollowButton` (Client Component, right-aligned)

**Tabs (shadcn `Tabs` component):**
- **Awards** — `EntityAwardsTable`: award ID, amount, description, date, contracting office. Sorted by date desc.
- **Filings** — `EntityFilingsTable`: form type, filed date, description, link to SEC EDGAR.
- **Insiders** — `EntityInsiderTable`: insider name, transaction type, shares, price, date.
- **Programs** — List of related programs (edge type `RUNS_PROGRAM`).
- **Related entities** — `EntityEdgesList`: edge type, direction, related entity name + link.

**Empty tab state:** "No [awards/filings/...] on record yet." with `EmptyState` component.

**SEO:** `robots: noindex`. `title`: "[Canonical Name] — Entity 360 — Hard Power Intelligence"

---

### `GET /subscribe` — Pricing / Trial Start

**Auth:** Public (redirect to `/desk/defense` if already Pro)
**Render:** Server Component (check auth state) + Client CTA button
**FastAPI calls:** `GET /auth/me` (if authenticated, to check tier)

**Layout:** Centered single column, max-width `lg`.

**Sections:**
1. **Headline** — "Start your 14-day free trial" in `text-display-lg` Playfair Display
2. **PricingTable** — Free vs Pro columns. Rows: each feature with ✓ / — icons. Highlight Pro column with navy border.
3. **Trial CTA** — Large primary button: "Start free trial — no charge for 14 days". Sub-text: "Credit card required. Cancel anytime. Charged $19/month after trial."
4. **Annual option** — Toggle or secondary row: "$179/year — save 21%"
5. **FAQ accordion** — "What happens after my trial?", "Can I cancel?", "What's included in Free?", "Is this investment advice?" (answer: no)

**CTA action:** Calls a Next.js API route (`/api/checkout`) which generates a Lemon Squeezy hosted-checkout URL for the selected variant (monthly/annual) with `custom_data.user_id` embedded, then redirects to it (or opens the Lemon.js overlay). Success URL (redirect/`receipt_link`): `/subscribe/success`. Cancel returns to `/subscribe`. Per D045, the route surfaces a "payments not yet configured" state when `LEMONSQUEEZY_API_KEY` is absent.

**SEO:** `robots: index, follow`. `title`: "Subscribe — Hard Power Intelligence". `description`: "14-day free trial. Daily cited defense intelligence briefs. Cancel anytime."

---

### `GET /subscribe/success` — Post-Checkout Confirmation

**Auth:** Required
**Render:** Server Component (validates subscription status via `GET /auth/me`)
**FastAPI calls:** `GET /auth/me`

**Layout:** Centered, max-width `md`.

**Content:**
1. **Checkmark icon** (large, brand primary)
2. **Headline**: "You're on Pro." in `text-display-md` Playfair Display
3. **3 feature highlights**: Archive access, Entity 360, PDF export — icon + one-line description each
4. **Primary CTA**: "Go to the Defense Desk →" → `/desk/defense`

**Note:** Subscription may not have updated instantly if the Lemon Squeezy webhook hasn't fired yet. If `auth/me` still returns `free`, show a spinner and poll `GET /auth/me` every 2 seconds for up to 10 seconds (TanStack Query with `refetchInterval`). If still free after 10s, show a reassurance message: "Your subscription is being activated. Refresh in a moment."

**SEO:** `robots: noindex`

---

### `GET /subscribe/cancel` — Cancelled Checkout

**Auth:** Public
**Render:** Static

**Content:** "No worries." + one-line pitch + "Try again" CTA → `/subscribe`.

---

### `GET /login` — Sign In

**Auth:** Public (redirect to `/desk/defense` if already authenticated)
**Render:** Client Component (form)

**Layout:** Centered card, max-width `sm`. Card has `shadow-md`, `rounded-xl`, `p-8`.

**Content:**
1. HPI logo (small)
2. "Sign in" heading — `text-display-sm` Playfair Display
3. **LoginForm**:
   - Email input (type="email", autocomplete="email")
   - `PasswordInput` with Eye/EyeOff toggle (type="password", autocomplete="current-password")
   - "Forgot password?" link → `/forgot-password` (right-aligned, `text-ui-sm`)
   - Submit button: "Sign in" (full-width, primary)
4. Divider: "or continue with"
5. `OAuthButton` for Google
6. `OAuthButton` for GitHub
7. Footer: "Don't have an account? [Start free trial]" → `/signup`

**Error states:**
- Invalid credentials: inline error below password field
- OAuth error: toast notification
- Network error: inline error with retry

---

### `GET /signup` — Create Account

**Auth:** Public (redirect if authenticated)
**Render:** Client Component

**Layout:** Same card layout as `/login`.

**Content:**
1. HPI logo
2. "Start your free trial" heading — `text-display-sm` Playfair Display
3. Sub-heading: "14 days Pro, then $19/month or $179/year. Cancel anytime."
4. **SignupForm**:
   - Email input
   - `PasswordInput` (Eye/EyeOff toggle, autocomplete="new-password")
   - Submit button: "Create account" (full-width)
5. Divider
6. Google OAuth button
7. GitHub OAuth button
8. Footer: "Already have an account? [Sign in]" → `/login`
9. Fine print: "By signing up you agree to our [Terms] and [Privacy Policy]."

**Post-signup flow:**
- Email/password: Supabase sends confirmation email. Show: "Check your email to confirm your account."
- OAuth: immediate redirect to `/subscribe` for trial start (or `/desk/defense` if already subscribed)

---

### `GET /forgot-password` — Password Reset

**Auth:** Public
**Render:** Client Component

**Layout:** Same card as `/login`, simpler.

**Content:** Email input + "Send reset link" button. Success state: "Check your email for a reset link."

---

### `GET /account` — Account Settings

**Auth:** Required
**Render:** Server Component for data; Client Components for mutations
**FastAPI calls:** `GET /auth/me`, `GET /users/follows`

**Layout:** Single column, max-width `lg`. Sections separated by headings.

**Sections:**

1. **Profile** — Email (read-only), display name (editable in future). "Managed via Supabase Auth."

2. **Subscription** — `SubscriptionStatus` component:
   - Current tier badge + status
   - Trial: "Trial ends [date]" + days remaining
   - Pro: "Pro · Renews [date] · $19/month"
   - Free (lapsed): "Free plan · [Upgrade to Pro] →"
   - "Manage subscription" → Lemon Squeezy Customer Portal link (`urls.customer_portal` from the subscription, surfaced via `GET /api/portal`)
   - "Cancel subscription" → also via the Lemon Squeezy Customer Portal

3. **Follows** (Pro only — `ArchiveLock` gate if free):
   - Heading: "Followed entities"
   - Search to add: `EntitySearch` component
   - List of followed entities with remove button (trash icon, TanStack Query mutation)
   - Empty state: "Follow entities to see their items highlighted in your brief."

**SEO:** `robots: noindex`

---

### `GET /admin` — Admin Stub

**Auth:** Required + `is_admin` JWT claim (D015)
**Render:** Server Component

**Content:**
- Heading: "Admin"
- Link list: "Resolution Queue (FastAPI)" → opens `FASTAPI_URL/admin/resolution-queue` in new tab
- "System Status (FastAPI)" → opens `FASTAPI_URL/admin/status` in new tab
- "Database (Supabase Studio)" → Supabase project URL in new tab

No custom components. No data fetching. Stub only in Cycle 1.

---

## 5. User Flows

### Flow 1: New visitor → trial subscriber

```
/ (marketing home)
  └─ "Start free trial" CTA
      └─ /signup
          ├─ Email/password → confirm email → /subscribe
          └─ OAuth → /subscribe
              └─ "Start free trial" → Lemon Squeezy Checkout
                  ├─ Success → /subscribe/success → /desk/defense
                  └─ Cancel → /subscribe
```

### Flow 2: Free user → archive upgrade

```
/desk/defense (reading current brief)
  └─ Clicks archive brief link or visits /brief/[id] with date < today
      └─ ArchiveLock gate shown
          └─ "Start 14-day free trial" CTA
              └─ /subscribe → Lemon Squeezy Checkout → /subscribe/success
```

### Flow 3: Reading a brief + citations

```
/desk/defense
  └─ Brief renders (Server Component, no spinner)
      └─ User reads brief item
          └─ Clicks citation chip [1]
              └─ CitationsDrawer slides in from right
                  ├─ Shows citation card: source, date, excerpt, external link
                  └─ User clicks source URL → opens in new tab
```

### Flow 4: Following an entity (Pro)

```
/desk/defense
  └─ Entity chip in brief item → hover shows "View entity →"
      └─ Clicks → /entity/[id]
          └─ EntityHeader with FollowButton
              └─ Click "Follow" → optimistic UI update
                  └─ TanStack mutation: POST /users/follows
                      └─ Next brief load: entity's items sorted first
```

---

## 6. Responsive Layout Rules

| Breakpoint | Width | Layout behavior |
|------------|-------|-----------------|
| Base (mobile) | <640px | Single column, 16px horizontal padding, bottom-anchored CitationsDrawer (full sheet) |
| `sm:` | 640px | Single column, 24px padding, more comfortable reading width |
| `md:` | 768px | Single column, brief max-width kicks in (`max-w-[72ch]`) |
| `lg:` | 1024px | Two-column: content + sidebar; CitationsDrawer as right panel |
| `xl:` | 1280px | Same as lg, page max-width container (`max-w-7xl`) centered |

**NavBar:** Hamburger below `lg:`; full horizontal nav at `lg:+`.

**CitationsDrawer:**
- `<lg:` → shadcn `Sheet` component, `side="bottom"`, full-width
- `lg:+` → fixed right panel, `w-[420px]`, `top-[nav-height]`, `h-[calc(100vh-nav-height)]`, does not push content (overlay)

**Typography scaling:** `text-display-xl` scales down one step at `<md:`. Brief body font size stays `text-body-lg` (18px) at all breakpoints — reading comfort is not sacrificed for mobile.

---

## 7. SEO and Metadata

### Per-page metadata (Next.js `generateMetadata`)

| Route | title | robots |
|-------|-------|--------|
| `/` | Hard Power Intelligence — Defense, Energy & AI Briefings | index |
| `/subscribe` | Subscribe — Hard Power Intelligence | index |
| `/desk/defense` | Defense Desk — HPI | noindex |
| `/brief/[id]` | [brief headline] — HPI | noindex |
| `/entity/[id]` | [canonical name] — Entity 360 — HPI | noindex |
| `/account` | Account — HPI | noindex |
| `/login` | Sign In — HPI | noindex |
| `/signup` | Start Free Trial — HPI | noindex |

### Open Graph images (`next/og`)

Dynamic OG image generation for the marketing home and subscribe pages.
- `app/og/route.tsx` — `ImageResponse` returning: HPI logo + brief headline or tagline on navy (`#1B3A6B`) background with gold (`#C8A96E`) accent line. 1200×630px.
- Used as `og:image` on `/` and `/subscribe`
- Auth-gated pages use the static fallback OG image

### Sitemap

`app/sitemap.ts` — includes `/` and `/subscribe` only. All other routes are auth-gated and excluded.

---

## 8. Loading and Error Conventions

### Loading states

- **Server Component pages:** No loading spinner for the initial render — content arrives pre-rendered. Use `loading.tsx` files for Suspense fallbacks only if a section uses dynamic segments.
- **Brief items:** `BriefItemSkeleton` × 4 used when TanStack Query revalidates in the background (not on first load).
- **Entity tabs:** Each tab's table shows `LoadingSkeleton` rows while data arrives.

### Error states

- **API error on brief page:** `ErrorBoundary` catches, renders: "Unable to load the brief. We've been notified." with a retry button. Sentry captures automatically.
- **404 (brief/entity not found):** Next.js `notFound()` → renders the nearest `not-found.tsx`.
- **Auth expired:** Supabase middleware refreshes tokens automatically. If refresh fails, middleware redirects to `/login`.

### Empty states

- **No brief published (new deploy):** `EmptyState` on `/desk/defense` — "Today's brief is being prepared. Check back at 5:30am ET."
- **Entity with no data:** Per-tab `EmptyState` — "No [awards] on record for this entity yet."
- **No follows:** `EmptyState` on `/account` follows section — "Follow entities from any brief or entity page."


## 9. Visual / UX Enhancement Roadmap (D084)

Grounded in a 2026 competitive scan (The Diff $20/mo, Stratechery $15/mo, The Information
$399/yr, SemiAnalysis institutional, AlphaSense $10–40k/seat). The takeaways: AlphaSense's
defining UX is **click-a-claim → see the source passage**; SemiAnalysis sells **charts/data**,
not prose; The Information moved to an **app-like multi-feed IA**; and fintech-intel best practice
is **card layouts + sparklines, "compared to what?" context, importance-first hierarchy, beware
prose overload**.

**Design thesis:** HPI's editorial typographic reader (Stratechery-like) is an asset — keep it.
But HPI's two differentiators — **provenance** (the moat) and **convergence** (the identity) — are
visually under-expressed, and there is no **data layer** or **scannable summary**. Foreground both
differentiators; add glanceability; don't lose the calm reader. Target feel: *Stratechery typography
+ Bloomberg glanceability + AlphaSense click-to-source.*

**Already built (do not rebuild):** `CitationsDrawer` (per-item source cards: source · date · title ·
excerpt · "View source ↗"); item-type color tokens (`--color-item-award|filing|policy|macro|signal`);
inline `[CITE:N]` chips that open the drawer; the layered Convergence + Analysis disclosure cards.

### Tier 1 — provenance visible + at-a-glance (DONE, D084 — no backend change)
- **At-a-glance header** (`brief-glance.tsx`): a compact, scannable ledger above the long read — per
  item: type swatch + label, headline (anchor-links to the item), a normalized **magnitude bar** from
  the item's key dollar figure (parsed from headline, then body), and a **Sources (N)** count. A summary
  strip: "N items · ≈$X tracked · 100% cited." Delivers the day in ~10 seconds (importance-first).
- **Provenance discoverability:** a visible **"Sources (N) ↗"** control on each item (not just the tiny
  inline chips) opening the existing drawer; prettify `source_id` → display name (SEC EDGAR,
  USASpending.gov, arXiv, GDELT…) in the drawer + glance.

### Tier 2a — the data layer, frontend (DONE, D087 — no backend change)
- **Type icons** — a consistent glyph per `item_type`, centralized in `web/lib/item-types.ts` (label +
  color token + icon), replacing the bare dot in `brief-glance` and `brief-content`.
- **Magnitude bars inline** on each item's key dollar figure (reusing the D084 `amounts` parser),
  normalized to the brief max → "compared to what?" at the item, not just in the ledger.
- **Signal trend styling** — `SignalLine` (`web/lib/signal.ts` `splitSignal`) renders a trend arrow +
  color on each GDELT momentum delta, replacing the flat dashed text. Disclaimer text preserved.

### Tier 2b — real signal sparkline (TODO — needs backend)
- A true **sparkline** of the GDELT volume series (6w) behind the Signal line. Blocked on persisting the
  numeric series: `briefs.signal` is currently only a prose string (`build_signal_line`), so this is a
  schema + generator + API change, then a small client chart. Tier 2a's arrow is the interim.

### Tier 3 — entity + convergence as first-class
- **Entity chips** (company + ticker) linking to Entity 360 (`/entity/[id]`), teasing the Pro feature in
  the free brief. **Convergence visualization** — a small entity/theme relationship graph of the day's
  cross-desk links; the visual front-end for the `entity_edges` moat (D055).

### Tier 3 — entity + convergence as first-class
- **Entity chips** (company + ticker) linking to Entity 360 (`/entity/[id]`), teasing the Pro feature in
  the free brief. **Convergence visualization** — a small entity/theme relationship graph of the day's
  cross-desk links; the visual front-end for the `entity_edges` moat (D055).

### Tier 4 — information architecture (later)
- A cross-desk **front page / feed** and **archive search** — the app-like step (cf. The Information).

**Dependency:** Tier 1's at-a-glance + Tier 2's bars are *honest* — a filler item (no $, no event) shows
an empty row. So significance-filtering (the content gate) should land first or alongside, or the new UI
will spotlight weak items rather than hide them. Selection quality and visualization reinforce each other.

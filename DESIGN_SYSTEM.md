# Design System — Hard Power Intelligence

Visual language for the web reader and marketing site. "Premium intelligence publication" —
The Economist's restraint, Stratfor's analytical weight, Bloomberg's data precision.

Gate 3 artifact. Implemented via shadcn/ui CSS custom properties + Tailwind config extensions.

---

## 1. Design Principles

**Editorial over app.** Typography and whitespace carry the design. Decoration is noise.
A well-set typeface and comfortable leading matter more than gradients and shadows.

**Information hierarchy.** Every element has a clear weight. Nothing competes with brief
content for attention. UI chrome recedes; intelligence surfaces.

**Restraint in color.** Color signals meaning: status, urgency, entity type, tier. It does
not signal style. Navy and gold used sparingly — the expensive feel comes from proportion
and type, not from applying brand colors everywhere.

**Trust signals as first-class citizens.** Faithfulness score, source badges, and citation
chips are not UI footnotes — they are the product's credibility proof and should be
visually prominent without being visually loud.

---

## 2. Color Tokens

Implemented as CSS custom properties on `:root`. shadcn/ui's theming system reads these.
Dark mode tokens reserved with the same names; values swap. Dark mode implementation
deferred to Cycle 2 (D021).

### Background and surface

```css
:root {
  --background:     250 250 248;   /* #FAFAF8 — warm white, editorial */
  --surface:        255 255 255;   /* #FFFFFF — card surfaces */
  --surface-muted:  245 244 240;   /* #F5F4F0 — sidebar, muted sections */
}
```

### Text

```css
  --foreground:         26  26  26;  /* #1A1A1A — near-black, body text */
  --foreground-muted:   107 107 107; /* #6B6B6B — secondary text, metadata */
  --foreground-subtle:  155 155 155; /* #9B9B9B — placeholder, tertiary */
```

### Brand

```css
  --brand-primary:      27  58 107;  /* #1B3A6B — deep navy */
  --brand-primary-fg:   255 255 255; /* text on brand-primary */
  --brand-secondary:    200 169 110; /* #C8A96E — antique gold */
  --brand-secondary-fg: 27  58 107;  /* text on brand-secondary */
```

### Interactive

```css
  --primary:        37  99 235;   /* #2563EB — blue, CTAs, links */
  --primary-fg:     255 255 255;
  --primary-hover:  29  78 216;   /* #1D4ED8 */
```

### Status

```css
  --success:        22 163  74;   /* #16A34A — published, verified */
  --success-light:  240 253 244;  /* bg for success badges */
  --warning:        217 119   6;  /* #D97706 — pending, stale */
  --warning-light:  255 251 235;
  --destructive:    220  38  38;  /* #DC2626 — failed, error */
  --destructive-light: 254 242 242;
  --info:            14 165 233;  /* #0EA5E9 — informational */
  --info-light:     240 249 255;
```

### Desk accent colors (badge backgrounds)

```css
  --desk-defense:   27  58 107;   /* #1B3A6B — navy */
  --desk-energy:    22 163  74;   /* #16A34A — green */
  --desk-ai:        124 58 237;   /* #7C3AED — violet */
```

### Brief item type colors

```css
  --item-award:     27  58 107;   /* navy */
  --item-filing:    37  99 235;   /* blue */
  --item-policy:    217 119  6;   /* amber */
  --item-macro:     20 184 166;   /* teal */
  --item-signal:    124 58 237;   /* violet */
```

### Border and ring

```css
  --border:     229 228 223;   /* #E5E4DF — warm gray, subtle */
  --border-strong: 201 200 196; /* #C9C8C4 — visible separator */
  --ring:       37  99 235;    /* focus ring, matches interactive */
  --radius:     0.375rem;      /* 6px base radius */
```

### Applying tokens in Tailwind

shadcn/ui maps these to Tailwind utility classes automatically. Custom tokens are used
directly in CSS or via `@apply`. Example:
```css
.brief-headline { color: rgb(var(--foreground)); font-family: var(--font-display); }
```

---

## 3. Typography System

### Font families

Loaded via `next/font/google` in `app/layout.tsx`. Zero layout shift; no external request at runtime.

```typescript
import { Playfair_Display, Lora, Inter } from 'next/font/google'

const playfair = Playfair_Display({
  subsets: ['latin'],
  variable: '--font-display',
  display: 'swap',
})

const lora = Lora({
  subsets: ['latin'],
  variable: '--font-body',
  display: 'swap',
})

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-ui',
  display: 'swap',
})
```

```css
:root {
  --font-display: var(--font-playfair), Georgia, serif;
  --font-body:    var(--font-lora), Georgia, serif;
  --font-ui:      var(--font-inter), system-ui, sans-serif;
}
```

**Usage rules:**
- `--font-display` (Playfair Display): headlines, brief item titles, entity names, page titles, hero copy
- `--font-body` (Lora): brief body paragraphs, citation excerpts, marketing body copy
- `--font-ui` (Inter): all navigation, buttons, badges, labels, form fields, metadata, everything else

### Type scale

Add to `tailwind.config.ts` under `theme.extend.fontSize`:

```typescript
fontSize: {
  // Display — Playfair Display
  'display-xl': ['3rem',    { lineHeight: '1.15', fontWeight: '700', letterSpacing: '-0.02em' }],  // 48px — hero
  'display-lg': ['2.25rem', { lineHeight: '1.2',  fontWeight: '700', letterSpacing: '-0.02em' }],  // 36px — page title, brief headline
  'display-md': ['1.75rem', { lineHeight: '1.25', fontWeight: '600', letterSpacing: '-0.01em' }],  // 28px — section headers
  'display-sm': ['1.375rem',{ lineHeight: '1.3',  fontWeight: '600', letterSpacing: '-0.01em' }],  // 22px — brief item headlines

  // Body — Lora
  'body-lg':    ['1.125rem',{ lineHeight: '1.75', fontWeight: '400' }],  // 18px — brief body (primary reading size)
  'body-md':    ['1rem',    { lineHeight: '1.7',  fontWeight: '400' }],  // 16px — standard body
  'body-sm':    ['0.875rem',{ lineHeight: '1.65', fontWeight: '400' }],  // 14px — captions, citation text

  // UI — Inter
  'ui-lg':      ['1rem',    { lineHeight: '1.5',  fontWeight: '500' }],  // 16px — button labels, nav
  'ui-md':      ['0.875rem',{ lineHeight: '1.5',  fontWeight: '400' }],  // 14px — form labels, metadata
  'ui-sm':      ['0.75rem', { lineHeight: '1.4',  fontWeight: '400' }],  // 12px — badges, timestamps
  'ui-xs':      ['0.6875rem',{ lineHeight: '1.4', fontWeight: '500' }],  // 11px — ALL CAPS labels
}
```

### Reading line length

Brief body column is capped at `max-w-[72ch]` — optimal editorial line length (65–75 characters). Never let brief body text span the full viewport width.

---

## 4. Spacing and Layout

Tailwind's default 4px base scale is used throughout. Custom additions:

```typescript
// tailwind.config.ts — theme.extend
maxWidth: {
  'content': '72ch',    // brief body reading column
  'page':    '80rem',   // page max-width (1280px)
  'card':    '42rem',   // auth/confirmation card
}
```

**Spacing conventions:**
- Page horizontal padding: `px-4` (mobile), `px-6` (sm+), `px-8` (lg+)
- Section vertical gap: `py-16` (marketing), `py-8` (reader)
- Brief item padding: `p-6`
- Card padding: `p-8` (auth, confirmation), `p-6` (brief item cards)
- Sidebar gap from content: `gap-8`

---

## 5. Elevation and Shadow

Three levels only. Shadow color is warm (not pure black) to match the editorial palette.

```typescript
// tailwind.config.ts — theme.extend.boxShadow
boxShadow: {
  'sm':  '0 1px 2px 0 rgba(26, 26, 26, 0.06)',
  'md':  '0 4px 12px 0 rgba(26, 26, 26, 0.08)',
  'lg':  '0 12px 32px 0 rgba(26, 26, 26, 0.12)',
  'drawer': '−8px 0 32px 0 rgba(26, 26, 26, 0.10)',
}
```

Usage:
- `shadow-sm`: brief item cards, entity identifier chips, source badges
- `shadow-md`: dropdowns, command palette, user menu
- `shadow-lg`: modals, confirmation dialogs
- `shadow-drawer`: citations drawer panel

---

## 6. Border Radius

```typescript
// tailwind.config.ts — theme.extend.borderRadius (supplements defaults)
borderRadius: {
  // Uses --radius CSS variable (6px) for shadcn compatibility
  DEFAULT: 'var(--radius)',          // 6px — buttons, inputs, most UI elements
  'sm': 'calc(var(--radius) - 2px)', // 4px — badges, chips
  'md': 'var(--radius)',             // 6px
  'lg': 'calc(var(--radius) + 4px)', // 10px — cards
  'xl': '1rem',                      // 16px — modals, drawers, large cards
}
```

---

## 7. Motion and Animation

Restrained. Brief and entity content never animates — reading content should be stable.
Interactions animate; content does not.

```typescript
// tailwind.config.ts — theme.extend
transitionDuration: {
  'fast':   '150ms',
  DEFAULT:  '200ms',
  'slow':   '300ms',
  'drawer': '350ms',
}

transitionTimingFunction: {
  'enter': 'cubic-bezier(0.0, 0.0, 0.2, 1)',  // ease-out, for appearing elements
  'exit':  'cubic-bezier(0.4, 0.0, 1, 1)',    // ease-in, for disappearing elements
}

keyframes: {
  'skeleton-pulse': {
    '0%, 100%': { opacity: '1' },
    '50%':      { opacity: '0.5' },
  },
  'slide-in-right': {
    from: { transform: 'translateX(100%)' },
    to:   { transform: 'translateX(0)' },
  },
  'fade-in': {
    from: { opacity: '0' },
    to:   { opacity: '1' },
  },
}

animation: {
  'skeleton':      'skeleton-pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
  'slide-in-right':'slide-in-right 350ms cubic-bezier(0.0, 0.0, 0.2, 1)',
  'fade-in':       'fade-in 200ms ease-out',
}
```

**Citations drawer:** `animate-slide-in-right` on open. shadcn `Sheet` handles close animation.

---

## 8. Component-Level Tokens (shadcn/ui)

shadcn uses these CSS custom properties for its default component styles. Set in
`app/globals.css`. Values reference the color tokens above.

```css
@layer base {
  :root {
    --background: 250 250 248;
    --foreground: 26 26 26;
    --card: 255 255 255;
    --card-foreground: 26 26 26;
    --popover: 255 255 255;
    --popover-foreground: 26 26 26;
    --primary: 27 58 107;           /* brand navy for primary buttons */
    --primary-foreground: 255 255 255;
    --secondary: 245 244 240;
    --secondary-foreground: 26 26 26;
    --muted: 245 244 240;
    --muted-foreground: 107 107 107;
    --accent: 200 169 110;          /* gold accent */
    --accent-foreground: 27 58 107;
    --destructive: 220 38 38;
    --destructive-foreground: 255 255 255;
    --border: 229 228 223;
    --input: 229 228 223;
    --ring: 37 99 235;
    --radius: 0.375rem;
  }
}
```

---

## 9. Icon Usage

**Library:** `lucide-react` (ships with shadcn/ui).

**Size convention:** Always use the `size` prop, never CSS width/height overrides.
- `size={16}` — inline icon in text, badge icon
- `size={20}` — standard UI icon (buttons, nav)
- `size={24}` — page-level icon (empty state, heading icon)
- `size={40}` — hero icon (confirmation page checkmark, large empty state)

**Common icons and their semantic use:**

| Icon | Use |
|------|-----|
| `Eye` / `EyeOff` | Password visibility toggle |
| `ChevronRight` | Citation chip indicator, expand |
| `X` | Close (drawer, modal, badge remove) |
| `ExternalLink` | Source citation link |
| `Lock` | Pro-gated content indicator |
| `FileText` | PDF export, brief archive |
| `Building2` | Company entity type |
| `Calendar` | Catalyst calendar, event |
| `Star` / `StarOff` | Follow / Unfollow entity |
| `AlertTriangle` | Staleness indicator, warning |
| `CheckCircle2` | Published status, success |
| `Clock` | Pending status |
| `TrendingUp` | Materiality, signal item type |
| `Landmark` | Policy, government item type |
| `BarChart3` | Macro item type |
| `Search` | Search trigger |
| `Menu` | Mobile hamburger |
| `LogOut` | Sign out |
| `Settings` | Account settings |
| `Shield` | Defense desk icon |

**No custom SVG icons in Cycle 1.** All icons from lucide-react. Custom icons deferred
to when a distinct HPI visual identity is designed.

---

## 10. Tailwind Config Extensions (complete reference)

```typescript
// tailwind.config.ts
import type { Config } from 'tailwindcss'
import { fontFamily } from 'tailwindcss/defaultTheme'

const config: Config = {
  darkMode: ['class'],                // dark mode via class (for future Pro toggle)
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        display: ['var(--font-display)', ...fontFamily.serif],
        body:    ['var(--font-body)',    ...fontFamily.serif],
        ui:      ['var(--font-ui)',      ...fontFamily.sans],
      },
      colors: {
        brand: {
          primary:   'rgb(var(--brand-primary) / <alpha-value>)',
          secondary: 'rgb(var(--brand-secondary) / <alpha-value>)',
        },
        desk: {
          defense: 'rgb(var(--desk-defense) / <alpha-value>)',
          energy:  'rgb(var(--desk-energy) / <alpha-value>)',
          ai:      'rgb(var(--desk-ai) / <alpha-value>)',
        },
        item: {
          award:  'rgb(var(--item-award) / <alpha-value>)',
          filing: 'rgb(var(--item-filing) / <alpha-value>)',
          policy: 'rgb(var(--item-policy) / <alpha-value>)',
          macro:  'rgb(var(--item-macro) / <alpha-value>)',
          signal: 'rgb(var(--item-signal) / <alpha-value>)',
        },
      },
      maxWidth: {
        content: '72ch',
        page:    '80rem',
        card:    '42rem',
      },
      boxShadow: {
        sm:     '0 1px 2px 0 rgb(26 26 26 / 0.06)',
        md:     '0 4px 12px 0 rgb(26 26 26 / 0.08)',
        lg:     '0 12px 32px 0 rgb(26 26 26 / 0.12)',
        drawer: '-8px 0 32px 0 rgb(26 26 26 / 0.10)',
      },
      keyframes: {
        'skeleton-pulse': {
          '0%, 100%': { opacity: '1' },
          '50%':      { opacity: '0.5' },
        },
        'slide-in-right': {
          from: { transform: 'translateX(100%)' },
          to:   { transform: 'translateX(0)' },
        },
        'fade-in': {
          from: { opacity: '0' },
          to:   { opacity: '1' },
        },
      },
      animation: {
        skeleton:        'skeleton-pulse 2s ease-in-out infinite',
        'slide-in-right':'slide-in-right 350ms cubic-bezier(0, 0, 0.2, 1)',
        'fade-in':       'fade-in 200ms ease-out',
      },
    },
  },
  plugins: [
    require('tailwindcss-animate'),    // shadcn/ui dependency
    require('@tailwindcss/typography'), // for brief body prose styling
  ],
}

export default config
```

### `@tailwindcss/typography` configuration

The `prose` class from `@tailwindcss/typography` is applied to brief body text columns.
Override the default prose styles to use the HPI fonts and color tokens:

```css
/* app/globals.css */
.prose {
  --tw-prose-body:       rgb(var(--foreground));
  --tw-prose-headings:   rgb(var(--foreground));
  --tw-prose-links:      rgb(var(--primary));
  --tw-prose-bold:       rgb(var(--foreground));
  font-family:           var(--font-body);
  font-size:             1.125rem;   /* 18px */
  line-height:           1.75;
}
```

---

## 11. Atmospheric backdrop — parchment-equations motif

A parchment texture overlaid with accurately-rendered equations grouped by the four
coverage domains (Defense, Space, AI, Energy) is the brand's atmospheric motif.
Source asset: `web/public/textures/parchment-equations.png`. See D051.

This is an exception to Principle 1, scoped tightly so it never competes with reading
content:

| Surface                              | Treatment                                            |
|--------------------------------------|------------------------------------------------------|
| Marketing hero, auth (`/`, login)    | Full image as backdrop, dimmed behind a `#FAFAF8`/navy overlay (≈80–90% opacity scrim) so foreground type meets contrast targets. |
| App chrome (header, footer, sidebar) | A *hint* only — faint parchment fill or a thin equation-edge strip. Low opacity (≈8–15%). Motif persists across authenticated pages. |
| Reading surfaces (brief reader, dashboard, cards) | None. Clean `--surface` / `--background`. The backdrop stops at the chrome. |

Implementation notes for the frontend gate:
- Apply via a dedicated wrapper/util, not on `body`, so reading routes opt out cleanly.
- Ship an optimized derivative (WebP/AVIF) plus a pre-dimmed hero variant and a
  low-opacity chrome crop — do not scrim a 3.2 MB PNG at runtime.
- Respect `prefers-reduced-motion`/contrast: the scrim must keep body text ≥ WCAG AA.
- Verify the equations are correct before launch — visibly wrong math undercuts the
  "every claim cites its source" brand promise.

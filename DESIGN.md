# Design — TerraTriage

Locked design system. This file is transcribed from the shipped implementation
(`web/src/index.css`, `web/tailwind.config.js`, `web/src/lib/damage.ts`,
`web/src/lib/nc.ts`) — it is a record of the system, not a redesign of it.
`web/src/index.css` `:root` is the source of truth; amend there and here together.

Future design passes read this file first. Pages **share** this system — they do
not each get a different look.

---

## Direction

**Emergency-response cartography.** The reference points are real government
mapping tools — USGS topo conventions, NOAA storm-tracking dashboards, FEMA
damage-assessment sheets — not decorative landing-page design. The interface is
a working instrument: a reader should be able to tell primary from secondary
from tertiary at a glance, and every mark on a map should mean one specific
thing. Warm paper, one blue accent, a fixed four-step damage ramp borrowed from
xView2/xBD. No mood, no atmosphere, no decoration that isn't carrying data.

- **Genre** · utilitarian / technical (Hallmark: modern-minimal, dashboard school)
- **Macrostructure** · Workbench — persistent top bar, map canvas, docked panels
- **Mode** · light default, full dark theme. Dark is a real second surface
  (map basemap swaps positron ↔ dark-matter), not a reflex — an operator on a
  night shift in an EOC is a real user.

---

## Colour

Tokens are space-separated `R G B` triples on `:root` in `index.css`, re-declared
for dark under `@media (prefers-color-scheme: dark) :root:not([data-theme=light])`
and `:root[data-theme=dark]`. Tailwind reads them as `rgb(var(--x) / <alpha>)`.

| Token | Light | Dark | Role |
| --- | --- | --- | --- |
| `--canvas` | `#FAF9F6` | `#0F1115` | page ground (warm paper / near-black) |
| `--surface` | `#FFFFFF` | `#17191E` | panels, cards, top bar |
| `--surface-2` | `#F4F3EF` | `#202329` | insets, skeletons, form fields |
| `--line` | `#E3E0D9` | `#2A2E36` | hairline borders |
| `--line-strong` | `#C8C5BC` | `#3E434E` | dashed drop-zones, slider track |
| `--ink` | `#1C1D21` | `#E9EAE8` | primary text, headlines |
| `--ink-dim` | `#5C6068` | `#9EA1A8` | secondary text, labels |
| `--ink-faint` | `#8A8E96` | `#6C7079` | captions, metadata |
| `--accent` | `#2563EB` | `#4A80F6` | the one accent — links, primary buttons, active nav, selected building |
| `--accent-soft` | `#E0EAFE` | `#1C2A4A` | accent fills behind text |
| `--accent-ink` | `#FFFFFF` | `#FFFFFF` | text on an accent fill |
| `--meter` | `#475569` | `#8494A8` | neutral gauge / bar fill (non-severity) |

**Accent discipline.** Blue is for interaction and "this is live", never for
severity. It stays well under ~5 % of any viewport. There is no second accent,
no gradient, no accent-on-accent.

### Damage ramp — fixed, theme-independent

From `web/src/lib/damage.ts` / `tailwind.config.js`. This is the xView2 four-level
scale; it does not change between light and dark because it is data, not chrome.

| Class | Hex | Meaning |
| --- | --- | --- |
| `dmg0` | `#3FA06D` green | no damage |
| `dmg1` | `#EFB036` amber | minor damage |
| `dmg2` | `#E56A2B` orange | major damage |
| `dmg3` | `#A81B38` red | destroyed |

Green base means any damage reads instantly against it on the 3-D map, the
Summary bars, and the Home cards.

### Live severity ramp — NC monitor

From `web/src/lib/nc.ts` `NC_SEV_COLOR`, used for flood / streamflow / alert
marks on the Live map and Home hero. Deliberately a **different, cooler** ramp
from the damage ramp so a flood gauge is never confused with a destroyed
building: `-1` offline `#5A6673` · `0` normal `#5A7C86` · `1` watch `#F5D76E` ·
`2` elevated `#E8894A` · `3` severe `#D1495B`. Road closures and cameras sit
**off** this ramp on fixed marks — they are ground-truth references, not risk.

---

## Type

`@import` from Google Fonts in `index.css`. A deliberate pairing — a squared
grotesque for display against a clean humanist sans for text — chosen so
headlines read with the flat authority of a printed field report while the body
stays quiet at small sizes on a dense screen. Not Inter; not the current
anti-slop trend fonts either.

- `--font-display` · **Archivo** (500 / 600 / 700) — `h1`–`h3`, `.section-title`,
  wordmark, stat figures. Always roman. `letter-spacing: -0.014em`,
  `text-wrap: balance`. Headline weight is 600.
- `--font-sans` · **Geist** (400 / 450 / 500 / 600) — all body and UI text.
  `font-feature-settings: "cv11", "ss01"`.
- `--font-mono` · **Geist Mono** (400 / 500) — only where digits must align in a
  column (`.tnum` is preferred first) and inline CLI snippets.

Scale is Tailwind's default plus one addition: `text-2xs` = `0.6875rem` /
`1rem`, the caption size used across panels. `.cap` (11px / 500 / `--ink-faint`)
is the quiet sentence-case label — never uppercase-mono as decoration.

**No italic display type.** Emphasis is weight, `--accent`, or a drawn rule.

---

## Space, radius, elevation

- **Spacing** · Tailwind's 4 px scale, unextended. No arbitrary pixel gaps.
- **Radius** · `sm 4 · DEFAULT 6 · md 8 · lg 10 · xl 14` (px). `.panel` is 10.
  Corners are tight on purpose — this is closer to a map legend than a SaaS card.
- **Border** · always a single hairline `1px solid var(--line)`, all four sides.
  No thick side-stripes, no card nested inside a card.
- **Elevation** · `.panel` = `0 1px 2px /.08, 0 6px 20px /.10` of `--shadow`.
  One soft shadow, opaque surface. **No `backdrop-blur` as decoration** — it is
  used in exactly four places, each floating over live map imagery or a scrim:
  the deck.gl map tooltip, the Home "feeds live" pill, and the two modal
  overlays (⌘K, Dialog). Nowhere else.
- Dark mode conveys elevation with surface lightness, not glow.

---

## Motion

Easings (`index.css` + `tailwind.config.js`): `--ease-out`
`cubic-bezier(0.23, 1, 0.32, 1)` for almost everything; `--ease-drawer`
`cubic-bezier(0.32, 0.72, 0, 1)` for sheets. Never the bare browser `ease`,
never overshoot/bounce on UI state.

**What animates**

- `.pressable` — `transform` + colour, 130–150 ms `--ease-out`; `:active`
  `scale(0.975)`. On every button.
- Nav active-tab indicator — `transform` + `width`, 300 ms `--ease-out`.
- Hero map — `opacity` fade-in, 700 ms, once.
- Live NEXRAD radar — 300–600 ms raster cross-fade; a 2 s ambient loop on the
  Home hero. Pauses on a hidden tab and under `prefers-reduced-motion`.
- Skeletons — 1.4 s shimmer while a feed loads.
- **Stat figures count up** to their value (~600 ms `--ease-out`, `useCountUp`,
  no library) — Home status tiles, Summary headline figure, Review backlog
  count. First paint only; a value that changes later just updates.
- **One orchestrated entrance.** On the Home dashboard's first paint the status
  tiles and the assessed-area cards reveal in a short stagger (`opacity` + 4px
  `translateY`, ~50 ms apart, CSS `@keyframes` + `animation-delay`). It runs
  once, on Home only. No other screen has an entrance animation.

**What does not**

- No element fades in on scroll. Once a screen is mounted, its content is just
  there.
- Focus rings appear **instantly** (`:focus-visible`, 2px `--accent`,
  `outline-offset: 2px`) — never transitioned.
- `prefers-reduced-motion: reduce` drops every animation and transition to
  ~0 ms (global rule in `index.css`) and stops the radar loop.

**Interaction stance**

- Silent success. Toasts are for failures, background jobs, and "link copied"
  (an effect the user can't see) — not for actions whose result is on screen.
- Optimistic update + Undo over a confirm dialog. Review-queue overrides apply
  immediately.
- Hover tooltips delay ~800 ms; focus shows them at 0 ms.

### Smooth-scroll libraries — deliberately declined

**No Lenis, no GSAP ScrollTrigger.** This is a dashboard, not a scrolling
marketing site. Four surfaces own the wheel — the MapLibre `scrollZoom` on the
Home hero, the Live map, Assess, and the Damage map — plus the History
timeline's hand-rolled non-passive wheel-zoom-to-cursor. A global smooth-scroll
layer would fight all five and add perceptible input lag, which is the opposite
of the goal. Scroll is native and owned by the map layer.
`html { scroll-behavior: smooth }` (already set) covers anchor jumps.

**No motion library at all.** Every animation in the app is CSS `@keyframes` /
`transition` plus one ~30-line `useCountUp` hook. `motion` / `framer-motion` /
`gsap` / `lenis` are not dependencies. Nothing here needs them, and the Home
bundle stays lean (gzip ~390 KB) without them.

---

## Components

- `.panel` — the one container. Opaque `--surface`, hairline `--line`, 10px,
  one soft shadow. Everything docks in a panel or sits directly on `--canvas`.
- `.section-title` — Archivo 13px / 600 / `--ink`. Panel headers. **Not** an
  eyebrow; there are no `01 · SECTION` kickers anywhere, and no tag-left /
  heading-right split heads.
- Primary button — `bg-accent text-accent-ink`, radius `md`, `.pressable`.
- Secondary button — `border-line bg-surface text-ink-dim`, same radius,
  `hover:text-ink`.
- Damage bar — a flex row of `dmg0`–`dmg3` spans sized by count share.
- Icons — hand-built inline SVG at 12–16px, `stroke-width` 1.4–1.6, currentColor.
  One exception: the ⌘K palette uses `lucide-react` at caption size for its row
  glyphs. No emoji as functional icons anywhere.

---

## Copy

Plain, specific, sentence case. Names the real source ("NOAA NWPS", "xView2 CMU
baseline classifier"), the real number, the real date. No marketing register, no
invented metrics, no em dashes (purged; use `.` before a capital, else `,`).

# Design - NC Recon

Locked design system. This file is transcribed from the shipped implementation
(`web/src/index.css`, `web/tailwind.config.js`, `web/src/lib/damage.ts`,
`web/src/lib/nc.ts`) - it is a record of the system, not a redesign of it.
`web/src/index.css` `:root` is the source of truth; amend there and here together.

Future design passes read this file first. Pages **share** this system - they do
not each get a different look.

---

## Direction

**Emergency-response cartography.** The reference points are real government
mapping tools - USGS topo conventions, NOAA storm-tracking dashboards, FEMA
damage-assessment sheets - not decorative landing-page design. The interface is
a working instrument: a reader should be able to tell primary from secondary
from tertiary at a glance, and every mark on a map should mean one specific
thing. Warm paper, one blue accent, a fixed four-step damage ramp borrowed from
xView2/xBD. No mood, no atmosphere, no decoration that isn't carrying data.

- **Genre** · utilitarian / technical, modern-minimal dashboard
- **Macrostructure** · Workbench - persistent top bar, map canvas, docked panels
- **Mode** · light default, full dark theme. Dark is a real second surface
  (map basemap swaps positron ↔ dark-matter), not a reflex - an operator on a
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
| `--accent` | `#2563EB` | `#4A80F6` | the one accent - links, primary buttons, active nav, selected building |
| `--accent-soft` | `#E0EAFE` | `#1C2A4A` | accent fills behind text |
| `--accent-ink` | `#FFFFFF` | `#FFFFFF` | text on an accent fill |
| `--meter` | `#475569` | `#8494A8` | neutral gauge / bar fill (non-severity) |

**Accent discipline.** Blue is for interaction and "this is live", never for
severity. It stays well under ~5 % of any viewport. There is no second accent,
no gradient, no accent-on-accent.

### Damage ramp - fixed, theme-independent

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

### Live severity ramp - NC monitor

From `web/src/lib/nc.ts` `NC_SEV_COLOR`, used for flood / streamflow / alert
marks on the Live map and Home hero. Deliberately a **different, cooler** ramp
from the damage ramp so a flood gauge is never confused with a destroyed
building: `-1` offline `#5A6673` · `0` normal `#5A7C86` · `1` watch `#F5D76E` ·
`2` elevated `#E8894A` · `3` severe `#D1495B`. Road closures and cameras sit
**off** this ramp on fixed marks - they are ground-truth references, not risk.

---

## Type

`@import` from Google Fonts in `index.css`; the families live in
`tailwind.config.js` `theme.extend.fontFamily` (`display` / `sans` / `mono`) and
are reached in CSS via `theme("fontFamily.display")`, in markup via
`font-display` / `font-sans` / `font-mono`. A deliberate pairing - a text serif
for headings against a clean grotesque for body and UI - the register US
government statistical and hazard products use (Census, BLS, USWDS default,
weather.gov product pages). Headlines read as an official instrument, not a
generated landing page; the body stays quiet at small sizes on a dense screen.

- `fontFamily.display` · **Source Serif 4** (400 / 600 / 700, optical-size
  8-60) - `h1`-`h3`, wordmark. Always roman. `letter-spacing: -0.006em`,
  `line-height: 1.16`, `font-optical-sizing: auto`, `text-wrap: balance`.
  Headline weight 600. Restrained sizes: `--text-display` clamps at ~2.6rem so a
  headline never becomes drama on a 1280-1440 px operations screen.
- `fontFamily.sans` · **Geist** (400 / 450 / 500 / 600) - all body and UI text,
  `.section-title`, `.cap`, `.eyebrow`, and the `body` default.
  `font-feature-settings: "cv11", "ss01"`.
- `fontFamily.mono` · **Geist Mono** (400 / 500) - every figure that sits in a
  column or next to another figure (`.tnum` first) and inline CLI snippets.

Scale: Tailwind's default plus `text-2xs` (`0.6875rem` / `1rem`, the panel
caption size), `text-display` and `text-display-s` (the two clamps above).
`.cap` (11 px / 500 / `--ink-faint`) is the quiet sentence-case micro-label -
a legend key or a figure caption, never a section eyebrow. `.eyebrow` (12 px /
500 / `--ink-faint`, sans) names *where you are* ("Summary · Old Fort"); it is
an ordinal/context tag, stacked above its heading, never beside it. `.section-
title` (14 px / 600 / `--ink`, sans) is a run-in heading inside a panel or
document block - sans so it reads as structure, not a second serif headline.

**No italic display type.** Emphasis is weight, `--accent`, or a drawn rule.

---

## Space, radius, elevation

- **Spacing** · Tailwind's 4 px scale, unextended. No arbitrary pixel gaps.
- **Radius** · `sm 4 · DEFAULT 6 · md 8 · lg 10 · xl 14` (px). `.panel` is 10.
  Corners are tight on purpose - this is closer to a map legend than a SaaS card.
- **Border** · always a single hairline `1px solid var(--line)`, all four sides.
  No thick side-stripes, no card nested inside a card.
- **Containers** · two only. `.panel` (hairline + one soft shadow) is for a
  container that *floats over live map imagery or a scrim* - the deck.gl
  tooltip, the map-screen side panels, the two modal overlays. `.card` (hairline,
  **no shadow**) is for every container on a plain surface - the content screens.
  Depth on a content screen comes from weight, size, and spacing, not elevation.
  Never nest a card in a card.
- **Elevation** · `.panel` = `0 1px 2px /.08, 0 6px 20px /.10` of `--shadow`.
  **No `backdrop-blur` as decoration.** Dark mode conveys elevation with surface
  lightness, not glow.
- **Data bars** · `.bar-track` (surface-2, 3 px radius) + `.bar-fill` (4 px
  rounded data-end, `--ease-out` width transition). Adjacent fills in a stacked
  bar carry a 1 px `--surface` gap (`box-shadow: 1px 0 0`). Distribution and
  confidence bars on Summary, the area cards, and History use this.

---

## Motion

Easings (`index.css` + `tailwind.config.js`): `--ease-out`
`cubic-bezier(0.23, 1, 0.32, 1)` for almost everything; `--ease-drawer`
`cubic-bezier(0.32, 0.72, 0, 1)` for sheets. Never the bare browser `ease`,
never overshoot/bounce on UI state.

**What animates**

- `.pressable` - `transform` + colour, 130-150 ms `--ease-out`; `:active`
  `scale(0.975)`. On every button.
- Nav active-tab indicator - `transform` + `width`, 300 ms `--ease-out`.
- Hero map - `opacity` fade-in, 700 ms, once.
- Live NEXRAD radar - 300-600 ms raster cross-fade; a 2 s ambient loop on the
  Home hero. Pauses on a hidden tab and under `prefers-reduced-motion`.
- Skeletons - 1.4 s shimmer while a feed loads.
- **Stat figures count up** to their value (~600 ms `--ease-out`, `useCountUp`,
  no library) - Home status tiles, Summary headline figure, Review backlog
  count. First paint only; a value that changes later just updates.
- **One orchestrated entrance.** On the Home dashboard's first paint the status
  tiles and the assessed-area cards reveal in a short stagger (`opacity` + 4px
  `translateY`, ~50 ms apart, CSS `@keyframes` + `animation-delay`). It runs
  once, on Home only. No other screen has an entrance animation.

**What does not**

- No element fades in on scroll. Once a screen is mounted, its content is just
  there.
- Focus rings appear **instantly** (`:focus-visible`, 2px `--accent`,
  `outline-offset: 2px`) - never transitioned.
- `prefers-reduced-motion: reduce` drops every animation and transition to
  ~0 ms (global rule in `index.css`) and stops the radar loop.

**Interaction stance**

- Silent success. Toasts are for failures, background jobs, and "link copied"
  (an effect the user can't see) - not for actions whose result is on screen.
- Optimistic update + Undo over a confirm dialog. Review-queue overrides apply
  immediately.
- Hover tooltips delay ~800 ms; focus shows them at 0 ms.

### Smooth-scroll libraries - deliberately declined

**No Lenis, no GSAP ScrollTrigger.** This is a dashboard, not a scrolling
marketing site. Four surfaces own the wheel - the MapLibre `scrollZoom` on the
Home hero, the Live map, Assess, and the Damage map - plus the History
timeline's hand-rolled non-passive wheel-zoom-to-cursor. A global smooth-scroll
layer would fight all five and add perceptible input lag, which is the opposite
of the goal. Scroll is native and owned by the map layer.
`html { scroll-behavior: smooth }` (already set) covers anchor jumps.

**No motion library at all.** Every animation in the app is CSS `@keyframes` /
`transition` plus one ~30-line `useCountUp` hook. `motion` / `framer-motion` /
`gsap` / `lenis` are not dependencies. Nothing here needs them, and the Home
bundle stays lean (gzip ~390 KB) without them.

---

### God's Eye View (2026-09) - what was borrowed, what was declined

[bilawalsidhu/gods-eye-view](https://github.com/bilawalsidhu/gods-eye-view)
went open source and inspired a look at what it does that would genuinely help
NC disaster response, on the app's own stack - not a rewrite onto its stack.

**Borrowed: live aircraft, NC-clipped.** A `NCDashboard` layer (off by
default, like DOT cameras/closures) pulling `adsb.lol`'s keyless point API
through the existing `/feed` proxy (`lib/nc.ts` `ncAircraft`, `server.py`
`_FEEDS["aircraft"]`). One 250nm query centred on the state covers it edge to
edge. Guard rotary-wing, medevac, and post-storm aerial survey flights read
the same as any other traffic - real disaster-response signal, not a demo.

**Declined - Cesium / Google Photorealistic 3D Tiles.** Metered (Google
Maps), fights the `maplibre-gl` v5 pin this app needs for deck.gl's
`MapboxOverlay` (see Phase B gotcha above), and a second map engine would
blow the Home bundle budget for a "wow" the 3-D extruded damage map already
delivers cheaply.

**Declined - OpenAI Realtime voice control.** Metered, and a new third-party
credential surface for a Congressional App Challenge entry with no clear
disaster-response job to do here.

**Declined - the rest of the 13-layer catalogue** (ships, satellites,
earthquakes, radio, bikeshare, space missions, global CCTV). This app
deliberately narrowed to NC-only (see the NC-only rebuild note in the project
history) - a layer only earns a place if it's NC disaster-response signal,
not global trivia. DriveNC's 1,141 NC cameras already beat a ~800 global CCTV
list for this state.

**Follow-up, same day - pushed further, held to "real data only."** The user
asked to use God's Eye View "to the max," with one hard constraint: real
data/tracking, not a demo effect. That constraint did the scoping:

- **Traffic - checked the source before building anything.** God's Eye
  View's own docs: *"without `TOMTOM_API_KEY` the traffic layer runs its
  built-in simulation"* - and even with a key, TomTom's flow data is
  aggregate vectors, not individual vehicles, so the "moving cars" are always
  an animation, never tracked traffic. Declined the animation outright; built
  the honest version instead - `nc-traffic` raster layer, TomTom's real
  relative-flow tiles (`/traffic/map/4/tile/flow/relative0[-dark]`), key-gated
  like CLOUDS, CORS-enabled so no server proxy needed. Road colour = real live
  speed vs free-flow, per segment.
- **Live camera video - checked for a documented feed, found none.**
  DriveNC's own site clearly streams a refreshing per-camera still image
  (`data-refresh-rate` + a `t=` cache-buster on a real `<img>`, confirmed by
  reading the page's JS), but the image URL is populated by an internal AJAX
  call with no documented API, unlike Austin/Caltrans/TfL in God's Eye View's
  own source list, which all publish one. Didn't reverse-engineer it: an
  undocumented state-government endpoint, and even found, `server.py`'s
  `/feed` proxy is a fixed-URL whitelist by design (`_FEEDS`, not a
  parameterized passthrough) - a per-camera image proxy is exactly the SSRF
  surface that file was hardened against. Instead: clicking a camera links out
  to the real drivenc.gov image ("View live camera image ↗" - see
  `linkLabel` in `NCDashboard.tsx`), and `About.tsx` says why plainly.
- **"Highly detailed, Google Maps feel" - real building geometry, not a new
  map engine.** CARTO's positron/dark-matter styles already carry a
  `building` source-layer (OSM-derived); the default style just renders it
  flat. Added `nc-building-depth`, a modest `fill-extrusion` at zoom ≥14 in
  `useMapLibre.ts` (shared by every screen), re-added after every style swap
  the same way the theme toggle already re-triggers style loads. This is
  texture, not a height dataset - `render_height` is used where the tile
  carries it, else a flat 8 m block - so it's framed as depth, not surveyed
  height, the same honesty bar as the traffic call above.

---

## Components

- `.panel` / `.card` - the two containers (see Space § Containers). `.panel`
  floats over a map; `.card` sits on a content screen with no shadow. Everything
  docks in one or sits directly on `--canvas`.
- `.section-title` - Geist 14px / 600 / `--ink`, run-in panel/block header.
  `.eyebrow` - Geist 12px / 500 / `--ink-faint`, the "where you are" tag, always
  stacked above its heading. **Neither is a decorative kicker**; there are no
  `01 · SECTION` numbers and no tag-left / heading-right split heads.
- Primary button - `bg-accent text-accent-ink`, radius `md`, `.pressable`.
- Secondary button - `border-line bg-surface text-ink-dim`, same radius,
  `hover:text-ink`.
- Damage bar - a flex row of `dmg0`-`dmg3` spans sized by count share.
- Icons - hand-built inline SVG at 12-16px, `stroke-width` 1.4-1.6, currentColor.
  One exception: the ⌘K palette uses `lucide-react` at caption size for its row
  glyphs. No emoji as functional icons anywhere.

---

## Copy

Plain, specific, sentence case. Names the real source ("NOAA NWPS", "xView2 CMU
baseline classifier"), the real number, the real date. No marketing register, no
invented metrics, no em dashes (purged; use `.` before a capital, else `,`).

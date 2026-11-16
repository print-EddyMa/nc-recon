# Design - NC Recon

Locked design system for the NC Recon web app (`web/`) and site (`site/`).
`web/src/index.css` `:root` and `web/tailwind.config.js` are the source of
truth; amend there and here together. Screens **share** this system: a new
screen uses the kit in `web/src/components/ui/kit.tsx`, not its own look.

Last site pass: 2026-11-04 (Hallmark redesign in the launch film's language; see
**The site** below; the app and public pages are unchanged by it). Last full
pass: 2026-10-26 (de-AI pass after studying palantir.com,
nvidia.com and about.meta.com: one sans family for app and site, a light-first
site, short copy; public pages). Before that, 2026-10-23 (one brand with the
site: obsidian and limestone, cast bronze; public pages). Before that, 2026-10-22 (NC Recon
rename, operations-console redesign). The research behind it (FEMA lifelines
toolkit, WCAG 2.2, NASA Worldview, NN/g, USWDS) is summarised at the end.

---

## Direction

**A working instrument for people acting on a disaster.** County and state
emergency managers in an EOC, National Guard planners, search teams, insurers.
Every mark means one thing; every number carries its uncertainty and an
absolute as-of time; every screen says what to do next. The app's brand is the
North Carolina outline with a scan ring over the Triangle: it looks the same way every time.
The website has moved to the new mark, "the odd one out" (`docs/brand/`); the
app still carries the outline until it is changed on purpose.

- **Genre** · utilitarian instrument (operations console), not a dashboard of
  KPI cards
- **Macrostructure** · Workbench: top bar, rail (list) · map · inspector
  (tabs), status bar at the bottom
- **Mode** · light (limestone) and dark (obsidian), both first-class; system
  default. Dark is for the EOC wall and night shift (a dimmable dark theme, not
  a red-light mode: night-vision practice moved away from red).

## The frame (App shell)

- **Top bar, 48 px.** NC Recon mark + "NC Recon" (Public Sans, semibold); the four jobs: **Assess**,
  **Verify**, **Conditions**, **Help** (icon + label, accent underline on the
  current one); right side: data-source status (one dot summarising every
  feed, list on click), responder access (key), theme.
- **Status bar, bottom.** The standing disclaimer (`DISCLAIMER` in
  `lib/ops.ts`, never hard-coded) and the service connection. Always visible,
  never a yellow banner across the work.
- System panels (sources, access, accuracy) live in the frame, one click
  away, not at the bottom of a list.

## Assess (Operations)

| Column | Job | Primary action |
|---|---|---|
| Rail (288 px) | Which areas, worst first, grouped by event; jobs in progress | New assessment (`N`) |
| Map | What this area looks like, with its own imagery | Pick a structure |
| Inspector (408 px) | What to do next: Overview · Review · Respond · People · Checks | The next step, written out |

- **Area rows**: name, role tag (TEST / TUNE only), a damage strip of expected
  counts, `~N ≥ Major` and the review count in mono. Active row: accent-soft
  fill with a hairline ring (never a side stripe).
- **Overview tab**: two figures with ranges, the level table with inline
  bars, **Next steps** (review, brief, GIS), caveats folded.
- **Review tab**: queue rows carry the level as text and swatch (never colour
  alone), grid reference, probability and people; structure view with
  before/after chips, probability bar, why it needs a person, keyed label
  buttons.
- **Respond tab**: lifelines (status shape + colour), who is cut off (three
  scenarios), search priority by USNG 1 km square, landing candidates, supplies,
  losses and debris, KML plan. Its map layers appear only while it is open.
- **Checks tab**: every published field record or measurement that covers the
  area, each in the shape its data supports (agreement both ways, positives
  found, ground change), caveats always one click away.
- **New assessment**: four numbered steps beside the map (event, place,
  size, check and run); the event step can start from a FEMA disaster number
  and shows the draft before anything is registered.
- **Map controls**: imagery bar top-left (After · Before · **Swipe** · Map,
  with the capture date; hold `B` to flicker to before); legend bottom-left
  that is also the filter (click a level to hide it; "needs review only").

## 3D view (Assess, opt-in)

- A **2D / 3D** toggle in the imagery bar; 2D is the default and the choice
  is never remembered as a default. Terrain is a further opt-in inside 3D.
- Buildings are MapLibre fill-extrusions (they follow the terrain): height is
  inventory stories x 3 m, colour is the most likely FEMA level.
- **Height unknown** (about half the footprints) is drawn as a faint 0.5 m
  slab with a dashed outline and counted in the legend: never a default
  one-storey block.
- Terrain: AWS Terrain Tiles (terrarium), one constant `TERRAIN_HOST` in
  `components/map/useBuildings3D.ts`, matched by the server CSP. deck.gl's
  overlay is detached while terrain is on (it cannot follow MapLibre terrain).
- Swipe is unavailable in 3D; the camera tilts once, never rotates by itself,
  and does not animate under reduced motion.

## The site (`site/template.html`)

Cut like the launch film: near-black, hard cuts between bands, expanded type,
one orange. Marketing, not an instrument, so it may be loud where the app may
not; the honesty rules are the same.

- **Palette.** Paper `#0B0B0B`, ink `#F5F3EE`, signal `#FF5A1F`; dark only, no
  `prefers-color-scheme` switch. `.light` flips the surface tokens for one band
  (product, results, the pilot plan) and is the hard cut. Tokens stay hex: the
  WebGL and canvas code reads them, and three.js does not parse `oklch()`.
- **Orange is the signal, never severity.** It sits inside the damage ramp, so
  it stays off the map, the legend, the anatomy plates and the damage bars. It
  appears on the mark, the odd tile, the primary button, the third cut and the
  closing band. Map sectors and the home's outline are off-white.
- **Type.** Archivo for everything, self-hosted (`site/assets/web/fonts/`, OFL):
  display at `font-stretch` 116% and weight 720 (104% below 40rem, so words do
  not break), body at 100%. IBM Plex Mono 500 for figures that line up, grid
  references and code. Archivo has no arrows, so arrows are the CSS `.arr` mask.
- **Shape.** Square corners everywhere, like the tiles. Hover is a hard
  inversion with no transition.
- **Mark.** `site/logo.svg` is `docs/brand/app-icon.svg`; `mark()` in
  `site/build.py` writes the 3x3 tiles inline, ink in `currentColor`.
- **Hero tile wall.** One tile per building in the Swannanoa run, in the mark's
  proportions, read from `layers.json`. Tile order means nothing and carries no
  damage: all tiles are the same except the last, the showcase home. One sweep
  on load replays the run 40 times faster, and the caption says so; the count
  and clock end on the real 893 and 01:28. A ring follows the pointer on
  desktop. Reduced motion shows the final state.
- **The cut.** 893 buildings, 88 seconds, 1 laptop: three bands side by side,
  with the speed caveat under them.
- **No scroll animation.** Nothing is pinned, swapped, revealed or moved by
  scrolling, and anchors jump. The user finds it annoying; do not add it back.
- **Motion budget.** The hero sweep on load, and the anatomy stack, which
  lights a layer when a step is hovered, clicked or focused. Hero text uses `mix-blend-mode: difference` so it
  holds up while the ring passes under it.
- **Structure.** Hallmark: Marquee Hero, floating square bar (N5), statement
  footer (Ft5) that closes on "Verify on the ground".
- **Public-page limits.** No per-building geometry except the showcase home
  (17S LV 7253 4080); damage only as the 70 m smoothed density; no building
  views of TEST areas. Numbers keep their caveats beside them.

## Offline (field laptop)

- `lib/offline.ts` asks `GET /ops/offline` once at start-up and caches the
  answer; any failure means online. The map waits for it, so CARTO is never
  requested from an offline laptop.
- Base map offline: the packed USGS topo (`basemap.style_url`, its own
  attribution) or, with none packed, a plain background in the theme's canvas
  colour. The area's own imagery and 3D buildings work on either.
- An amber **Offline** chip in the top bar lists what is unavailable, in the
  server's words. New assessment (button and `N`), Terrain and Conditions are
  disabled with that reason, never hidden without one. Review and Verify show
  where offline labels end up. A 503 from the server shows its sentence.

## Colour

Tokens are space-separated `R G B` triples on `:root`, redeclared for dark
under `@media (prefers-color-scheme: dark) :root:not([data-theme=light])` and
`:root[data-theme=dark]`. Tailwind reads them as `rgb(var(--x) / <alpha>)`.

| Token | Light (limestone) | Dark (obsidian) | Role |
|---|---|---|---|
| `--canvas` | `#F4F2ED` | `#0A0A0A` | page ground |
| `--surface` | `#FBFAF7` | `#131312` | panels, bars |
| `--surface-2` | `#E9E6DF` | `#1C1C1A` | insets, tracks, skeletons |
| `--line` / `--line-strong` | `#DEDAD2` / `#BEB9AF` | `#282825` / `#403F3B` | hairlines |
| `--ink` / `-dim` / `-faint` | `#0F0F0E` / `#4A4742` / `#6A665F` | `#F5F3EE` / `#B6B3AC` / `#8A8780` | text |
| `--accent` | `#0F0F0E` ink | `#F5F3EE` | interaction: the selected tab, primary buttons |
| `--brand` | `#DE4812` | `#FF5A1F` | the odd tile of the NC Recon mark, and nothing else |
| `--review` | `#2563EB` | `#60A5FA` | needs-review outline: off the damage ramp, legible on imagery |
| `--st-ok/warn/bad/unknown` | green / amber / red / grey | lighter for dark | system and lifeline status in UI chrome |

**Accent discipline (2026-11-15, the brand pass).** Interaction is ink, as on
the site: near-black on paper, off-white on near-black. Signal orange is the
brand and appears only as the odd tile of the mark, never in the app's chrome
or on the map, because the FEMA damage ramp already uses orange and red. Titles
are Archivo, expanded (`.title-display`, `font-display`), the face of the site
and the launch film; text stays Public Sans and figures IBM Plex Mono. No
gradients, no glow, no glass, and no scroll-driven motion.

**Public pages** (`#/check`, `#/index`, `#/record/...`, `screens/public/Shell.tsx`)
keep the look of the 2026-10-26 site: a light sticky top bar, large medium-weight titles, black
pill buttons (`.btn-pill`), large fields (`.field-lg`), monochrome except for
damage data, and the disclaimer in the footer. They never show operator
chrome or anything that needs a token.

**The site** (`site/template.html`) has its own palette, from the launch
film; see **The site** below.

### Damage scale (data, identical in both themes)

FEMA five levels on ColorBrewer YlOrRd with a grey base: No damage `#9E9E9E`,
Affected `#FECC5C`, Minor `#FD8D3C`, Major `#F03B20`, Destroyed `#BD0026`;
Not assessed `#555555`. One sequential lightness ramp, so order survives every
colour-vision deficiency; adjacent levels are still close, so the level is
always also written as text. Fill opacity is confidence. Blue outline = needs
review.

### Lifeline status (Respond)

FEMA Community Lifelines Toolkit v2.1 colours, each paired with the shape
DHS S&T's lifeline tool uses, because FEMA red and green are hard to tell
apart for deuteranopes: Stable `#5E9C42` square · Strained `#FBBA16`
triangle · Disrupted `#C52038` inverted triangle · Unknown `#919395` circle
with "?". **Grey is unknown, never fine**, and is counted, not hidden.
FEMA's administrative blue is never used as a status.

### Conditions ramp (live feeds)

The cooler `NC_SEV_COLOR` ramp in `lib/nc.ts` stays separate from damage so
a flood gauge is never read as a destroyed building.

## Type

Bundled with `@fontsource` (works offline on a field laptop).

- **Public Sans** (variable) - all UI and body text; the US Web Design System
  face the government users already read. Headings are Public Sans at weight
  650, not a second typeface.
- **IBM Plex Mono** (400/500/600) - every figure in a column, grid references,
  times, keys. `.tnum` on anything that lines up.
- **One family.** Screen titles, the wordmark and public-page titles are Public
  Sans too (`.title-display`: semibold, tight tracking; big public titles
  medium weight). Palantir, NVIDIA and Meta each use one family; a display
  serif on dark read as a generated site. No Roman numerals or other
  ornament: steps are numbered 01, 02 in mono.

Sizes: body 14 px, dense panels 13 px, captions 11-12 px, inspector titles
18 px, figures 28 px mono. USNG at the precision the data supports (10 m for
an outline centroid, 1 km for sectors), never 1 m on a modelled point.

## Space, radius, elevation

- 4 px grid; controls 28 or 32 px tall; radius 6 px (4 px tags).
- `.panel` (hairline + soft shadow) only for things floating over the map;
  everything else is hairline-separated sections, no card-in-card.
- Dark mode elevation is surface lightness, not glow.

## Components (`web/src/components/ui/kit.tsx`)

`Button` (primary · secondary · ghost · danger; `kbd` hint; `busy`),
`Tag`, `Dot` (status), `Tabs` (arrow-key navigation, counts), `Segmented`,
`Disclosure`, `Popover` (outside click and Esc close), `Empty` (says what is
missing and the one next action), `DamageStrip`, `Swatch`, `Figure` (value +
80% range), `Kbd`, `Spinner`, `Icon` (hand-drawn 16 px set, 1.5 stroke,
currentColor). Form fields use `.field`.

Shared panels: `components/ops/SystemPanels.tsx` (sources, access, accuracy),
`components/ops/References.tsx` (Checks), `components/ops/Respond.tsx`,
`components/map/SwipeCompare.tsx`.

## Motion

- `--ease-out` for nearly everything, 130-450 ms; `transform`, `opacity`,
  `width` of data bars only.
- Map camera eases (350-450 ms) when the inspector asks it to look somewhere.
- Spinners only for work in flight; progress bars for jobs.
- Focus rings instant. `prefers-reduced-motion` drops everything to ~0 ms.
- No scroll-triggered fades, no count-ups on the operations screens, no motion
  library, no smooth-scroll library (the map owns the wheel).

## Interaction

- Keyboard: `N` new assessment, hold `B` before image, `0`-`4` label,
  `x` can't tell, `j`/`k` next/previous, `Esc` close or cancel.
- Silent success where the result is visible; toasts for background jobs,
  failures and effects you cannot see.
- Teach in empty states, not tours.
- Touch targets at least 24 px (WCAG 2.5.8); phone layout scrolls as one
  column with the map first and the legend folded.

## Copy

Plain, specific, sentence case; the real source name, the real number, the
real date. No em dashes. FEMA vocabulary for damage and lifelines. Estimates
say they are estimates where it matters: landing zones are reconnaissance
candidates, never approved LZs; the worst-case access scenario is a planning
bound, not a finding.

## Declined, and why

- Command palette, auto-tilt, auto-rotating cameras, count-ups: decoration on
  an instrument (the marketing site's one replay count is labelled as a replay). (3D is an opt-in view, below, never the default.)
- Cesium / Google 3D tiles and paid traffic: metered services and a second map
  engine.
- Red-only night mode: current night-vision practice; the dark theme is the
  night mode.

## Research behind this pass (2026-10-22)

- FEMA Community Lifelines Toolkit v2.1 (status colours p61, component
  analysis p23-24, grey = unknown p25):
  https://www.fema.gov/sites/default/files/documents/fema_lifelines-toolkit-v2.1_2023.pdf
- DHS S&T next-generation EOC and lifeline status shapes:
  https://www.dhs.gov/science-and-technology/news/2024/09/12/feature-article-how-st-supports-next-generation-emergency-operations-center
- WCAG 2.2 non-text contrast (3:1) and target size:
  https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html
- NASA Worldview comparison (swipe default):
  https://www.earthdata.nasa.gov/news/blog/introducing-worldviews-comparison-feature
- NN/g on empty states: https://www.nngroup.com/articles/empty-state-interface-design/
- USNG reading conventions: https://www.fgdc.gov/usng/how-to-read-usng
- USWDS colour grades and Public Sans: https://designsystem.digital.gov/design-tokens/color/overview/

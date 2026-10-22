# Design - Groma

Locked design system for the Groma web app (`web/`) and site (`site/`).
`web/src/index.css` `:root` and `web/tailwind.config.js` are the source of
truth; amend there and here together. Screens **share** this system: a new
screen uses the kit in `web/src/components/ui/kit.tsx`, not its own look.

Last full pass: 2026-10-22 (Groma rename, operations-console redesign). The
research behind it (FEMA lifelines toolkit, WCAG 2.2, NASA Worldview, NN/g,
USWDS) is summarised at the end.

---

## Direction

**A working instrument for people acting on a disaster.** County and state
emergency managers in an EOC, National Guard planners, search teams, insurers.
Every mark means one thing; every number carries its uncertainty and an
absolute as-of time; every screen says what to do next. The brand is the
Roman surveyor's groma: an instrument that measures the same way every time.

- **Genre** · utilitarian instrument (operations console), not a dashboard of
  KPI cards
- **Macrostructure** · Workbench: top bar, rail (list) · map · inspector
  (tabs), status bar at the bottom
- **Mode** · light (limestone) and dark (basalt), both first-class; system
  default. Dark is for the EOC wall and night shift (a dimmable dark theme, not
  a red-light mode: night-vision practice moved away from red).

## The frame (App shell)

- **Top bar, 48 px.** Groma mark + GROMA wordmark; the four jobs: **Assess**,
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

## Colour

Tokens are space-separated `R G B` triples on `:root`, redeclared for dark
under `@media (prefers-color-scheme: dark) :root:not([data-theme=light])` and
`:root[data-theme=dark]`. Tailwind reads them as `rgb(var(--x) / <alpha>)`.

| Token | Light (limestone) | Dark (basalt) | Role |
|---|---|---|---|
| `--canvas` | `#ECEEEA` | `#0D1012` | page ground |
| `--surface` | `#FAFBF8` | `#14191B` | panels, bars |
| `--surface-2` | `#E5E8E3` | `#1C2225` | insets, tracks, skeletons |
| `--line` / `--line-strong` | `#D6DBD5` / `#B7BEB8` | `#272F33` / `#3A454A` | hairlines |
| `--ink` / `-dim` / `-faint` | `#161B1D` / `#4C5552` / `#68716D` | `#E9E7E0` / `#A4A9A3` / `#7C837F` | text |
| `--accent` | `#2C7A66` verdigris | `#63B59C` | interaction and "this is live" only |
| `--brand` | `#8E5F27` bronze | `#C9954B` | the mark's plumb bobs only |
| `--review` | `#2563EB` | `#60A5FA` | needs-review outline: off the damage ramp, legible on imagery |
| `--st-ok/warn/bad/unknown` | green / amber / red / grey | lighter for dark | system and lifeline status in UI chrome |

**Accent discipline.** Verdigris is interaction, never severity, under ~5 % of
any view. No gradients, no glow, no glass.

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
- **Marcellus** - the GROMA wordmark and document titles only (`.title-display`).
  Roman inscriptional capitals: the brand's surveyor lineage. Never body text,
  never italic.

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

- Command palette, 3-D extrusion, auto-tilt, count-ups: decoration on an
  instrument.
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

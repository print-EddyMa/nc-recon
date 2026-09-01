# Phase G — kill AI-slop, add craft, verify nothing is broken

Working tree, branch `phase-cd-and-redesign`. A checkpoint commit
(`22d6942`) captured all Phase C–F work first, so Phase G has a rollback point.

---

## G0. Functional pass (before any visual work)

All green:

- `tsc -b` · `oxlint` · `vite build` — clean, **0 warnings**.
- Full Chrome sweep, 8 routes × light + dark (`web/scripts/qa_shots.mjs`) —
  **0 console / page errors**.
- Live feeds verified today through the server proxy: `GET /feed/{nwps,nws,nwis}`
  all return fresh data. The Aug-30/31 committed snapshots are fallback only, and
  the UI labels snapshot-vs-live ("feeds live" / "feeds cached" pill on Home;
  "committed snapshot" on the affected Live-map layers; ", cached" suffix on
  stat subtitles).
- **`/assess` re-verified end-to-end**: assessed a fresh Spruce Pine point
  (35.912, -82.075) via `HurricaneHelene-Oct24` → fusion backend (real xView2
  CMU classifier + change-detection), **147 buildings** {0:84, 1:42, 2:11, 3:10},
  NC priors applied (`in_fema_decl: true`), 532 + 532 tiles cut, 35 review /
  112 high, registry updated.
- **`spruce_pine_test` slug retired**: the old test area (name still carried
  "Test" in the URL slug `#/a/spruce_pine_test/...`) was replaced by the clean
  `spruce_pine` assessment above; its artifacts and registry entry were removed.
  Registry is now **Old Fort + Spruce Pine**, both with clean slugs.
- **Bug found and fixed while verifying that run — stale OSM footprint cache.**
  The first `/assess` for `spruce_pine` returned only 62 buildings. Root cause:
  `footprints.load_for_area` keyed the Overpass cache purely by area name
  (`{area}_osm.json`), so reusing an area name (an earlier `spruce_pine` run
  existed from Aug 29 with different AOI bounds) silently loaded the previous
  run's polygons with no error — `/assess` completing successfully is exactly
  the check that can't catch it. Fix: the cache key now includes an 8-char hash
  of the AOI bounds (`{area}_{bboxhash}_osm.json`). A fresh fetch for the same
  point then reproducibly returns 147, matching the earlier Spruce Pine
  assessment. `pipeline/src/terratriage/footprints.py`.
- No-key demo state checked: FIRMS and CLOUDS panels degrade to a legible
  "add a free key" prompt, not empty boxes.

## G1. Hallmark

Installed to `.agents/skills/hallmark/` (symlinked into `.claude/skills/`,
gitignored) via `npx skills add nutlope/hallmark`. Audit run manually against
its 58-gate slop test + `anti-patterns.md`. The per-genre subfolders did not
come down in the package; the top-level gate list and anti-pattern catalogue —
the substance of audit mode — are complete.

### Audit result

**Verdict: does not read as AI-generated.** One real fix, the rest are
documented deviations, not defects.

| Gate / tell | Result |
| --- | --- |
| 1 · Inter / system default display | **pass** — Archivo (display) + Geist (body), a deliberate pairing, not off either trend list |
| 2 · purple↔cyan gradient, gradient text | **pass** — grep-clean; one accent (blue `#2563EB`), zero gradient text, zero aurora blobs |
| 3 · 3-col icon-tile feature grid | **pass** — About's feed list is a typographic spec-sheet grid (label / name / prose), no icon-above-heading tiles |
| 4 · card-in-card | **pass** — one `.panel` containment layer |
| 5 · thick side-stripe card border | **pass** — hairline all four sides only |
| 6 · centred-everything hero | **pass** — Home hero is left-aligned and bottom-anchored (eyebrow + headline + priority line + CTAs all left); About hero left-aligned |
| 7 · pure #000 / #fff base | **deviation** — `--surface` is `#FFFFFF` in light mode (panels). The page *ground* `--canvas` is warm `#FAF9F6`. Allowed for the dashboard genre; recorded in DESIGN.md |
| 10 · `transition-all` | **fixed** — nav active-tab indicator was `transition-all duration-300`; now `transition-[transform,width]` |
| 11 · uniform `hover:scale` | **pass** — none in the codebase |
| 12 · bounce / overshoot easing on UI | **pass** — none; two `cubic-bezier` easings, both ease-out |
| 14 · animating width/left/margin | **deviation** — the 2px nav indicator transitions `width` alongside `translateX`; imperceptible on a hairline, kept for simplicity |
| 15 · focus ring fades in | **pass** — global `:focus-visible`, never transitioned |
| 16 · celebratory success toast | **pass** — toasts only for failures, background jobs, and "link copied" (an invisible effect) |
| 17 · tooltip hover-delay == focus-delay | **pass** — Radix tooltip: hover delay, focus 0 |
| 22 · zero-chroma neutrals | **pass** — neutrals carry a warm cast |
| 23 · accent > ~5% of viewport | **pass** — accent is buttons / links / active tab / selected building only |
| 24 · off-scale spacing | **minor** — a few deliberate one-offs (`h-[44vh]` hero, `text-[1.6rem]` stat figure, `-bottom-10` map bleed). Left as-is; each is intentional |
| 26 · missing `:focus-visible` / `:active` / `:disabled` | **pass** — `.pressable` + global focus rule |
| 27 · keyframe with no reduced-motion fallback | **pass** — global `prefers-reduced-motion` rule zeroes all animation; radar loop and `.reveal` also handled explicitly |
| 30 · mixed icon sets / emoji as icon | **deviation** — hand-built inline SVG everywhere except the ⌘K palette (`lucide-react`, caption size, one component). No emoji as functional icons. Recorded in DESIGN.md |
| 40–41 · contrast | **pass** — visual check across 8 routes × 2 themes, 0 issues; `--accent-ink` defined and applied on accent fills |
| 46 · invented metrics | **pass** — every figure (764 buildings, 161 review, 38% agreement, 0.13 km²) comes from the actual pipeline run |
| 47 · re-drawn browser / phone / IDE chrome | **pass** — none; review crops are real Maxar tiles in a plain frame |
| 34, 49 · horizontal scroll / two-line clickable text | **pass** — nav is a horizontal-scroll tab strip (no wrap); TopBar collapses to two rows on mobile (verified in earlier phases at 390px) |

## G2. Tells checked explicitly — all absent

Purple/indigo/violet · gradient text · gradient orbs · glassmorphism-everywhere
(4 purposeful `backdrop-blur` spots only) · neon-on-dark glow borders · the
"tasteful minimalist" cream+serif+sage cliché (this is warm-paper + grotesque +
blue, a different thing) · one-big-icon-above-every-heading · emoji as icons ·
same fade-in on every element (there is exactly one orchestrated entrance, on
Home) · dead hover states · snap-not-ease · vague marketing copy · invented
stats. Grep evidence in the commit.

## G3. DESIGN.md

Written at project root. **Transcribed** from the shipped implementation
(`web/src/index.css` custom-property triples, `tailwind.config.js`,
`lib/damage.ts`, `lib/nc.ts`) — not a redesign. Locks: the emergency-response
cartography direction, the full light/dark colour table with hex values, the
two damage/severity ramps, the Archivo + Geist + Geist Mono pairing, the
radius / border / elevation rules, and the motion rules.

**Lenis + GSAP ScrollTrigger — deliberately declined**, with the reason in
DESIGN.md § Motion: five surfaces own the wheel (MapLibre `scrollZoom` on the
Home hero / Live map / Assess / Damage map, plus the History timeline's
hand-rolled wheel-zoom), and a global smooth-scroll layer would fight all of
them and add input lag. Scroll stays native.

## G4. Craft added

- **`web/src/lib/useCountUp.ts`** + **`web/src/components/StatNumber.tsx`** — a
  ~30-line hook (no library), cubic ease-out, ~600 ms. It animates the **first**
  transition to a real value, then every later change **snaps** — so rapid
  Approve clicks on the Review headline land the true count immediately instead
  of restarting a roll. Wired into the Home status tiles, the Summary headline
  figure and its lead percentage, and the Review backlog count. Non-numeric
  values ("off", "…") pass through untouched. Reduced-motion returns the value
  with no animation. A React `key` (area switch) gives a fresh count-up.
- **One orchestrated entrance** — `.reveal` keyframe in `index.css` (`opacity` +
  4px `translateY`, 320 ms), applied with a 45 ms stagger to the Home status
  tiles and assessed-area cards. Home only; no other screen animates on mount.
- **No motion library added.** `motion` / `framer-motion` / `gsap` / `lenis`
  are not dependencies. `npm audit` stays at 0; Home bundle stays gzip ~389 KB.

## G5. Re-validation

- `tsc -b` · `oxlint` · `vite build` — clean, **0 warnings**, after all edits.
- `qa_shots.mjs` extended to also render the second assessed area
  (`#/a/spruce_pine/{map,review,stats}`) — it had only ever swept `old_fort`.
  Full run: **11 routes × light + dark, 0 console / page errors.** The
  `spruce_pine` deck.gl extrusion (147 features) and the Review crop
  404 → zoom-out retry both render.
- Count-ups and the Home stagger verified in the rendered app (light + dark).
- `prefers-reduced-motion` block also zeroes `animation-delay` now, so the Home
  stagger doesn't hold tiles blank through their delay under that setting.

### One-sentence identity

TerraTriage looks like a government field instrument — warm paper, a single
blue "this is live" accent, a fixed FEMA-style green→red damage ramp, a squared
grotesque over a humanist sans, and hand-drawn contour textures — not a
landing-page template.

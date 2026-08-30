# Design skills — what was pulled in

Source: `~/Downloads/Pulse-main-6/.agents/skills/` (≈30 community design skills
from GitHub: `emilkowalski/skill`, `Leonxlnx/taste-skill`,
`nextlevelbuilder/ui-ux-pro-max-skill`, `dickwu/apple-design-skill`). They are
not installed as Claude Code skills, so the relevant `SKILL.md` files were read
and their guidance applied directly to `web/`.

## Applied

**`redesign-existing-projects` — the AI-pattern audit** (primary reference)
- Font swap: **Inter → Geist** (body/UI), **IBM Plex Mono → Geist Mono** (data).
  Space Grotesk kept for display. Geist has character and ships tabular figures.
- Killed the hairline-divider stat grid on the landing (a "broadsheet" tell) —
  now left-border stat ticks with real whitespace.
- `:active` press feedback on every button (`.pressable` → `scale(0.97)`).
- Custom easing tokens (`--ease-out`, `--ease-in-out`, `--ease-drawer`) replacing
  weak built-in curves; applied to buttons, toggles, bars, slider thumb.
- Tinted shadows (`--shadow-1/2`, carry the canvas hue, never flat black).
- `scroll-behavior: smooth`, `text-wrap: balance` on headings, `pretty` on `<p>`.
- Faint SVG film-grain overlay (fixed, `pointer-events:none`, 2.5% opacity) so
  surfaces read as physical rather than vector-flat.
- Meta tags: description, `og:*`, `twitter:card`, `theme-color`, generated
  `og-image.png`.
- Semantic landmarks (`<main id="main">`), skip-to-content link.
- Softened radius scale: containers `rounded-lg`, inner elements `rounded-md`.

**`emil-design-eng` — motion craft**
- Never animate `scale(0)`; entrances start at `scale(0.985)` + opacity
  (`.enter-pop` on the selected-building card).
- Staggered list entrance (`.stagger`, 40ms steps) on the ranked-cluster list and
  landing stats.
- Durations kept ≤ 300ms for UI; `ease-out` for enters, no `ease-in`.
- Button-in-button trailing icon on the primary CTA.

**`apple-design` — materials & type**
- Translucent panels (`backdrop-filter: blur`) as a floating layer, not opaque
  bars; scroll-edge fade on the map attribution instead of a hard divider.
- Negative tracking on display type (`-0.02em`), tabular mono for all figures.
- `prefers-reduced-motion` gates every animation *and* the deck.gl / camera
  transitions (in `DeckMap` via `lib/motion.ts`); reduced-motion also flattens
  `.stagger`.

## Deliberately NOT applied

**`high-end-visual-design` ("$150k agency" maximalism)** — its core moves
(radial mesh-gradient orbs, glass "double-bezel" nested enclosures, `-2deg` card
rotations, `py-40` sections, Awwwards-tier scroll choreography) would make a
rescue-coordination tool read as *more* trend-chasing, which is the opposite of
the goal. The build brief's anti-AI move was to ground the design in real
emergency-response cartography (USGS / NOAA / FEMA), and that's kept. Craft,
motion, and typography lessons were taken; the decorative agency tropes were not.

---

## Second pass — 2026-08-30 (de-AI the Phase C/D screens)

Re-ran the `redesign-existing-projects` audit + `ui-ux-pro-max` after Phases C/D
added Live Monitor, Review queue, the event picker and the assess panel — parts
built faster than the original landing.

Design read: *redesign of an emergency-response operational tool, trust-first /
control-room, one type family, low motion, data-dense; preserve not overhaul.*

Fixed:
- **Emoji as icons** (🌀🔥🌊⚡ in the picker / live monitor / assess panel) →
  `components/HazardIcon.tsx`, one schematic 1.5px-stroke line-icon per hazard
  family, `currentColor`.
- **Space Grotesk display face** (the "vibe-coded 2024" pairing with Geist) →
  **Archivo**. One type family: Archivo display, Geist body, Geist Mono figures.
- **Generic bordered cards** (border + shadow + bg) on Summary and Review, and
  the "four equal stat tiles in a row" → asymmetric figure block (lead % +
  left-border ticks) on Summary; a hairline-divided worklist on Review. `.panel`
  is now used only where it floats over the map (elevation earns its keep).
- **Red score bars** on the map cluster list collided with the damage ramp's
  meaning → new neutral `meter` token; red is now exclusively per-building damage.
- **ALL-CAPS as a section-header device** → `.section-title` (sentence case, in
  the display face). `.cap` kept for true legend micro-labels only.
- **"Loading…" text** → `.skel` skeleton blocks shaped like the panels/rows.
- **Raw model slug** (`fusion:cmu-classifier + …`) on the polished Summary →
  `modelLabel()` renders it as prose.
- **Unicode glyph chevrons** (`›`, `▸`) → inline SVG.
- Landing: strengthened the topographic backdrop + a single soft ambient light
  (skill: "empty flat sections with no visual depth").
- Nav: one indicator that **slides** between the active tab (CSS transition, no
  animation library) — the one transferable idea from the pill-nav components
  that were suggested.

## Still deliberately NOT applied

Three 21st.dev components were suggested during this pass (a `motion/react` pill
nav, a scroll-locked video hero, a list/card/"pack" layout switcher). Declined:
each adds a heavy dependency (`motion/react`, `lucide-react`, `@hugeicons`) and
is built for a different context (SaaS dashboard, NFT gallery, marketing). A
scroll-hijacking cinematic hero in particular is the decorative landing-page
aesthetic the build brief names as the top risk to the judging score. Took the
one good idea (sliding active-tab indicator), implemented natively.

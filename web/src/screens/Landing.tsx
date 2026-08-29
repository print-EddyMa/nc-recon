import { useMemo } from "react";
import { summarize } from "../lib/data";
import type { AreaConfig, DamageCollection } from "../lib/types";
import { DAMAGE } from "../lib/damage";

interface Props {
  area: AreaConfig;
  fc: DamageCollection | null;
  onEnter: () => void;
}

export default function Landing({ area, fc, onEnter }: Props) {
  const stats = useMemo(() => (fc ? summarize(fc) : null), [fc]);

  return (
    <div className="relative flex min-h-full flex-col">
      {/* faint contour backdrop */}
      <Contours />

      <div className="relative mx-auto flex w-full max-w-5xl flex-1 flex-col px-6 py-10 md:py-16">
        <div className="cap mb-6 flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-accent" />
          Rapid damage assessment · Hurricane Helene · Sept–Oct 2024
        </div>

        <h1 className="max-w-3xl font-display text-4xl leading-[1.05] text-ink md:text-6xl">
          Every building, triaged from orbit.
        </h1>

        <p className="mt-5 max-w-2xl text-[15px] leading-relaxed text-ink-dim">
          Hurricane Helene pushed the Swannanoa and North Toe rivers through the mountain
          towns of western North Carolina, cutting road access for days. TerraTriage pairs
          pre- and post-storm satellite imagery, finds every structure, and rates its damage
          on a four-level scale &mdash; turning two photographs into a map a response
          coordinator can act on.
        </p>

        <div className="mt-8 flex flex-wrap items-center gap-3">
          <button
            onClick={onEnter}
            className="rounded-sm bg-accent px-5 py-2.5 text-sm font-semibold text-[#05171a] transition-transform hover:-translate-y-0.5"
          >
            Open the damage map →
          </button>
          <span className="tnum text-xs text-ink-faint">
            {area.name}, {area.subtitle}
          </span>
        </div>

        {/* headline stat strip */}
        <div className="mt-12 grid grid-cols-2 gap-px overflow-hidden rounded-sm border border-line bg-line sm:grid-cols-4">
          <HeroStat label="Buildings assessed" value={stats ? stats.total.toLocaleString() : "—"} />
          <HeroStat
            label="Major or destroyed"
            value={stats ? `${stats.severePct.toFixed(0)}%` : "—"}
            accent={DAMAGE[2].hex}
          />
          <HeroStat
            label="Footprint area"
            value={stats ? `${stats.assessedAreaKm2.toFixed(1)} km²` : "—"}
          />
          <HeroStat label="Damage levels" value="4" />
        </div>

        <p className="mt-6 max-w-2xl text-xs leading-relaxed text-ink-faint">
          Imagery: Maxar Open Data. Footprints: OpenStreetMap. Damage model:{" "}
          {fc?.properties.model ?? "—"}
          {fc?.properties.notes ? ` — ${fc.properties.notes}` : ""}
        </p>
      </div>
    </div>
  );
}

function HeroStat({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="bg-surface px-4 py-4">
      <div className="cap mb-1.5">{label}</div>
      <div className="tnum text-2xl font-semibold" style={accent ? { color: accent } : undefined}>
        {value}
      </div>
    </div>
  );
}

function Contours() {
  return (
    <svg
      aria-hidden
      className="pointer-events-none absolute inset-0 h-full w-full opacity-[0.07]"
      preserveAspectRatio="xMidYMid slice"
      viewBox="0 0 800 600"
    >
      {Array.from({ length: 14 }).map((_, i) => (
        <path
          key={i}
          d={`M-50 ${80 + i * 40} C 150 ${20 + i * 40}, 300 ${140 + i * 40}, 500 ${70 + i * 40} S 850 ${30 + i * 40}, 900 ${90 + i * 40}`}
          fill="none"
          stroke="#3fb6c4"
          strokeWidth="1"
        />
      ))}
    </svg>
  );
}

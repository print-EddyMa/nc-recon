import { useMemo } from "react";
import { summarize } from "../lib/data";
import type { AreaConfig, DamageCollection } from "../lib/types";
import { DAMAGE } from "../lib/damage";
import BeforeAfterImage from "../components/BeforeAfterImage";

interface Props {
  area: AreaConfig;
  fc: DamageCollection | null;
  onEnter: () => void;
}

export default function Landing({ area, fc, onEnter }: Props) {
  const stats = useMemo(() => (fc ? summarize(fc) : null), [fc]);

  return (
    <main id="main" className="relative min-h-full overflow-y-auto">
      <Contours />

      <div className="relative mx-auto w-full max-w-6xl px-6 py-12 md:py-16">
        <p className="cap mb-7 flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-accent" />
          Rapid damage assessment · Hurricane Helene · Sept 2024
        </p>

        <div className="grid items-start gap-12 md:grid-cols-[1.05fr_0.95fr]">
          <div>
            <h1 className="font-display text-[2.5rem] leading-[1.04] text-ink md:text-[3.5rem]">
              Every building, triaged from orbit.
            </h1>

            <p className="mt-6 max-w-[46ch] text-[0.95rem] leading-relaxed text-ink-dim">
              Hurricane Helene pushed the Swannanoa and North Toe rivers through the
              mountain towns of western North Carolina, cutting road access for days.
              TerraTriage pairs pre- and post-storm satellite imagery, finds every
              structure, and rates its damage on a four-level scale — turning two
              photographs into a map a response coordinator can act on.
            </p>

            <div className="mt-8 flex flex-wrap items-center gap-4">
              <button
                onClick={onEnter}
                className="pressable group inline-flex items-center gap-2.5 rounded-full bg-accent py-2.5 pl-5 pr-2.5 text-sm font-semibold text-[#05171a]"
              >
                Open the damage map
                <span className="grid h-7 w-7 place-items-center rounded-full bg-[#05171a]/12 transition-transform duration-200 ease-out group-hover:translate-x-0.5">
                  <svg width="13" height="13" viewBox="0 0 16 16" fill="none" aria-hidden>
                    <path
                      d="M3 8h10M9 4l4 4-4 4"
                      stroke="currentColor"
                      strokeWidth="1.7"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </span>
              </button>
              <span className="tnum text-xs text-ink-faint">
                {area.name}, {area.subtitle}
              </span>
            </div>
          </div>

          <BeforeAfterImage
            area={area}
            preDate={fc?.properties.pre_image.date}
            postDate={fc?.properties.post_image.date}
          />
        </div>

        <dl className="stagger mt-14 grid grid-cols-2 gap-x-10 gap-y-6 sm:grid-cols-4">
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
        </dl>

        <p className="mt-8 max-w-[68ch] text-xs leading-relaxed text-ink-faint">
          Imagery from Maxar Open Data, building footprints from OpenStreetMap. Damage
          is classified by the xView2 CMU baseline model — a per-building
          post-image classifier trained on the xBD dataset, not the competition's
          1st-place ensemble.
        </p>
      </div>
    </main>
  );
}

function HeroStat({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="border-l border-line pl-3.5">
      <dt className="cap mb-1.5">{label}</dt>
      <dd className="tnum m-0 text-2xl font-semibold" style={accent ? { color: accent } : undefined}>
        {value}
      </dd>
    </div>
  );
}

function Contours() {
  return (
    <svg
      aria-hidden
      className="pointer-events-none absolute inset-0 h-full w-full opacity-[0.06]"
      preserveAspectRatio="xMidYMid slice"
      viewBox="0 0 800 600"
    >
      {Array.from({ length: 16 }).map((_, i) => (
        <path
          key={i}
          d={`M-50 ${70 + i * 38} C 160 ${10 + i * 38 + (i % 3) * 12}, 300 ${150 + i * 38}, 520 ${60 + i * 38} S 860 ${20 + i * 38}, 900 ${88 + i * 38}`}
          fill="none"
          stroke="#3fb6c4"
          strokeWidth={i % 4 === 0 ? 1.4 : 0.8}
        />
      ))}
    </svg>
  );
}

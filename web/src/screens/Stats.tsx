import { useMemo } from "react";
import { summarize } from "../lib/data";
import { DAMAGE } from "../lib/damage";
import StatTile from "../components/StatTile";
import type { AreaConfig, DamageCollection } from "../lib/types";

interface Props {
  area: AreaConfig;
  fc: DamageCollection | null;
  onOpenMap: () => void;
}

export default function Stats({ area, fc, onOpenMap }: Props) {
  const stats = useMemo(() => (fc ? summarize(fc) : null), [fc]);
  if (!fc || !stats) {
    return <div className="grid h-full place-items-center"><span className="cap animate-pulse">Loading…</span></div>;
  }
  const total = stats.total || 1;
  const p = fc.properties;

  return (
    <div className="mx-auto h-full max-w-4xl overflow-y-auto px-6 py-8">
      <div className="cap mb-2">Summary · {area.name}, {area.subtitle}</div>
      <h1 className="font-display text-3xl text-ink">
        <span className="tnum text-dmg2">{stats.severe.toLocaleString()}</span> of{" "}
        <span className="tnum">{stats.total.toLocaleString()}</span> buildings sustained major
        damage or were destroyed.
      </h1>
      <p className="mt-3 max-w-2xl text-sm text-ink-dim">
        Assessment of Hurricane Helene (landfall 26 Sep 2024) from Maxar Open Data captures on{" "}
        <span className="tnum">{p.pre_image.date}</span> (before) and{" "}
        <span className="tnum">{p.post_image.date}</span> (after).
      </p>

      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile label="Buildings assessed" value={stats.total.toLocaleString()} />
        <StatTile
          label="Severe (major + destroyed)"
          value={`${stats.severePct.toFixed(1)}%`}
          sub={`${stats.severe.toLocaleString()} structures`}
          accent={DAMAGE[2].hex}
        />
        <StatTile label="Footprint area" value={`${stats.assessedAreaKm2.toFixed(2)} km²`} />
        <StatTile
          label="Destroyed"
          value={stats.counts[3].toLocaleString()}
          sub={`${((stats.counts[3] / total) * 100).toFixed(1)}% of all buildings`}
          accent={DAMAGE[3].hex}
        />
      </div>

      <div className="mt-8 panel px-4 py-4">
        <div className="cap mb-3">Distribution by damage level</div>
        <div className="space-y-2.5">
          {DAMAGE.map((d) => {
            const n = stats.counts[d.index];
            const pct = (n / total) * 100;
            return (
              <div key={d.index} className="flex items-center gap-3">
                <span className="w-24 text-xs text-ink-dim">{d.label}</span>
                <span className="relative h-5 flex-1 overflow-hidden rounded-sm bg-surface-2">
                  <span
                    className="absolute inset-y-0 left-0 transition-[width] duration-500 ease-out"
                    style={{ width: `${Math.max(pct, 0.6)}%`, background: d.hex }}
                  />
                </span>
                <span className="tnum w-16 text-right text-sm text-ink">{n}</span>
                <span className="tnum w-14 text-right text-xs text-ink-faint">
                  {pct.toFixed(1)}%
                </span>
              </div>
            );
          })}
        </div>
      </div>

      <div className="mt-6 flex flex-wrap items-center gap-3 text-xs text-ink-faint">
        <button
          onClick={onOpenMap}
          className="pressable rounded-md border border-line px-3 py-1.5 text-ink-dim hover:border-accent hover:text-ink"
        >
          View on map →
        </button>
        <span>
          Model: {p.model}
          {p.runtime_sec ? ` · ${p.runtime_sec}s` : ""}
        </span>
        {p.notes && <span className="text-dmg1">{p.notes}</span>}
      </div>
    </div>
  );
}

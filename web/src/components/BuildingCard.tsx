import { DAMAGE } from "../lib/damage";
import type { BuildingFeature } from "../lib/types";

interface Props {
  feature: BuildingFeature;
  onClear: () => void;
}

export default function BuildingCard({ feature, onClear }: Props) {
  const p = feature.properties;
  const d = DAMAGE[p.damage_class];
  return (
    <div className="panel px-3 py-3" style={{ borderColor: d.hex }}>
      <div className="flex items-start justify-between">
        <div>
          <div className="cap">Selected building</div>
          <div className="tnum text-sm text-ink">{p.id}</div>
        </div>
        <button
          onClick={onClear}
          className="text-ink-faint hover:text-ink"
          aria-label="Clear selection"
        >
          ✕
        </button>
      </div>
      <div className="mt-2 flex items-center gap-2">
        <span className="h-3 w-3 rounded-[2px]" style={{ background: d.hex }} />
        <span className="text-sm font-medium" style={{ color: d.hex }}>
          {d.label}
        </span>
      </div>
      <p className="mt-1.5 text-xs leading-relaxed text-ink-dim">{d.blurb}</p>
      <dl className="mt-2.5 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
        <div className="flex justify-between">
          <dt className="text-ink-faint">Footprint</dt>
          <dd className="tnum text-ink">{p.area_m2.toFixed(0)} m²</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-ink-faint">Confidence</dt>
          <dd className="tnum text-ink">{(p.confidence * 100).toFixed(0)}%</dd>
        </div>
        <div className="col-span-2 flex justify-between">
          <dt className="text-ink-faint">Location</dt>
          <dd className="tnum text-ink">
            {p.centroid[1].toFixed(5)}, {p.centroid[0].toFixed(5)}
          </dd>
        </div>
      </dl>
    </div>
  );
}

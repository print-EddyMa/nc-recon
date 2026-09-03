import { useMemo, useState } from "react";
import { heroTileUrl, tileForLonLat, summarize } from "../lib/data";
import { DAMAGE } from "../lib/damage";
import { useReviewDecisions, overrideClasses } from "../lib/review";
import { Tooltip } from "../components/ui/Tooltip";
import StatNumber from "../components/StatNumber";
import AreaLoadError from "../components/AreaLoadError";
import type { ReviewDecision } from "../lib/review";
import type {
  AreaConfig,
  BuildingFeature,
  DamageClass,
  DamageCollection,
} from "../lib/types";

interface Props {
  area: AreaConfig;
  fc: DamageCollection | null;
  loadError?: string | null;
  onRetry?: () => void;
  onOpenMap: () => void;
}

const CROP_Z = 17;
const CROP_PX = 156;
const SCALE = 2.4;

function Crop({
  areaId,
  kind,
  lon,
  lat,
  label,
}: {
  areaId: string;
  kind: "pre" | "post";
  lon: number;
  lat: number;
  label: string;
}) {
  // start tight (CROP_Z); on a 404 (edge buildings can fall outside the cut
  // tiles) step out one zoom, which covers 4× the area
  const [zoomOut, setZoomOut] = useState(0);
  const z0 = CROP_Z - zoomOut;
  const { z, x, y, fx, fy } = tileForLonLat(lon, lat, z0);
  const size = 256 * SCALE;
  const tx = Math.max(Math.min(fx * size - CROP_PX / 2, size - CROP_PX), 0);
  const ty = Math.max(Math.min(fy * size - CROP_PX / 2, size - CROP_PX), 0);
  return (
    <figure
      className="relative m-0 overflow-hidden rounded-sm bg-surface-2"
      style={{ width: CROP_PX, height: CROP_PX }}
    >
      <img
        key={z0}
        // ?empty=1 → the server hands back a 1x1 blank instead of a 404 for an
        // edge building outside the cut tiles; we detect that on load and step
        // out a zoom, so the console stays clean
        src={`${heroTileUrl(areaId, kind, [z, x, y])}?empty=1`}
        alt={`${label} crop of the building`}
        draggable={false}
        crossOrigin="anonymous"
        style={{ position: "absolute", width: size, height: size, left: -tx, top: -ty, maxWidth: "none" }}
        onLoad={(e) => {
          if (e.currentTarget.naturalWidth <= 1 && zoomOut < 3) setZoomOut((n) => n + 1);
        }}
        onError={(e) => {
          if (zoomOut < 3) setZoomOut((n) => n + 1);
          else e.currentTarget.style.visibility = "hidden";
        }}
      />
      <span className="absolute left-1 top-1 rounded-sm bg-canvas/80 px-1 py-0.5 text-[10px] uppercase tracking-wider text-ink-dim">
        {label}
      </span>
      <span
        className="pointer-events-none absolute left-1/2 top-1/2 h-6 w-6 -translate-x-1/2 -translate-y-1/2 rounded-full border border-accent/80"
        aria-hidden
      />
    </figure>
  );
}

export default function ReviewQueue({ area, fc, loadError, onRetry, onOpenMap }: Props) {
  const { decisions, setDecision, clearAll } = useReviewDecisions(area.id);
  const [showResolved, setShowResolved] = useState(false);
  const PAGE = 60;
  const [limit, setLimit] = useState(PAGE);

  const queue = useMemo(() => {
    if (!fc) return [];
    return fc.features
      .filter((f) => f.properties.confidence_tier === "review")
      .sort((a, b) => b.properties.area_m2 - a.properties.area_m2);
  }, [fc]);

  // the area is remounted via key= from App, so `limit` only needs a manual
  // reset when the "show resolved" filter flips
  const toggleResolved = () => {
    setShowResolved((v) => !v);
    setLimit(PAGE);
  };

  const filtered = showResolved ? queue : queue.filter((f) => !decisions[f.properties.id]);
  const visible = filtered.slice(0, limit);
  const rawStats = useMemo(() => (fc ? summarize(fc) : null), [fc]);
  const overrideStats = useMemo(
    () => (fc ? summarize(fc, overrideClasses(decisions)) : null),
    [fc, decisions],
  );

  if (loadError && !fc) {
    return <AreaLoadError areaName={area.name} detail={loadError} onRetry={onRetry ?? (() => {})} />;
  }

  if (!fc) {
    return (
      <div className="mx-auto max-w-4xl px-6 py-10">
        <div className="skel h-4 w-56" />
        <div className="skel mt-4 h-9 w-96" />
        <div className="mt-8 space-y-4">
          {[0, 1, 2].map((i) => (
            <div key={i} className="skel h-40" />
          ))}
        </div>
      </div>
    );
  }

  const resolved = queue.length - queue.filter((f) => !decisions[f.properties.id]).length;
  const open = queue.length - resolved;

  // buildings where the second pass actually agrees with the model, safe to
  // clear in bulk (they were flagged only for a low decision margin)
  const agreeing = queue.filter((f) => {
    const s = f.properties.sources;
    return s && s.heuristic === s.cnn && !decisions[f.properties.id];
  });

  const approveMany = (list: typeof queue) => {
    const at = Date.now();
    for (const f of list) setDecision(f.properties.id, { action: "approve", at });
  };

  const exportDecisions = () => {
    const rows = Object.entries(decisions).map(([id, d]) => ({
      id,
      action: d.action,
      override_class: d.damage_class ?? null,
      at: new Date(d.at).toISOString(),
    }));
    const blob = new Blob([JSON.stringify({ area: area.id, decisions: rows }, null, 2)], {
      type: "application/json",
    });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `nc-recon-review-${area.id}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const pctDone = queue.length ? Math.round((resolved / queue.length) * 100) : 0;
  const rail = (
    <div className="card p-4">
      <div className="cap mb-1.5">Review progress</div>
      <div className="tnum font-display text-2xl font-semibold text-ink">
        {resolved.toLocaleString()}
        <span className="text-base text-ink-faint"> / {queue.length.toLocaleString()}</span>
      </div>
      <div className="bar-track mt-2 h-1.5">
        <span className="bar-fill block h-full bg-accent" style={{ width: `${pctDone}%` }} />
      </div>
      {rawStats && overrideStats && (
        <div className="tnum mt-3 flex items-baseline justify-between border-t border-line pt-3 text-xs">
          <span className="text-ink-dim">Severe count</span>
          <span className="font-medium text-ink">
            {rawStats.severe.toLocaleString()}
            {overrideStats.severe !== rawStats.severe && (
              <>
                {" → "}
                <span className="text-dmg2">{overrideStats.severe.toLocaleString()}</span>
              </>
            )}
          </span>
        </div>
      )}
      <div className="mt-3 flex flex-col gap-1.5 border-t border-line pt-3 text-xs">
        <label className="flex items-center gap-2 text-ink-faint">
          <input
            type="checkbox"
            className="accent-accent"
            checked={showResolved}
            onChange={toggleResolved}
          />
          Show resolved
        </label>
        {agreeing.length > 0 && (
          <button
            onClick={() => approveMany(agreeing)}
            className="pressable mt-1 rounded-md border border-line px-2.5 py-1.5 text-left text-ink-dim hover:border-line-strong hover:text-ink"
          >
            Approve {agreeing.length} where both passes agree
          </button>
        )}
        <div className="mt-1 flex gap-3 text-ink-faint">
          {resolved > 0 && (
            <>
              <button onClick={exportDecisions} className="pressable hover:text-ink">
                Export
              </button>
              <button onClick={clearAll} className="pressable hover:text-ink">
                Reset
              </button>
            </>
          )}
          <button onClick={onOpenMap} className="pressable ml-auto text-ink-dim hover:text-ink">
            View on map →
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto grid w-full max-w-6xl gap-x-12 gap-y-6 px-6 py-10 xl:grid-cols-[minmax(0,1fr)_16rem]">
        <div className="min-w-0">
          <p className="eyebrow mb-3">
            Human review · {area.name}
            {area.subtitle ? `, ${area.subtitle}` : ""}
          </p>
          <h1 className="font-display text-display-s font-semibold text-ink">
            <StatNumber value={open} className="tnum text-dmg1" /> building
            {open === 1 ? "" : "s"} need a second look
          </h1>
          <p className="measure mt-4 text-sm leading-relaxed text-ink-dim">
            Buildings where the CNN classifier and an independent change-detection pass landed two or
            more damage levels apart, plus a few whose footprint is too small to read. Confirm the
            model&rsquo;s call, or override it by eye from the pre and post crop.
          </p>

          {/* rail moves inline above the list below xl */}
          <div className="mt-6 xl:hidden">{rail}</div>

          {visible.length === 0 ? (
            <p className="mt-12 text-center text-sm text-ink-dim">
              {queue.length === 0
                ? "No buildings were flagged for review in this area."
                : "Every flagged building has been reviewed."}
            </p>
          ) : (
            <>
              <ul className="mt-6 border-t border-line xl:mt-8">
                {visible.map((f) => (
                  <ReviewRow
                    key={f.properties.id}
                    feature={f}
                    areaId={area.id}
                    decision={decisions[f.properties.id] ?? null}
                    onDecide={(d) => setDecision(f.properties.id, d)}
                  />
                ))}
              </ul>
              {filtered.length > visible.length && (
                <div className="mt-6 flex items-center justify-center gap-3 text-xs text-ink-faint">
                  <span className="tnum">
                    showing {visible.length.toLocaleString()} of {filtered.length.toLocaleString()}
                  </span>
                  <button
                    onClick={() => setLimit((n) => n + PAGE)}
                    className="pressable rounded-md border border-line px-3 py-1.5 text-ink-dim hover:border-line-strong hover:text-ink"
                  >
                    Load {Math.min(PAGE, filtered.length - visible.length)} more
                  </button>
                </div>
              )}
            </>
          )}
        </div>

        <aside className="hidden xl:sticky xl:top-6 xl:block xl:self-start">{rail}</aside>
      </div>
    </div>
  );
}

const CheckMark = () => (
  <svg width="11" height="11" viewBox="0 0 12 12" fill="none" aria-hidden>
    <path d="M2 6.5 4.7 9 10 3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
const XMark = () => (
  <svg width="10" height="10" viewBox="0 0 12 12" fill="none" aria-hidden>
    <path d="M3 3l6 6M9 3l-6 6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
  </svg>
);

function ReviewRow({
  feature,
  areaId,
  decision,
  onDecide,
}: {
  feature: BuildingFeature;
  areaId: string;
  decision: ReviewDecision | null;
  onDecide: (d: ReviewDecision | null) => void;
}) {
  const p = feature.properties;
  const [lon, lat] = p.centroid;
  const model = DAMAGE[p.damage_class];
  const s = p.sources;
  const now = () => Date.now();

  return (
    <li className="flex flex-col gap-4 border-b border-line py-5 last:border-0 sm:flex-row">
      <div className="flex gap-2">
        <Crop areaId={areaId} kind="pre" lon={lon} lat={lat} label="Before" />
        <Crop areaId={areaId} kind="post" lon={lon} lat={lat} label="After" />
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <span className="tnum text-xs text-ink-dim">{p.id}</span>
          <span className="tnum text-2xs text-ink-faint">{p.area_m2.toFixed(0)} m²</span>
        </div>

        <dl className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
          <div className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-[2px]" style={{ background: model.hex }} />
            <span style={{ color: model.hex }}>Model · {model.label}</span>
          </div>
          {s && (
            <>
              <span className="tnum text-ink-faint">
                Change-detection · {DAMAGE[s.heuristic as DamageClass]?.label ?? s.heuristic}
              </span>
              <span className={`tnum ${s.cnn === s.heuristic ? "text-ink-faint" : "text-dmg1"}`}>
                {s.cnn === s.heuristic ? "passes agree" : "passes disagree"}
              </span>
            </>
          )}
        </dl>

        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <button
            onClick={() =>
              onDecide(decision?.action === "approve" ? null : { action: "approve", at: now() })
            }
            aria-pressed={decision?.action === "approve"}
            className={`pressable inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs ${
              decision?.action === "approve"
                ? "border-accent bg-accent/15 text-ink"
                : "border-line text-ink-dim hover:text-ink"
            }`}
          >
            <CheckMark /> Approve
          </button>
          <button
            onClick={() =>
              onDecide(decision?.action === "reject" ? null : { action: "reject", at: now() })
            }
            aria-pressed={decision?.action === "reject"}
            className={`pressable inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs ${
              decision?.action === "reject"
                ? "border-dmg2 bg-dmg2/15 text-ink"
                : "border-line text-ink-dim hover:text-ink"
            }`}
          >
            <XMark /> Reject
          </button>
          <span className="mx-1 text-2xs text-ink-faint">override to</span>
          {DAMAGE.map((d) => {
            const on = decision?.action === "override" && decision.damage_class === d.index;
            return (
              <Tooltip key={d.index} content={d.label}>
                <button
                  onClick={() =>
                    onDecide(on ? null : { action: "override", damage_class: d.index, at: now() })
                  }
                  aria-pressed={on}
                  aria-label={`Override to ${d.label}`}
                  className={`pressable h-6 w-6 rounded-sm text-[10px] font-semibold ring-1 ring-inset ${
                    on ? "ring-ink" : "ring-black/20"
                  }`}
                  style={{ background: d.hex, color: d.index <= 1 ? "#1a1c1f" : "#fff" }}
                >
                  {d.index}
                </button>
              </Tooltip>
            );
          })}
        </div>
      </div>
    </li>
  );
}

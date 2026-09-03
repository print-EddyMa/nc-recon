import { useCallback, useMemo, useState } from "react";
import DeckMap from "../components/DeckMap";
import BeforeAfterSlider from "../components/BeforeAfterSlider";
import ClassBar from "../components/ClassBar";
import HotspotList from "../components/HotspotList";
import BuildingCard from "../components/BuildingCard";
import { hotspots, summarize } from "../lib/data";
import { useReviewDecisions, overrideClasses } from "../lib/review";
import AreaLoadError from "../components/AreaLoadError";
import type { AreaConfig, DamageCollection, EventConfig } from "../lib/types";

interface Props {
  event: EventConfig;
  area: AreaConfig;
  fc: DamageCollection | null;
  loadError?: string | null;
  onRetry?: () => void;
}

export default function MapView({ area, fc, loadError, onRetry }: Props) {
  if (loadError && !fc) {
    return <AreaLoadError areaName={area.name} detail={loadError} onRetry={onRetry ?? (() => {})} />;
  }
  return <MapViewInner area={area} fc={fc} />;
}

function MapViewInner({ area, fc }: Pick<Props, "area" | "fc">) {
  const [assessment, setAssessment] = useState(1);
  const [imagery, setImagery] = useState<"pre" | "post">("post");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [activeHotspot, setActiveHotspot] = useState<string | null>(null);
  const [filter, setFilter] = useState<Set<number>>(new Set([0, 1, 2, 3]));
  const [flyTarget, setFlyTarget] = useState<
    { center: [number, number]; zoom?: number; nonce: number } | null
  >(null);

  const { decisions } = useReviewDecisions(area.id);
  const overrides = useMemo(() => overrideClasses(decisions), [decisions]);
  const reviewedCount = useMemo(() => Object.keys(decisions).length, [decisions]);
  // side panels are collapsible below lg so the map is usable on a small screen
  const [panelsOpen, setPanelsOpen] = useState(true);
  // per-area reset is handled by a `key={area.id}` remount from App.tsx

  const spots = useMemo(() => (fc ? hotspots(fc) : []), [fc]);
  const stats = useMemo(() => (fc ? summarize(fc) : null), [fc]);
  const selected = useMemo(
    () => fc?.features.find((f) => f.properties.id === selectedId) ?? null,
    [fc, selectedId],
  );

  const toggleClass = (c: number) =>
    setFilter((prev) => {
      const next = new Set(prev);
      if (next.has(c)) next.delete(c);
      else next.add(c);
      return next.size ? next : new Set([0, 1, 2, 3]);
    });

  // stable so DeckMap's layer memo doesn't rebuild the GeoJsonLayer on every
  // incidental re-render (panel toggle, review decision, hover)
  const handleSelect = useCallback((id: string | null, center?: [number, number]) => {
    setSelectedId(id);
    if (id && center) setFlyTarget({ center, zoom: 17.5, nonce: Date.now() });
  }, []);

  return (
    <div className="relative h-full">
      <DeckMap
        area={area}
        fc={fc}
        overrides={overrides}
        assessment={assessment}
        imagery={imagery}
        selectedId={selectedId}
        filter={filter}
        onSelect={handleSelect}
        flyTarget={flyTarget}
      />

      {/* collapse toggle, only matters below lg */}
      <button
        onClick={() => setPanelsOpen((v) => !v)}
        className="pressable panel absolute left-3 top-3 z-30 flex items-center gap-1.5 px-2.5 py-1.5 text-2xs text-ink-dim hover:text-ink lg:hidden"
        aria-expanded={panelsOpen}
      >
        <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden>
          <path
            d={panelsOpen ? "M4 6l4 4 4-4" : "M6 4l4 4-4 4"}
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        {panelsOpen ? "Hide panels" : "Panels"}
      </button>

      {/* left: hardest-hit + selection */}
      <aside
        className={`absolute left-3 top-3 z-20 flex max-h-[calc(100%-8.5rem)] w-[19rem] max-w-[calc(100vw-1.5rem)] flex-col gap-3 overflow-y-auto sm:left-4 sm:top-4 lg:!flex ${
          panelsOpen ? "flex pt-11 lg:pt-0" : "hidden"
        }`}
      >
        <section className="panel px-3.5 py-3.5">
          <div className="mb-2.5 flex items-baseline justify-between">
            <h2 className="section-title">Hardest-hit clusters</h2>
            <span className="cap">ranked</span>
          </div>
          <HotspotList
            items={spots}
            activeKey={activeHotspot}
            onPick={(h) => {
              setActiveHotspot(h.key);
              setSelectedId(null);
              setFlyTarget({ center: h.center, zoom: 16.6, nonce: Date.now() });
            }}
          />
        </section>

        {selected && (
          <BuildingCard feature={selected} onClear={() => setSelectedId(null)} />
        )}
      </aside>

      {/* right: filter + counts */}
      <aside
        className={`absolute right-3 top-3 z-20 hidden w-[18rem] max-w-[calc(100vw-1.5rem)] md:block lg:right-4 lg:top-4 ${
          panelsOpen ? "" : "md:!hidden lg:!block"
        }`}
      >
        <section className="panel px-3.5 py-3.5">
          <div className="mb-2.5 flex items-baseline justify-between">
            <h2 className="section-title">{area.name}</h2>
            {stats && (
              <span className="tnum text-2xs text-ink-dim">
                {stats.total.toLocaleString()} buildings
              </span>
            )}
          </div>
          {stats && (
            <ClassBar counts={stats.counts} filter={filter} onToggle={toggleClass} />
          )}
          {stats && (
            <div className="mt-3 border-t border-line pt-2.5 text-xs text-ink-dim">
              <span className="tnum text-dmg2 text-sm font-semibold">
                {stats.severePct.toFixed(0)}%
              </span>{" "}
              major or destroyed
            </div>
          )}
          {fc?.properties.review && (
            <div className="mt-1.5 flex items-center justify-between text-2xs text-ink-faint">
              <span>
                <span className="tnum text-ink-dim">
                  {fc.properties.review.total_review.toLocaleString()}
                </span>{" "}
                flagged for review
              </span>
              {reviewedCount > 0 && (
                <span className="tnum rounded-sm bg-accent/15 px-1.5 py-0.5 text-accent">
                  {reviewedCount} reviewed
                </span>
              )}
            </div>
          )}
        </section>
      </aside>

      {/* bottom: signature slider */}
      <div className="absolute bottom-4 left-1/2 z-20 w-[min(560px,calc(100%-2rem))] -translate-x-1/2">
        <BeforeAfterSlider
          value={assessment}
          onChange={setAssessment}
          imagery={imagery}
          onImageryChange={setImagery}
          preDate={fc?.properties.pre_image.date}
          postDate={fc?.properties.post_image.date}
        />
      </div>

      {!fc && (
        <div className="absolute inset-0 z-30 bg-canvas/80">
          <div className="absolute left-3 top-3 w-[19rem] max-w-[calc(100vw-1.5rem)] space-y-2 sm:left-4 sm:top-4">
            <div className="skel h-4 w-40" />
            <div className="skel h-16 w-full" />
            <div className="skel h-16 w-full" />
            <div className="skel h-16 w-full" />
          </div>
          <div className="absolute bottom-4 left-1/2 h-20 w-[min(560px,calc(100%-2rem))] -translate-x-1/2 skel" />
        </div>
      )}
    </div>
  );
}

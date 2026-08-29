import { useEffect, useMemo, useState } from "react";
import DeckMap from "../components/DeckMap";
import BeforeAfterSlider from "../components/BeforeAfterSlider";
import ClassBar from "../components/ClassBar";
import HotspotList from "../components/HotspotList";
import BuildingCard from "../components/BuildingCard";
import { hotspots, summarize } from "../lib/data";
import type { AreaConfig, DamageCollection } from "../lib/types";

interface Props {
  area: AreaConfig;
  fc: DamageCollection | null;
}

export default function MapView({ area, fc }: Props) {
  const [assessment, setAssessment] = useState(1);
  const [imagery, setImagery] = useState<"pre" | "post">("post");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [activeHotspot, setActiveHotspot] = useState<string | null>(null);
  const [filter, setFilter] = useState<Set<number>>(new Set([0, 1, 2, 3]));
  const [flyTarget, setFlyTarget] = useState<
    { center: [number, number]; zoom?: number; nonce: number } | null
  >(null);

  // reset per-area
  useEffect(() => {
    setSelectedId(null);
    setActiveHotspot(null);
    setFilter(new Set([0, 1, 2, 3]));
  }, [area.id]);

  const spots = useMemo(() => (fc ? hotspots(fc) : []), [fc]);
  const stats = useMemo(() => (fc ? summarize(fc) : null), [fc]);
  const selected = useMemo(
    () => fc?.features.find((f) => f.properties.id === selectedId) ?? null,
    [fc, selectedId],
  );

  const toggleClass = (c: number) =>
    setFilter((prev) => {
      const next = new Set(prev);
      next.has(c) ? next.delete(c) : next.add(c);
      return next.size ? next : new Set([0, 1, 2, 3]);
    });

  return (
    <div className="relative h-full">
      <DeckMap
        area={area}
        fc={fc}
        assessment={assessment}
        imagery={imagery}
        selectedId={selectedId}
        filter={filter}
        onSelect={(id, center) => {
          setSelectedId(id);
          if (id && center) setFlyTarget({ center, zoom: 17.5, nonce: Date.now() });
        }}
        flyTarget={flyTarget}
      />

      {/* left: hardest-hit + selection */}
      <aside className="absolute left-3 top-3 z-20 flex max-h-[calc(100%-8.5rem)] w-[19rem] max-w-[calc(100vw-1.5rem)] flex-col gap-3 overflow-y-auto sm:left-4 sm:top-4">
        <section className="panel px-3 py-3">
          <div className="mb-2 flex items-baseline justify-between">
            <h2 className="font-display text-sm text-ink">Hardest-hit clusters</h2>
            <span className="cap">Ranked</span>
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
      <aside className="absolute right-3 top-3 z-20 hidden w-[18rem] max-w-[calc(100vw-1.5rem)] md:block lg:right-4 lg:top-4">
        <section className="panel px-3 py-3">
          <div className="mb-2 flex items-baseline justify-between">
            <h2 className="font-display text-sm text-ink">{area.name}</h2>
            {stats && (
              <span className="tnum text-2xs text-ink-dim">{stats.total} buildings</span>
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
        <div className="absolute inset-0 grid place-items-center bg-canvas/70">
          <span className="cap animate-pulse">Loading assessment…</span>
        </div>
      )}
    </div>
  );
}

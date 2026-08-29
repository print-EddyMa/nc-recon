import { useCallback, useEffect, useState } from "react";
import { AREAS, areaById, loadArea } from "./lib/data";
import type { DamageCollection } from "./lib/types";
import Landing from "./screens/Landing";
import MapView from "./screens/MapView";
import Stats from "./screens/Stats";

type Screen = "landing" | "map" | "stats";

export default function App() {
  const [screen, setScreen] = useState<Screen>("landing");
  const [areaId, setAreaId] = useState(AREAS[0].id);
  const [cache, setCache] = useState<Record<string, DamageCollection>>({});
  const [error, setError] = useState<string | null>(null);

  const fc = cache[areaId] ?? null;

  useEffect(() => {
    let cancelled = false;
    if (cache[areaId]) return;
    loadArea(areaId)
      .then((data) => !cancelled && setCache((c) => ({ ...c, [areaId]: data })))
      .catch((e) => !cancelled && setError(String(e)));
    return () => {
      cancelled = true;
    };
  }, [areaId, cache]);

  // warm the other areas in the background
  useEffect(() => {
    for (const a of AREAS) {
      if (!cache[a.id]) {
        loadArea(a.id)
          .then((data) => setCache((c) => (c[a.id] ? c : { ...c, [a.id]: data })))
          .catch(() => void 0);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const go = useCallback((s: Screen) => setScreen(s), []);

  if (screen === "landing") {
    return <Landing area={areaById(areaId)} fc={fc} onEnter={() => go("map")} />;
  }

  return (
    <div className="flex h-full flex-col">
      <TopBar
        screen={screen}
        areaId={areaId}
        onArea={setAreaId}
        onNav={go}
      />
      {error && (
        <div className="bg-dmg2/20 px-4 py-2 text-sm text-dmg0">Failed to load data: {error}</div>
      )}
      <div className="relative flex-1 overflow-hidden">
        {screen === "map" && <MapView area={areaById(areaId)} fc={fc} />}
        {screen === "stats" && <Stats area={areaById(areaId)} fc={fc} onOpenMap={() => go("map")} />}
      </div>
    </div>
  );
}

function TopBar({
  screen,
  areaId,
  onArea,
  onNav,
}: {
  screen: Screen;
  areaId: string;
  onArea: (id: string) => void;
  onNav: (s: Screen) => void;
}) {
  return (
    <header className="flex items-center gap-4 border-b border-line bg-surface px-4 py-2.5">
      <button
        onClick={() => onNav("landing")}
        className="flex items-center gap-2 text-sm font-semibold tracking-tight"
      >
        <span className="grid h-6 w-6 place-items-center rounded-[3px] bg-accent text-[#05171a]">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden>
            <path d="M2 12L8 3l6 9" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
            <path d="M2 12h12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
        </span>
        <span className="font-display">TerraTriage</span>
      </button>

      <nav className="ml-2 flex gap-1 text-sm">
        {(["map", "stats"] as const).map((s) => (
          <button
            key={s}
            onClick={() => onNav(s)}
            aria-current={screen === s ? "page" : undefined}
            className={`rounded-sm px-2.5 py-1 capitalize transition-colors ${
              screen === s ? "bg-surface-2 text-ink" : "text-ink-dim hover:text-ink"
            }`}
          >
            {s === "map" ? "Damage map" : "Summary"}
          </button>
        ))}
      </nav>

      <div className="ml-auto flex overflow-hidden rounded-sm border border-line">
        {AREAS.map((a) => (
          <button
            key={a.id}
            onClick={() => onArea(a.id)}
            aria-pressed={areaId === a.id}
            className={`px-3 py-1 text-xs transition-colors ${
              areaId === a.id ? "bg-accent text-[#05171a]" : "text-ink-dim hover:text-ink"
            }`}
          >
            {a.name}
          </button>
        ))}
      </div>
    </header>
  );
}

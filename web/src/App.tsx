import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { loadArea } from "./lib/data";
import { loadEvents, eventById, areaRef } from "./lib/events";
import { useReviewDecisions } from "./lib/review";
import { useAssess } from "./lib/useAssess";
import type { DamageCollection, EventConfig } from "./lib/types";
import type { CatalogEvent } from "./lib/catalog";
import type { IngestState } from "./lib/useAssess";
import EventPicker from "./components/EventPicker";
import CommandMenu from "./components/CommandMenu";
import { Toaster } from "sonner";
import Landing from "./screens/Landing";
import MapView from "./screens/MapView";
import LiveMonitor from "./screens/LiveMonitor";
import ReviewQueue from "./screens/ReviewQueue";
import Stats from "./screens/Stats";

type Screen = "landing" | "map" | "live" | "review" | "stats";

export default function App() {
  // the app opens on the global Live Monitor — no disaster is selected until the
  // user picks one (from the monitor, the picker, or ⌘K)
  const [screen, setScreen] = useState<Screen>("live");
  const [events, setEvents] = useState<EventConfig[] | null>(null);
  const [eventId, setEventId] = useState<string | null>(null);
  const [areaId, setAreaId] = useState<string | null>(null);
  const [cache, setCache] = useState<Record<string, DamageCollection>>({});
  const [error, setError] = useState<string | null>(null);
  const [cmdkOpen, setCmdkOpen] = useState(false);

  const refreshEvents = useCallback(
    (selectId?: string) =>
      loadEvents()
        .then((evs) => {
          setEvents(evs);
          if (selectId) {
            const target = evs.find((e) => e.id === selectId);
            setEventId(selectId);
            setAreaId(target?.areas[0]?.id ?? null);
          }
        })
        .catch((e) => setError(String(e))),
    [],
  );

  // load the event registry once
  useEffect(() => {
    refreshEvents();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const event = useMemo(
    () => (events && eventId ? eventById(events, eventId) : null),
    [events, eventId],
  );
  const area = useMemo(
    () => (events && eventId && areaId ? areaRef(events, eventId, areaId) : null),
    [events, eventId, areaId],
  );
  const fc = areaId ? (cache[areaId] ?? null) : null;

  // load the selected area's GeoJSON
  useEffect(() => {
    if (!areaId || cache[areaId]) return;
    let cancelled = false;
    loadArea(areaId)
      .then((data) => !cancelled && setCache((c) => ({ ...c, [areaId]: data })))
      .catch((e) => !cancelled && setError(String(e)));
    return () => {
      cancelled = true;
    };
  }, [areaId, cache]);

  // warm every area in the background once the registry is in
  useEffect(() => {
    if (!events) return;
    for (const ev of events) {
      for (const a of ev.areas) {
        if (cache[a.id]) continue;
        loadArea(a.id)
          .then((data) => setCache((c) => (c[a.id] ? c : { ...c, [a.id]: data })))
          .catch(() => void 0);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [events]);

  const { decisions } = useReviewDecisions(areaId ?? "");
  const reviewOpen = useMemo(() => {
    if (!fc) return 0;
    return fc.features.filter(
      (f) => f.properties.confidence_tier === "review" && !decisions[f.properties.id],
    ).length;
  }, [fc, decisions]);

  const go = useCallback((s: Screen) => setScreen(s), []);
  const pickEvent = useCallback(
    (id: string) => {
      setEventId(id);
      const ev = events ? eventById(events, id) : null;
      setAreaId(ev?.areas[0]?.id ?? null);
      setScreen("map");
    },
    [events],
  );
  const hasEvent = !!event && !!area;

  // shared "ingest a Maxar catalogue event" flow — used by the top-bar picker,
  // the landing picker, and the Live Monitor's Assess panel
  const { catalog, online, jobs, ingest } = useAssess(async (evId) => {
    await refreshEvents(evId);
    go("map");
  });

  if (error && !events) {
    return (
      <div className="mx-auto grid h-full max-w-md place-items-center px-6 text-center">
        <div>
          <div className="section-title mb-2">Event registry didn't load</div>
          <p className="text-sm text-ink-dim">
            Build it with{" "}
            <code className="tnum rounded bg-surface-2 px-1.5 py-0.5 text-xs">
              python scripts/run.py events registry
            </code>{" "}
            in the pipeline, then reload.
          </p>
          <p className="mt-3 text-2xs text-ink-faint">{error}</p>
        </div>
      </div>
    );
  }
  if (!events) {
    return (
      <div className="grid h-full place-items-center">
        <div className="flex items-center gap-2.5 text-ink-dim">
          <span className="grid h-6 w-6 place-items-center rounded-md bg-accent text-[#05171a]">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden>
              <path d="M2 12L8 3l6 9" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
              <path d="M2 12h12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
          </span>
          <span className="font-display text-sm">Loading TerraTriage</span>
        </div>
      </div>
    );
  }

  // event screens fall back to the monitor until a disaster is chosen
  const effScreen: Screen =
    !hasEvent && (screen === "map" || screen === "review" || screen === "stats")
      ? "live"
      : screen;

  const showcase = event ?? events[0] ?? null;

  return (
    <>
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <Toaster
        theme="dark"
        position="bottom-right"
        toastOptions={{
          className: "tt-toast",
          style: {
            background: "#161d26",
            border: "1px solid #28313d",
            color: "#ccd5df",
            fontFamily: '"Geist", ui-sans-serif, system-ui, sans-serif',
            fontSize: "13px",
          },
        }}
      />
      <CommandMenu
        open={cmdkOpen}
        onOpenChange={setCmdkOpen}
        events={events}
        catalog={catalog}
        currentEventId={eventId ?? ""}
        online={online}
        jobs={jobs}
        onNav={go}
        onPickEvent={pickEvent}
        onIngest={ingest}
      />
      {effScreen === "landing" && showcase ? (
        <Landing
          event={showcase}
          area={area ?? showcase.areas[0]}
          fc={area ? fc : (cache[showcase.areas[0]?.id] ?? null)}
          events={events}
          catalog={catalog}
          online={online}
          jobs={jobs}
          onPickEvent={pickEvent}
          onIngest={ingest}
          onEnter={() => go("live")}
        />
      ) : (
        <div className="flex h-full flex-col">
          <TopBar
            screen={effScreen}
            hasEvent={hasEvent}
            events={events}
            event={event}
            areaId={area?.id ?? null}
            reviewOpen={reviewOpen}
            catalog={catalog}
            online={online}
            jobs={jobs}
            onPickEvent={pickEvent}
            onIngest={ingest}
            onArea={setAreaId}
            onNav={go}
            onOpenSearch={() => setCmdkOpen(true)}
          />
          {error && (
            <div
              role="alert"
              className="border-b border-dmg2/40 bg-dmg2/15 px-4 py-2 text-sm text-dmg0"
            >
              Couldn't load the assessment data. {error}
            </div>
          )}
          <main id="main" className="relative flex-1 overflow-hidden">
            {effScreen === "map" && event && area && (
              <MapView event={event} area={area} fc={fc} />
            )}
            {effScreen === "live" && (
              <LiveMonitor
                events={events}
                catalog={catalog}
                online={online}
                jobs={jobs}
                onOpenEvent={pickEvent}
                onNavMap={() => go("map")}
                onIngest={ingest}
                onOpenAbout={() => go("landing")}
              />
            )}
            {effScreen === "review" && area && (
              <ReviewQueue area={area} fc={fc} onOpenMap={() => go("map")} />
            )}
            {effScreen === "stats" && event && area && (
              <Stats event={event} area={area} fc={fc} onOpenMap={() => go("map")} />
            )}
          </main>
        </div>
      )}
    </>
  );
}

/** Top nav with a single indicator that slides between the active tab — the one
 * genuinely transferable idea from the pill-nav components, done with a CSS
 * transition and no animation library. */
function NavTabs({
  screen,
  hasEvent,
  reviewOpen,
  onNav,
}: {
  screen: Screen;
  hasEvent: boolean;
  reviewOpen: number;
  onNav: (s: Screen) => void;
}) {
  const tabs = (
    hasEvent
      ? [
          { id: "live", label: "Live monitor" },
          { id: "map", label: "Damage map" },
          { id: "review", label: "Review", badge: reviewOpen },
          { id: "stats", label: "Summary" },
        ]
      : [{ id: "live", label: "Live monitor" }]
  ) as { id: Screen; label: string; badge?: number }[];
  const navRef = useRef<HTMLElement | null>(null);
  const btnRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const [ind, setInd] = useState<{ x: number; w: number } | null>(null);

  useLayoutEffect(() => {
    const el = btnRefs.current[screen];
    const nav = navRef.current;
    if (!el || !nav) {
      setInd(null);
      return;
    }
    setInd({ x: el.offsetLeft, w: el.offsetWidth });
  }, [screen, reviewOpen, hasEvent]);

  return (
    <nav ref={navRef} className="relative flex text-sm">
      {ind && (
        <span
          aria-hidden
          className="absolute bottom-0 h-[2px] rounded-full bg-accent transition-all duration-300 ease-out"
          style={{ transform: `translateX(${ind.x}px)`, width: ind.w }}
        />
      )}
      {tabs.map((t) => (
        <button
          key={t.id}
          ref={(n) => {
            btnRefs.current[t.id] = n;
          }}
          onClick={() => onNav(t.id as Screen)}
          aria-current={screen === t.id ? "page" : undefined}
          className={`pressable relative px-3 py-2 transition-colors duration-200 ${
            screen === t.id ? "text-ink" : "text-ink-dim hover:text-ink"
          }`}
        >
          {t.label}
          {"badge" in t && t.badge ? (
            <span className="tnum ml-1.5 rounded-sm bg-dmg2/20 px-1.5 py-0.5 text-2xs text-dmg1">
              {t.badge}
            </span>
          ) : null}
        </button>
      ))}
    </nav>
  );
}

function TopBar({
  screen,
  hasEvent,
  events,
  event,
  areaId,
  reviewOpen,
  catalog,
  online,
  jobs,
  onPickEvent,
  onIngest,
  onArea,
  onNav,
  onOpenSearch,
}: {
  screen: Screen;
  hasEvent: boolean;
  events: EventConfig[];
  event: EventConfig | null;
  areaId: string | null;
  reviewOpen: number;
  catalog: CatalogEvent[];
  online: boolean | null;
  jobs: Record<string, IngestState>;
  onPickEvent: (id: string) => void;
  onIngest: (ev: { id: string; name: string; center: [number, number] | null }) => void;
  onArea: (id: string) => void;
  onNav: (s: Screen) => void;
  onOpenSearch: () => void;
}) {
  return (
    <header className="flex flex-wrap items-center gap-x-5 gap-y-2 border-b border-line bg-surface px-4 py-2">
      <button
        onClick={() => onNav("live")}
        className="pressable flex items-center gap-2 text-sm font-semibold tracking-tight"
      >
        <span className="grid h-6 w-6 place-items-center rounded-md bg-accent text-[#05171a]">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden>
            <path d="M2 12L8 3l6 9" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
            <path d="M2 12h12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
        </span>
        <span className="font-display">TerraTriage</span>
      </button>

      <NavTabs screen={screen} hasEvent={hasEvent} reviewOpen={reviewOpen} onNav={onNav} />

      {hasEvent && event && (
        <span className="hidden items-center gap-1.5 text-xs text-ink-faint md:flex">
          <span className="text-ink-dim">viewing</span>
          <span className="text-ink">{event.name}</span>
          <button
            onClick={() => onNav("live")}
            className="pressable rounded-sm px-1 text-ink-faint hover:text-ink"
            aria-label="Back to global monitor"
          >
            ✕
          </button>
        </span>
      )}

      <div className="ml-auto flex items-center gap-2">
        <button
          onClick={onOpenSearch}
          className="pressable hidden items-center gap-2 rounded-md border border-line bg-surface-2 px-2 py-1.5 text-xs text-ink-faint hover:text-ink-dim lg:flex"
          aria-label="Open command menu"
        >
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden>
            <circle cx="7" cy="7" r="4.5" stroke="currentColor" strokeWidth="1.5" />
            <path d="M11 11l3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          <span>Search</span>
          <kbd className="tnum rounded-sm border border-line px-1 text-[10px] leading-4">⌘K</kbd>
        </button>
        <EventPicker
          events={events}
          catalog={catalog}
          value={event?.id ?? ""}
          online={online}
          jobs={jobs}
          onChange={onPickEvent}
          onIngest={onIngest}
        />
        {event && event.areas.length > 1 && (
          <div className="flex overflow-hidden rounded-md border border-line">
            {event.areas.map((a) => (
              <button
                key={a.id}
                onClick={() => onArea(a.id)}
                aria-pressed={areaId === a.id}
                className={`px-3 py-1 text-xs transition-colors duration-200 ease-out ${
                  areaId === a.id ? "bg-accent text-[#05171a]" : "text-ink-dim hover:text-ink"
                }`}
              >
                {a.name}
              </button>
            ))}
          </div>
        )}
      </div>
    </header>
  );
}

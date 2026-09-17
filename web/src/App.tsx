import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { loadArea } from "./lib/data";
import { loadEvents, areaLookup } from "./lib/events";
import { useReviewDecisions } from "./lib/review";
import { useAssess } from "./lib/useAssess";
import { useTheme } from "./lib/theme";
import type { DamageCollection, EventConfig } from "./lib/types";
import CommandMenu from "./components/CommandMenu";
import ErrorBoundary from "./components/ErrorBoundary";
import ShortcutsDialog from "./components/ShortcutsDialog";
import { Toaster, toast } from "sonner";
import Home from "./screens/Home";

// the map-heavy screens pull in deck.gl (~1 MB); load them on demand so the
// first paint of Home doesn't pay for code it isn't showing
const About = lazy(() => import("./screens/About"));
const Assess = lazy(() => import("./screens/Assess"));
const MapView = lazy(() => import("./screens/MapView"));
const NCDashboard = lazy(() => import("./screens/NCDashboard"));
const ReviewQueue = lazy(() => import("./screens/ReviewQueue"));
const Stats = lazy(() => import("./screens/Stats"));
const History = lazy(() => import("./screens/History"));

type Screen =
  "home" | "nc" | "history" | "assess" | "map" | "review" | "stats" | "about";
const AREA_SCREENS: Screen[] = ["map", "review", "stats"];

/** cap the in-memory GeoJSON cache so a long session over many assessed areas
 * doesn't grow without bound (each area is ~0.1-1 MB). */
const CACHE_LIMIT = 4;

/** NC Recon brand mark - the real North Carolina outline with a scan-ring
 * signal over the Triangle. `currentColor` fills the state; the rings and
 * signal dot use the app's one accent ("this is live"), so the mark tracks
 * the light / dark theme with everything else. */
function Mark({ uid, className }: { uid: string; className?: string }) {
  const nc =
    "M 92.04,0.0 L 294.65,1.34 L 298.66,15.28 L 288.92,13.94 L 274.03,19.67 L 266.2,20.24 L 266.58,22.72 L 287.97,20.81 L 291.41,24.06 L 297.71,22.72 L 300.0,31.13 L 297.9,35.14 L 293.7,35.52 L 284.91,44.11 L 273.27,44.49 L 271.36,50.41 L 276.32,56.33 L 280.33,57.48 L 272.88,67.22 L 266.58,66.07 L 247.87,69.13 L 235.84,75.81 L 226.29,84.6 L 221.32,95.67 L 214.07,93.19 L 201.46,95.48 L 161.94,62.25 L 122.79,61.68 L 123.36,57.67 L 118.01,51.75 L 114.39,53.85 L 114.19,50.22 L 71.23,48.5 L 42.2,55.38 L 0.0,55.76 L 0.95,47.55 L 7.83,46.79 L 10.5,41.06 L 19.1,35.9 L 28.64,35.71 L 37.24,30.36 L 46.21,28.45 L 53.85,20.62 L 58.63,18.33 L 59.58,21.77 L 73.33,15.09 L 79.63,16.42 L 84.02,9.93 L 90.52,8.21 L 92.04,0.0 Z";
  // accent parts go through `style` so the CSS var() resolves (var() is not
  // valid in a bare SVG presentation attribute)
  const stroke = { stroke: "rgb(var(--accent))" };
  const fill = { fill: "rgb(var(--accent))" };
  return (
    <svg viewBox="0 0 300 96" fill="none" aria-hidden className={className}>
      <clipPath id={`ncmark-${uid}`}>
        <path d={nc} />
      </clipPath>
      <path d={nc} fill="currentColor" />
      <g clipPath={`url(#ncmark-${uid})`}>
        <circle
          cx="198.09"
          cy="28.24"
          r="20"
          fill="none"
          style={stroke}
          strokeWidth="3.5"
        />
        <circle
          cx="198.09"
          cy="28.24"
          r="38"
          fill="none"
          style={stroke}
          strokeWidth="3.5"
        />
      </g>
      <circle cx="198.09" cy="28.24" r="6" style={fill} />
    </svg>
  );
}

export default function App() {
  // NC Recon is a North Carolina product: it opens on the operations home.
  // The damage-assessment screens light up once an NC area has been assessed.
  const [screen, setScreen] = useState<Screen>("home");
  const [registry, setRegistry] = useState<EventConfig[] | null>(null);
  const [areaId, setAreaId] = useState<string | null>(null);
  const [cache, setCache] = useState<Record<string, DamageCollection>>({});
  const [error, setError] = useState<string | null>(null);
  // area-GeoJSON load failure, kept separate from the registry `error` above so
  // one bad area load doesn't leave a registry-flavoured banner up all session
  // error is scoped to the area it happened on, so switching areas clears it
  // without a set-state-in-effect (the derived `areaError` below goes null when
  // `areaId` no longer matches).
  const [areaErr, setAreaErr] = useState<{ id: string; msg: string } | null>(
    null,
  );
  const [areaReload, setAreaReload] = useState(0);
  const [cmdkOpen, setCmdkOpen] = useState(false);

  const refreshRegistry = useCallback(
    (selectAreaId?: string) =>
      loadEvents()
        .then((evs) => {
          setRegistry(evs);
          setError(null);
          if (selectAreaId) setAreaId(selectAreaId);
        })
        .catch((e) => setError(String(e))),
    [],
  );

  useEffect(() => {
    refreshRegistry();
  }, [refreshRegistry]);

  // flat [{ event, area }] view of every assessed NC area
  const areas = useMemo(
    () =>
      (registry ?? []).flatMap((ev) =>
        ev.areas.map((a) => ({ event: ev, area: a })),
      ),
    [registry],
  );
  const current = useMemo(
    () => (registry && areaId ? areaLookup(registry, areaId) : null),
    [registry, areaId],
  );
  const event = current?.event ?? null;
  const area = current?.area ?? null;
  const fc = areaId ? (cache[areaId] ?? null) : null;
  const areaError = areaErr && areaErr.id === areaId ? areaErr.msg : null;

  // load (and LRU-cache) the selected area's GeoJSON
  useEffect(() => {
    if (!areaId || cache[areaId]) return;
    let cancelled = false;
    loadArea(areaId)
      .then((data) => {
        if (cancelled) return;
        setCache((c) => {
          const next: Record<string, DamageCollection> = {
            ...c,
            [areaId]: data,
          };
          const keys = Object.keys(next);
          if (keys.length > CACHE_LIMIT) delete next[keys[0]];
          return next;
        });
      })
      .catch((e) => !cancelled && setAreaErr({ id: areaId, msg: String(e) }));
    return () => {
      cancelled = true;
    };
  }, [areaId, cache, areaReload]);

  const retryArea = useCallback(() => {
    setAreaErr(null);
    setAreaReload((n) => n + 1);
  }, []);

  const { decisions } = useReviewDecisions(areaId ?? "");
  const reviewOpen = useMemo(() => {
    if (!fc) return 0;
    return fc.features.filter(
      (f) =>
        f.properties.confidence_tier === "review" &&
        !decisions[f.properties.id],
    ).length;
  }, [fc, decisions]);

  const go = useCallback((s: Screen) => setScreen(s), []);
  const pickArea = useCallback((id: string) => {
    setAreaId(id);
    setScreen("map");
  }, []);
  const hasArea = !!event && !!area;

  // --- URL hash deep-linking:
  //     #/ · #/monitor · #/assess · #/about · #/a/<area>/<screen> ---
  const hydrated = useRef(false);
  useEffect(() => {
    if (!registry) return;
    const applyHash = () => {
      hydrated.current = true;
      const m = window.location.hash.match(
        /^#\/(monitor|history|assess|about|a\/([^/]+)\/(map|review|stats))?$/,
      );
      if (!m || !m[1]) {
        setScreen("home");
        return;
      }
      if (m[1] === "monitor") setScreen("nc");
      else if (m[1] === "history") setScreen("history");
      else if (m[1] === "assess") setScreen("assess");
      else if (m[1] === "about") setScreen("about");
      else if (m[2]) {
        const found = areaLookup(registry, decodeURIComponent(m[2]));
        if (found) {
          setAreaId(found.area.id);
          setScreen(m[3] as Screen);
        } else {
          setScreen("home");
        }
      }
    };
    applyHash();
    window.addEventListener("hashchange", applyHash);
    return () => window.removeEventListener("hashchange", applyHash);
  }, [registry]);

  useEffect(() => {
    if (!registry || !hydrated.current) return;
    let hash = "#/";
    if (screen === "nc") hash = "#/monitor";
    else if (screen === "history") hash = "#/history";
    else if (screen === "assess") hash = "#/assess";
    else if (screen === "about") hash = "#/about";
    else if (areaId && AREA_SCREENS.includes(screen))
      hash = `#/a/${encodeURIComponent(areaId)}/${screen}`;
    if (hash !== window.location.hash)
      window.history.replaceState(null, "", hash);
  }, [screen, areaId, registry]);

  // shared "assess an NC area" flow, used by the Assess screen and ⌘K
  const { catalog, online, jobs, ingest } = useAssess(async (newAreaId) => {
    await refreshRegistry(newAreaId);
    go("map");
  });

  if (error && !registry) {
    return (
      <div className="mx-auto grid h-full max-w-md place-items-center px-6 text-center">
        <div>
          <div className="section-title mb-2">Event registry didn't load</div>
          <p className="text-sm text-ink-dim">
            The app still runs without it, this only lists NC areas that have
            been assessed. Rebuild it with{" "}
            <code className="tnum rounded bg-surface-2 px-1.5 py-0.5 text-xs">
              python scripts/run.py events registry
            </code>
            .
          </p>
          <p className="mt-3 text-2xs text-ink-faint">{error}</p>
        </div>
      </div>
    );
  }
  if (!registry) {
    return (
      <div className="grid h-full place-items-center">
        <div className="flex items-center gap-2.5 text-ink-dim">
          <Mark uid="load" className="h-4 w-[52px] text-ink-dim" />
          <span className="font-display text-sm">Loading NC Recon</span>
        </div>
      </div>
    );
  }

  // the area screens fall back to home until an NC area is assessed
  const effScreen: Screen =
    !hasArea && AREA_SCREENS.includes(screen) ? "home" : screen;

  return (
    <>
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <Toaster
        position="top-right"
        toastOptions={{
          className: "tt-toast",
          style: {
            background: "rgb(var(--surface))",
            border: "1px solid rgb(var(--line))",
            color: "rgb(var(--ink-dim))",
            fontFamily: '"Geist", ui-sans-serif, system-ui, sans-serif',
            fontSize: "13px",
          },
        }}
      />
      <ShortcutsDialog onNav={(s) => go(s)} />
      <CommandMenu
        open={cmdkOpen}
        onOpenChange={setCmdkOpen}
        areas={areas}
        catalog={catalog}
        currentAreaId={areaId ?? ""}
        online={online}
        jobs={jobs}
        onNav={go}
        onPickArea={pickArea}
        onIngest={ingest}
      />
      <div className="flex h-full flex-col">
        <TopBar
          screen={effScreen}
          hasArea={hasArea}
          areas={areas}
          areaId={areaId}
          eventName={event?.name ?? null}
          reviewOpen={reviewOpen}
          onPickArea={setAreaId}
          onNav={go}
          onOpenSearch={() => setCmdkOpen(true)}
        />
        {error && (
          <div
            role="alert"
            className="border-b border-dmg3/40 bg-dmg3/15 px-4 py-2 text-sm text-dmg3"
          >
            Couldn&rsquo;t load the assessment data. {error}
          </div>
        )}
        <main id="main" className="relative flex-1 overflow-hidden">
          <Suspense
            fallback={
              <div className="grid h-full place-items-center text-sm text-ink-faint">
                Loading…
              </div>
            }
          >
            {effScreen === "home" && (
              <ErrorBoundary label="The home dashboard">
                <Home
                  areas={areas}
                  online={online}
                  onOpenArea={pickArea}
                  onOpenMonitor={() => go("nc")}
                  onOpenAssess={() => go("assess")}
                  onOpenAbout={() => go("about")}
                />
              </ErrorBoundary>
            )}
            {effScreen === "nc" && (
              <ErrorBoundary label="The North Carolina risk dashboard">
                <NCDashboard
                  onOpenAssess={() => go("assess")}
                  onOpenAbout={() => go("about")}
                />
              </ErrorBoundary>
            )}
            {effScreen === "history" && (
              <ErrorBoundary label="The disaster-history timeline">
                <History
                  areas={areas}
                  onOpenAssess={() => go("assess")}
                  onOpenArea={pickArea}
                />
              </ErrorBoundary>
            )}
            {effScreen === "assess" && (
              <ErrorBoundary label="On-demand assessment">
                <Assess
                  areas={areas}
                  catalog={catalog}
                  online={online}
                  jobs={jobs}
                  onIngest={ingest}
                  onOpenArea={pickArea}
                  onBack={() => go("nc")}
                />
              </ErrorBoundary>
            )}
            {effScreen === "map" && event && area && (
              <ErrorBoundary label="The damage map">
                <MapView
                  key={area.id}
                  event={event}
                  area={area}
                  fc={fc}
                  loadError={areaError}
                  onRetry={retryArea}
                />
              </ErrorBoundary>
            )}
            {effScreen === "review" && area && (
              <ErrorBoundary label="The review queue">
                <ReviewQueue
                  key={area.id}
                  area={area}
                  fc={fc}
                  loadError={areaError}
                  onRetry={retryArea}
                  onOpenMap={() => go("map")}
                />
              </ErrorBoundary>
            )}
            {effScreen === "stats" && event && area && (
              <ErrorBoundary label="The summary">
                <Stats
                  key={area.id}
                  event={event}
                  area={area}
                  fc={fc}
                  loadError={areaError}
                  onRetry={retryArea}
                  onOpenMap={() => go("map")}
                />
              </ErrorBoundary>
            )}
            {effScreen === "about" && (
              <ErrorBoundary label="About">
                <About onEnter={() => go("nc")} />
              </ErrorBoundary>
            )}
          </Suspense>
        </main>
      </div>
    </>
  );
}

/** Top nav with a single indicator that slides between the active tab. */
function NavTabs({
  screen,
  hasArea,
  reviewOpen,
  onNav,
}: {
  screen: Screen;
  hasArea: boolean;
  reviewOpen: number;
  onNav: (s: Screen) => void;
}) {
  const tabs = (
    hasArea
      ? [
          { id: "home", label: "Home" },
          { id: "nc", label: "Live map" },
          { id: "history", label: "History" },
          { id: "assess", label: "Assess" },
          { id: "map", label: "Damage map" },
          { id: "review", label: "Review", badge: reviewOpen },
          { id: "stats", label: "Summary" },
        ]
      : [
          { id: "home", label: "Home" },
          { id: "nc", label: "Live map" },
          { id: "history", label: "History" },
          { id: "assess", label: "Assess" },
        ]
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
  }, [screen, reviewOpen, hasArea]);

  return (
    <nav
      ref={navRef}
      className="relative -mb-2 flex overflow-x-auto pb-2 text-sm [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
    >
      {ind && (
        <span
          aria-hidden
          className="absolute bottom-2 h-[2px] rounded-full bg-accent transition-[transform,width] duration-300 ease-out"
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
          className={`pressable relative shrink-0 px-3 py-2 transition-colors duration-200 ${screen === t.id ? "text-ink" : "text-ink-dim hover:text-ink"}`}
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
  hasArea,
  areas,
  areaId,
  eventName,
  reviewOpen,
  onPickArea,
  onNav,
  onOpenSearch,
}: {
  screen: Screen;
  hasArea: boolean;
  areas: { event: EventConfig; area: EventConfig["areas"][number] }[];
  areaId: string | null;
  eventName: string | null;
  reviewOpen: number;
  onPickArea: (id: string) => void;
  onNav: (s: Screen) => void;
  onOpenSearch: () => void;
}) {
  return (
    <header className="flex flex-col gap-2 border-b border-line bg-surface px-4 py-2 md:flex-row md:flex-wrap md:items-center md:gap-x-5">
      <div className="flex items-center gap-x-5">
        <button
          onClick={() => onNav("home")}
          className="pressable flex items-center gap-2 text-sm font-semibold tracking-tight"
        >
          <Mark uid="nav" className="h-4 w-[52px] text-ink" />
          <span className="font-display">NC Recon</span>
          <span className="cap hidden text-ink-faint sm:inline">
            North Carolina
          </span>
        </button>

        <NavTabs
          screen={screen}
          hasArea={hasArea}
          reviewOpen={reviewOpen}
          onNav={onNav}
        />
      </div>

      {hasArea && eventName && (
        <span className="hidden items-center gap-1.5 text-xs text-ink-faint lg:flex">
          <span className="text-ink-dim">viewing</span>
          <span className="text-ink">{eventName}</span>
          <button
            onClick={() => {
              navigator.clipboard?.writeText(window.location.href).then(
                () =>
                  toast.success("Link copied", {
                    description: "Opens straight to this view.",
                  }),
                () => void 0,
              );
            }}
            className="pressable rounded-sm px-1 text-ink-faint hover:text-ink"
            aria-label="Copy a link to this view"
          >
            <svg
              width="12"
              height="12"
              viewBox="0 0 16 16"
              fill="none"
              aria-hidden
            >
              <path
                d="M6 10a3 3 0 004 0l2-2a3 3 0 00-4-4l-1 1M10 6a3 3 0 00-4 0L4 8a3 3 0 004 4l1-1"
                stroke="currentColor"
                strokeWidth="1.4"
                strokeLinecap="round"
              />
            </svg>
          </button>
        </span>
      )}

      <div className="flex flex-wrap items-center gap-2 md:ml-auto">
        <button
          onClick={onOpenSearch}
          className="pressable hidden items-center gap-2 rounded-md border border-line bg-surface-2 px-2 py-1.5 text-xs text-ink-faint hover:text-ink-dim lg:flex"
          aria-label="Open command menu"
        >
          <svg
            width="12"
            height="12"
            viewBox="0 0 16 16"
            fill="none"
            aria-hidden
          >
            <circle
              cx="7"
              cy="7"
              r="4.5"
              stroke="currentColor"
              strokeWidth="1.5"
            />
            <path
              d="M11 11l3 3"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
            />
          </svg>
          <span>Search</span>
          <kbd className="tnum rounded-sm border border-line px-1 text-[10px] leading-4">
            ⌘K
          </kbd>
        </button>
        <ThemeToggle />
        {areas.length > 0 && (
          <label className="flex items-center gap-1.5 text-xs text-ink-faint">
            <span className="hidden sm:inline">area</span>
            <select
              value={areaId ?? ""}
              onChange={(e) => onPickArea(e.target.value)}
              className="rounded-md border border-line bg-surface-2 px-2 py-1.5 text-xs text-ink-dim"
            >
              <option value="" disabled>
                pick an assessed area
              </option>
              {areas.map(({ event: ev, area: a }) => (
                <option key={a.id} value={a.id}>
                  {a.name}, {ev.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <button
          onClick={() => onNav("assess")}
          className="pressable rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-accent-ink"
        >
          Assess an area
        </button>
      </div>
    </header>
  );
}

function ThemeToggle() {
  const { effective, cycle } = useTheme();
  return (
    <button
      onClick={cycle}
      className="pressable grid h-8 w-8 place-items-center rounded-md border border-line bg-surface-2 text-ink-faint hover:text-ink"
      aria-label={`Switch to ${effective === "dark" ? "light" : "dark"} mode`}
      title={`Switch to ${effective === "dark" ? "light" : "dark"} mode`}
    >
      {effective === "dark" ? (
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden>
          <circle
            cx="8"
            cy="8"
            r="3.2"
            stroke="currentColor"
            strokeWidth="1.4"
          />
          <path
            d="M8 1.5v1.6M8 12.9v1.6M14.5 8h-1.6M3.1 8H1.5M12.6 3.4l-1.1 1.1M4.5 11.5l-1.1 1.1M12.6 12.6l-1.1-1.1M4.5 4.5L3.4 3.4"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinecap="round"
          />
        </svg>
      ) : (
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden>
          <path
            d="M13.2 9.4A5.5 5.5 0 016.6 2.8a5.5 5.5 0 106.6 6.6z"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinejoin="round"
          />
        </svg>
      )}
    </button>
  );
}

import { Suspense, lazy, useCallback, useEffect, useState } from "react";
import { Toaster } from "sonner";
import ErrorBoundary from "./components/ErrorBoundary";
import { useTheme } from "./lib/theme";
import { API_URL } from "./lib/catalog";
import { DISCLAIMER } from "./lib/ops";

// NC Recon, operational build. Three screens, no decoration:
//   Operations  damage assessments, review queue, exports, new assessments
//   Conditions  live rivers / alerts / roads / storms across NC
//   Help        how to read and use the outputs, limits, sources
// The earlier demo screens (xView2 4-class map, review, summary, 3-D hero)
// are not part of this build; the pitch demo lives in demo.html.
const Ops = lazy(() => import("./screens/Ops"));
const NCDashboard = lazy(() => import("./screens/NCDashboard"));
const Help = lazy(() => import("./screens/Help"));
const Verify = lazy(() => import("./screens/Verify"));

type Screen = "ops" | "conditions" | "verify" | "help";

function parseHash(): { screen: Screen; area: string | null } {
  const h = window.location.hash;
  const m = h.match(/^#\/ops\/([a-z0-9_]{1,40})$/);
  if (m) return { screen: "ops", area: m[1] };
  if (h.startsWith("#/conditions")) return { screen: "conditions", area: null };
  if (h.startsWith("#/help")) return { screen: "help", area: null };
  if (h.startsWith("#/verify")) return { screen: "verify", area: null };
  return { screen: "ops", area: null };
}

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
  const [{ screen, area }, setRoute] = useState(parseHash);

  useEffect(() => {
    const onHash = () => setRoute(parseHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const go = useCallback((s: Screen, a: string | null = null) => {
    const hash = s === "ops" ? (a ? `#/ops/${a}` : "#/") : `#/${s}`;
    if (window.location.hash !== hash) window.location.hash = hash;
    setRoute({ screen: s, area: a });
  }, []);

  return (
    <>
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: "rgb(var(--surface))",
            border: "1px solid rgb(var(--line))",
            color: "rgb(var(--ink))",
            fontFamily: '"Geist", ui-sans-serif, system-ui, sans-serif',
            fontSize: "14px",
          },
        }}
      />
      <div className="flex h-full flex-col">
        <header className="flex shrink-0 items-center gap-2 border-b border-line bg-surface px-3 py-2 sm:gap-4 sm:px-4">
          <a href="#/" className="flex items-center gap-2 text-ink" aria-label="NC Recon, operations">
            <Mark uid="hdr" className="h-5 w-[62px]" />
            <span className="hidden font-display text-base font-semibold sm:inline">NC Recon</span>
          </a>
          <nav aria-label="Main" className="flex items-center gap-1">
            {(
              [
                ["ops", "Operations"],
                ["conditions", "Conditions"],
                ["verify", "Verify"],
                ["help", "Help"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                onClick={() => go(id)}
                aria-current={screen === id ? "page" : undefined}
                className={`rounded-md px-3 py-1.5 text-sm font-medium ${
                  screen === id
                    ? "bg-ink text-canvas"
                    : "text-ink-dim hover:bg-surface-2 hover:text-ink"
                }`}
              >
                {label}
              </button>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3">
            {!API_URL && (
              <span className="rounded-sm bg-dmg1/20 px-2 py-0.5 text-xs text-ink">
                No assessment service connected
              </span>
            )}
            <ThemeToggle />
          </div>
        </header>
        <div
          role="note"
          className="shrink-0 border-b border-line bg-warn px-4 py-1 text-center text-sm font-medium text-warn-ink"
        >
          {DISCLAIMER}
        </div>
        <main id="main" className="relative min-h-0 flex-1 overflow-hidden">
          <Suspense
            fallback={
              <div className="grid h-full place-items-center text-sm text-ink-dim">Loading…</div>
            }
          >
            {screen === "ops" && (
              <ErrorBoundary label="The operations view">
                <Ops key={area ?? "none"} areaId={area} onPickArea={(a) => go("ops", a)} />
              </ErrorBoundary>
            )}
            {screen === "conditions" && (
              <ErrorBoundary label="The conditions map">
                <NCDashboard onOpenAssess={() => go("ops")} onOpenAbout={() => go("help")} />
              </ErrorBoundary>
            )}
            {screen === "verify" && (
              <ErrorBoundary label="Verify">
                <Verify />
              </ErrorBoundary>
            )}
            {screen === "help" && (
              <ErrorBoundary label="Help">
                <Help />
              </ErrorBoundary>
            )}
          </Suspense>
        </main>
      </div>
    </>
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

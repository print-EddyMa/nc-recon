import { Suspense, lazy, useCallback, useEffect, useState } from "react";
import { Toaster } from "sonner";
import ErrorBoundary from "./components/ErrorBoundary";
import { AccessButton, SourcesButton } from "./components/ops/SystemPanels";
import { Icon, type IconName } from "./components/ui/kit";
import { useTheme } from "./lib/theme";
import { API_URL } from "./lib/catalog";
import { DISCLAIMER } from "./lib/ops";

// Groma, operational build. The frame is three bands:
//   top     brand, the four jobs (Assess, Verify, Conditions, Help), system state
//   middle  the screen
//   bottom  the standing disclaimer and the service connection, always visible
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

const NAV: { id: Screen; label: string; icon: IconName; hint: string }[] = [
  { id: "ops", label: "Assess", icon: "map", hint: "Damage assessments: areas, review, exports" },
  { id: "verify", label: "Verify", icon: "check", hint: "Blind checks of uncertain calls" },
  { id: "conditions", label: "Conditions", icon: "signal", hint: "Live rivers, alerts, power, shelters, storms" },
  { id: "help", label: "Help", icon: "book", hint: "How to read and use every output" },
];

/** The groma: a Roman surveyor's staff, cross-arm and plumb lines. Strokes
 * follow the text colour; the plumb bobs and finial are the bronze brand. */
export function GromaMark({ className }: { className?: string }) {
  const bronze = { fill: "rgb(var(--brand))" };
  return (
    <svg viewBox="0 0 64 64" className={className} aria-hidden>
      <g fill="none" stroke="currentColor" strokeLinecap="round">
        <line x1="32" y1="9" x2="32" y2="55" strokeWidth="3.6" />
        <line x1="9" y1="15" x2="55" y2="15" strokeWidth="3.6" />
        <line x1="6" y1="56" x2="58" y2="56" strokeWidth="3.6" />
        <line x1="12" y1="15" x2="12" y2="39" strokeWidth="1.8" />
        <line x1="52" y1="15" x2="52" y2="39" strokeWidth="1.8" />
      </g>
      <path d="M12 38.5l-3.6 3.4 3.6 6 3.6-6zM52 38.5l-3.6 3.4 3.6 6 3.6-6z" style={bronze} />
      <circle cx="32" cy="9" r="2.8" style={bronze} />
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
        position="bottom-right"
        offset={40}
        toastOptions={{
          style: {
            background: "rgb(var(--surface))",
            border: "1px solid rgb(var(--line-strong))",
            color: "rgb(var(--ink))",
            fontFamily: '"Public Sans Variable", ui-sans-serif, system-ui, sans-serif',
            fontSize: "13px",
            borderRadius: "6px",
          },
        }}
      />
      <div className="flex h-full flex-col">
        <header className="flex h-12 shrink-0 items-center gap-1.5 border-b border-line bg-surface px-2 sm:gap-5 sm:px-4">
          <a
            href="#/"
            onClick={(e) => {
              e.preventDefault();
              go("ops");
            }}
            className="flex items-center gap-2 rounded text-ink"
            aria-label="Groma, assessments"
          >
            <GromaMark className="h-6 w-6 shrink-0 sm:h-7 sm:w-7" />
            <span className="title-display hidden text-[17px] tracking-[0.22em] sm:inline">GROMA</span>
          </a>
          <nav aria-label="Main" className="flex h-full items-stretch gap-0.5">
            {NAV.map((n) => {
              const on = screen === n.id;
              return (
                <button
                  key={n.id}
                  onClick={() => go(n.id)}
                  aria-current={on ? "page" : undefined}
                  title={n.hint}
                  aria-label={n.label}
                  className={`relative inline-flex items-center gap-1.5 px-2 text-[13px] sm:px-3 sm:text-sm ${
                    on ? "font-semibold text-ink" : "text-ink-dim hover:text-ink"
                  }`}
                >
                  <Icon name={n.icon} className={`min-[400px]:max-sm:hidden ${on ? "text-accent" : ""}`} />
                  <span className="max-[399px]:sr-only">{n.label}</span>
                  {on && <span className="absolute inset-x-2 bottom-0 h-0.5 rounded-t bg-accent" aria-hidden />}
                </button>
              );
            })}
          </nav>
          <div className="ml-auto flex items-center gap-1">
            <SourcesButton />
            <AccessButton />
            <ThemeToggle />
          </div>
        </header>

        <main id="main" className="relative min-h-0 flex-1 overflow-hidden">
          <Suspense
            fallback={<div className="grid h-full place-items-center text-sm text-ink-dim">Loading…</div>}
          >
            {screen === "ops" && (
              <ErrorBoundary label="The assessment view">
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

        <footer
          role="note"
          className="flex min-h-7 shrink-0 flex-wrap items-center gap-x-4 gap-y-0.5 border-t border-line bg-surface px-3 py-1 text-[12px] text-ink-dim sm:px-4"
        >
          <Disclaimer />
          <span className="ml-auto hidden items-center gap-1.5 sm:inline-flex">
            {API_URL ? (
              <>
                <span className="h-1.5 w-1.5 rounded-full bg-st-ok" aria-hidden />
                Assessment service connected
              </>
            ) : (
              <>
                <span className="h-1.5 w-1.5 rounded-full bg-st-unknown" aria-hidden />
                No assessment service connected
              </>
            )}
          </span>
        </footer>
      </div>
    </>
  );
}

/** The standing disclaimer: in full on wide screens; on a phone one line,
 * with the full text a tap away. */
function Disclaimer() {
  const [open, setOpen] = useState(false);
  return (
    <span className="inline-flex min-w-0 flex-1 items-start gap-1.5 sm:flex-none">
      <Icon name="shield" className="mt-px h-3.5 w-3.5 text-st-warn" />
      <span className={`min-w-0 text-ink ${open ? "" : "max-sm:truncate"}`}>
        <span className="sm:hidden">{open ? DISCLAIMER : "Decision support, not an official assessment."}</span>
        <span className="max-sm:hidden">{DISCLAIMER}</span>
      </span>
      <button
        className="shrink-0 text-ink-faint hover:text-ink sm:hidden"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={open ? "Show less" : "Read the full disclaimer"}
      >
        <Icon name={open ? "x" : "info"} className="h-3.5 w-3.5" />
      </button>
    </span>
  );
}

function ThemeToggle() {
  const { effective, cycle } = useTheme();
  return (
    <button
      onClick={cycle}
      className="pressable grid h-8 w-8 place-items-center rounded border border-line bg-surface text-ink-dim hover:text-ink"
      aria-label={`Switch to ${effective === "dark" ? "light" : "dark"} mode`}
      title={`Switch to ${effective === "dark" ? "light" : "dark"} mode`}
    >
      {effective === "dark" ? (
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden>
          <circle cx="8" cy="8" r="3.2" stroke="currentColor" strokeWidth="1.5" />
          <path
            d="M8 1.5v1.6M8 12.9v1.6M14.5 8h-1.6M3.1 8H1.5M12.6 3.4l-1.1 1.1M4.5 11.5l-1.1 1.1M12.6 12.6l-1.1-1.1M4.5 4.5L3.4 3.4"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
          />
        </svg>
      ) : (
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden>
          <path
            d="M13.2 9.4A5.5 5.5 0 016.6 2.8a5.5 5.5 0 106.6 6.6z"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinejoin="round"
          />
        </svg>
      )}
    </button>
  );
}

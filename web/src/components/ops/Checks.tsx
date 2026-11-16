/* Checks: every assessment checks itself and says how much margin it has.
 * Ported from Margin's verification panel (same author, MIT): a check is one
 * question the assessment asks of its own outputs; a check that could not be
 * answered is shown as not checked with its reason, never hidden. Load is the
 * share of a limit used; margin = 1 / load - 1. Checks label an assessment,
 * they never block an export. Served by GET /ops/areas/{area}/checks. */
import { useCallback, useEffect, useState } from "react";
import { API_URL } from "../../lib/catalog";
import { authHeaders } from "../../lib/ops";
import { Button, Disclosure, Icon, Tag } from "../ui/kit";
import { cx } from "../ui/classes";

export type CheckStatus = "pass" | "warn" | "fail" | "skip";
export type Verdict = "verified" | "passed_with_warnings" | "failed";

export interface CheckMetric {
  label: string;
  value: number | null;
  limit: number | null;
  unit: string;
  kind: "max" | "min";
  ok: boolean | null;
  load: number | null;
  margin: number | null;
  source?: string;
}

export interface CheckRow {
  id: string;
  title: string;
  category: string;
  status: CheckStatus;
  finding: string;
  source: string;
  value: number | null;
  limit: number | null;
  unit: string;
  kind: "max" | "min" | null;
  load: number | null;
  margin: number | null;
  metrics: CheckMetric[];
  /** caveats that qualify the one-line finding */
  note?: string;
  reason?: string;
  /** skip only: true = by design (held out, not built), false = a gap */
  not_applicable?: boolean;
}

export interface LandingZoneMargin {
  usng: string | null;
  lon: number | null;
  lat: number | null;
  fits: string[];
  marginal: boolean;
  cover: string | null;
  status: "pass" | "fail";
  load: number | null;
  margin: number | null;
  limiting: string | null;
  metrics: CheckMetric[];
}

export interface ChecksReport {
  schema: string;
  area: string;
  run_id: string | null;
  role: string;
  generated_utc: string;
  verdict: Verdict;
  summary: string;
  counts: Record<CheckStatus | "gaps", number>;
  limiting: { id: string; title: string; load: number; margin: number | null } | null;
  checks: CheckRow[];
  landing_zones: {
    params: Record<string, number>;
    params_recorded: boolean;
    source: string;
    caveat?: string | null;
    candidates: LandingZoneMargin[];
  } | null;
  note: string;
}

// --------------------------------------------------------------------------- //
// margin math and bands (Margin: web/src/panels/Load.tsx)
// --------------------------------------------------------------------------- //
/** Margin of safety from a load (share of the limit used): allowable / actual - 1. */
export function marginOf(load: number | null | undefined): number | null {
  if (load === null || load === undefined || !Number.isFinite(load)) return null;
  return load <= 0.01 ? 99 : 1 / load - 1;
}

/** Bands are set on the load, so the number and the bar always agree. */
export function loadBand(l: number | null | undefined) {
  if (l === null || l === undefined || !Number.isFinite(l))
    return { key: "none", label: "no limit to measure against", text: "text-st-unknown", bar: "bg-st-unknown/50" };
  if (l > 1) return { key: "over", label: "over the limit", text: "text-st-bad", bar: "bg-st-bad" };
  if (l > 0.8) return { key: "tight", label: "tight margin", text: "text-st-warn", bar: "bg-st-warn" };
  if (l > 0.5) return { key: "fine", label: "comfortable margin", text: "text-st-ok", bar: "bg-st-ok" };
  return { key: "large", label: "large margin", text: "text-st-ok", bar: "bg-st-ok/70" };
}

/** "+47%", "0%", "-12%"; very large margins read ">+300%". */
export function fmtMargin(load: number | null | undefined): string {
  const m = marginOf(load);
  if (m === null) return "no limit";
  if (m > 3) return ">+300%";
  const p = Math.round(m * 100);
  return `${p > 0 ? "+" : p < 0 ? "−" : ""}${Math.abs(p)}%`;
}

/** The margin with a slim bar: filled = the share of the limit used, the tick
 * is the limit, the gap between them is the margin. */
export function LoadBar({ load, className, compact }: { load: number | null | undefined; className?: string; compact?: boolean }) {
  const b = loadBand(load);
  const SCALE = 1.5; // the bar spans 0 to 150% of the limit
  const w = load === null || load === undefined || !Number.isFinite(load) ? 0 : Math.min(1, Math.max(0, load / SCALE));
  return (
    <div className={cx(compact ? "w-16" : "w-28", "shrink-0", className)} title={`Margin ${fmtMargin(load)}: ${b.label}`}>
      {!compact && (
        <div className="flex items-baseline justify-end gap-1">
          <span className={cx("tnum font-mono text-sm font-semibold", b.text)}>{fmtMargin(load)}</span>
          <span className="text-[10px] text-ink-faint">margin</span>
        </div>
      )}
      <div className={cx("relative h-1.5 rounded-full bg-line", !compact && "mt-1")}>
        <div className={cx("absolute inset-y-0 left-0 rounded-full", b.bar)} style={{ width: `${w * 100}%` }} />
        <div className="absolute -top-0.5 h-2.5 w-px bg-ink/60" style={{ left: `${100 / SCALE}%` }} aria-hidden />
      </div>
    </div>
  );
}

/** Margin as a small chip, for landing-zone rows and tables. */
export function MarginChip({ load, title }: { load: number | null | undefined; title?: string }) {
  const b = loadBand(load);
  return (
    <span
      title={title ?? `Margin ${fmtMargin(load)}: ${b.label}`}
      className={cx("tnum inline-block rounded-sm bg-surface-2 px-1 py-px font-mono text-[11px]", b.text)}
    >
      {fmtMargin(load)}
    </span>
  );
}

// --------------------------------------------------------------------------- //
// status
// --------------------------------------------------------------------------- //
const STATUS_WORD: Record<CheckStatus, string> = { pass: "Passed", warn: "Warning", fail: "Failed", skip: "Not checked" };

export function StatusIcon({ status, notApplicable, className }: { status: CheckStatus; notApplicable?: boolean; className?: string }) {
  const base = "grid h-5 w-5 shrink-0 place-items-center rounded-full";
  if (status === "skip") {
    const label = notApplicable ? "Not applicable" : "Not checked";
    return <span className={cx(base, "border border-dashed border-ink-faint/60", className)} role="img" aria-label={label} title={label} />;
  }
  const tone = status === "pass" ? "bg-st-ok/15 text-st-ok" : status === "warn" ? "bg-st-warn/15 text-st-warn" : "bg-st-bad/15 text-st-bad";
  const name = status === "pass" ? "check" : status === "warn" ? "alert" : "x";
  return (
    <span className={cx(base, tone, className)} role="img" aria-label={STATUS_WORD[status]} title={STATUS_WORD[status]}>
      <Icon name={name} className="h-3 w-3" />
    </span>
  );
}

const VERDICT: Record<Verdict, { word: string; tone: "ok" | "warn" | "bad" }> = {
  verified: { word: "Verified", tone: "ok" },
  passed_with_warnings: { word: "Passed with warnings", tone: "warn" },
  failed: { word: "Failed", tone: "bad" },
};

const pct = (v: number) => `${Math.round(v * 100)}%`;
const fmtValue = (r: CheckRow) => {
  if (r.value === null || r.value === undefined) return null;
  if (r.unit.startsWith("share")) return pct(r.value);
  return `${Number.isInteger(r.value) ? r.value.toLocaleString() : r.value.toFixed(2)}${r.unit && r.unit !== "share of the limit" ? ` ${r.unit}` : ""}`;
};

function CheckLine({ r }: { r: CheckRow }) {
  const v = fmtValue(r);
  return (
    <li className="flex items-start gap-3 border-b border-line py-2.5 last:border-b-0">
      <StatusIcon status={r.status} notApplicable={r.not_applicable} className="mt-0.5" />
      <div className="min-w-0 flex-1">
        <div className="text-sm font-semibold text-ink">{r.title}</div>
        <p className="mt-0.5 text-sm leading-relaxed text-ink-dim">{r.finding}</p>
        {r.note && <p className="mt-0.5 text-xs leading-snug text-ink-faint">{r.note}</p>}
        {r.source && <p className="mt-1 text-xs leading-snug text-ink-faint">Limit from: {r.source}</p>}
      </div>
      {r.status !== "skip" &&
        (r.load !== null && r.load !== undefined ? (
          <LoadBar load={r.load} className="mt-0.5" />
        ) : v ? (
          <div className="w-28 shrink-0 text-right">
            <div className="tnum font-mono text-sm font-semibold text-ink">{v}</div>
            <div className="text-[10px] text-ink-faint">
              {r.limit === null
                ? "no limit set"
                : `${r.kind === "min" ? "at least" : r.kind === "max" ? "at most" : "should equal"} ${r.limit.toLocaleString()}`}
            </div>
          </div>
        ) : null)}
    </li>
  );
}

function LandingZones({ lz }: { lz: NonNullable<ChecksReport["landing_zones"]> }) {
  if (!lz.candidates.length) return null;
  return (
    <Disclosure title="Landing-zone margins" meta={`${lz.candidates.length} candidates`}>
      <p className="mb-2 text-xs leading-snug text-ink-faint">
        Clear diameter against each aircraft a candidate is listed for, and slope against the slope limit. Limits
        from: {lz.source}.{lz.params_recorded ? "" : " The response file did not record its limits; defaults shown."}
      </p>
      <ul className="divide-y divide-line">
        {lz.candidates.map((c, i) => (
          <li key={`${c.usng}-${i}`} className="flex items-center gap-2 py-1.5 text-sm">
            <StatusIcon status={c.status} />
            <span className="tnum min-w-0 flex-1 truncate font-mono text-xs text-ink">{c.usng ?? "no grid reference"}</span>
            <span className="text-xs text-ink-dim">{c.fits.join(", ")}</span>
            {c.marginal && <Tag>marginal cover</Tag>}
            <MarginChip
              load={c.load}
              title={c.metrics
                .map((m) => `${m.label}: ${m.value ?? "?"} ${m.unit} against ${m.limit ?? "?"} (${fmtMargin(m.load)})`)
                .join("; ")}
            />
          </li>
        ))}
      </ul>
      {lz.caveat && <p className="mt-2 text-xs leading-snug text-ink-faint">{lz.caveat}</p>}
    </Disclosure>
  );
}

type State = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ok"; report: ChecksReport };

async function loadChecks(area: string, signal: AbortSignal): Promise<ChecksReport> {
  const r = await fetch(`${API_URL}/ops/areas/${encodeURIComponent(area)}/checks`, {
    headers: authHeaders(),
    signal,
  });
  if (r.status === 401 || r.status === 403) throw new Error("Responder access is needed to see the checks.");
  if (r.status === 404) throw new Error("This area has no assessment to check yet.");
  if (!r.ok) {
    let detail = "";
    try {
      const j = (await r.json()) as { detail?: unknown };
      if (typeof j.detail === "string") detail = j.detail;
    } catch {
      /* not JSON */
    }
    throw new Error(detail || `The checks could not be loaded (${r.status}).`);
  }
  return (await r.json()) as ChecksReport;
}

export function ChecksPanel({ area }: { area: string }) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [nonce, setNonce] = useState(0);
  const retry = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    // `alive` drops results from a request this effect has already abandoned
    // (area changed, or StrictMode re-ran the effect), so they never overwrite
    // the newer request's state
    let alive = true;
    let timedOut = false;
    const ctl = new AbortController();
    const timer = window.setTimeout(() => {
      timedOut = true;
      ctl.abort();
    }, 60_000);
    setState({ kind: "loading" });
    loadChecks(area, ctl.signal)
      .then((report) => {
        if (alive) setState({ kind: "ok", report });
      })
      .catch((e: Error) => {
        if (!alive) return;
        setState({ kind: "error", message: timedOut ? "The checks took too long to load." : e.message });
      })
      .finally(() => window.clearTimeout(timer));
    return () => {
      alive = false;
      window.clearTimeout(timer);
      ctl.abort();
    };
  }, [area, nonce]);

  if (state.kind === "loading") return <div className="skel mt-4 h-40" aria-label="Loading checks" />;
  if (state.kind === "error")
    return (
      <div className="mt-4 flex items-start gap-3 rounded border border-line-strong p-3 text-sm text-ink-dim">
        <Icon name="alert" className="mt-0.5 text-st-warn" />
        <div className="flex-1">{state.message}</div>
        <Button size="sm" variant="ghost" icon={<Icon name="refresh" className="h-3.5 w-3.5" />} onClick={retry}>
          Try again
        </Button>
      </div>
    );

  const r = state.report;
  const v = VERDICT[r.verdict] ?? VERDICT.passed_with_warnings;
  return (
    <section className="pb-4" aria-label="Self-checks">
      <div className="flex flex-wrap items-center gap-2 pt-3">
        <Tag tone={v.tone}>{v.word}</Tag>
        <span className="text-sm text-ink-dim">{r.summary.replace(/^[^:]*:\s*/, "")}</span>
      </div>
      {r.limiting && (
        <p className="mt-1 text-xs text-ink-faint">
          Least margin: {r.limiting.title.toLowerCase()} ({fmtMargin(r.limiting.load)}).
        </p>
      )}
      <ul className="mt-2">
        {r.checks.map((c) => (
          <CheckLine key={c.id} r={c} />
        ))}
      </ul>
      {r.landing_zones && <LandingZones lz={r.landing_zones} />}
      <p className="mt-3 text-xs leading-snug text-ink-faint">
        {r.note} Role: {r.role}. Run {r.run_id ?? "not recorded"}.
      </p>
    </section>
  );
}

/** The verdict as a small chip for an area header; opens the checks on click.
 * Shows nothing while loading or if the checks cannot be read (the Checks tab
 * says why). */
export function VerdictChip({ area, onOpen }: { area: string; onOpen: () => void }) {
  const [v, setV] = useState<Verdict | null>(null);
  useEffect(() => {
    let alive = true;
    const ctl = new AbortController();
    setV(null);
    loadChecks(area, ctl.signal)
      .then((r) => alive && setV(r.verdict))
      .catch(() => alive && setV(null));
    return () => {
      alive = false;
      ctl.abort();
    };
  }, [area]);
  if (!v) return null;
  const d = VERDICT[v] ?? VERDICT.passed_with_warnings;
  const tone = d.tone === "ok" ? "text-st-ok" : d.tone === "bad" ? "text-st-bad" : "text-st-warn";
  return (
    <button
      type="button"
      onClick={onOpen}
      title="This assessment checked itself: open the checks"
      className={`inline-flex items-center gap-1 rounded border border-line px-1.5 py-px text-2xs font-medium hover:border-line-strong ${tone}`}
    >
      <span aria-hidden className="inline-block h-1.5 w-1.5 rounded-full bg-current" />
      Checks: {d.word.toLowerCase()}
    </button>
  );
}

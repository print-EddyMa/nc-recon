/* SitBrief: the situation brief as a case file. Four to six short items,
 * each citing numbered evidence (E1, E2, ...) that a reader can open in
 * place. Written by fixed rules by default; when the server has a Claude key
 * and a network, a reader can ask Claude to write it from the same evidence,
 * and code (not the model) checks every figure against the evidence. */
import { useCallback, useEffect, useState } from "react";
import { API_URL } from "../../lib/catalog";
import { ago, authHeaders } from "../../lib/ops";
import { Button, Empty, Icon, Spinner, Tag } from "../ui/kit";
import { cx } from "../ui/classes";

export interface SitEvidence {
  id: string;
  label: string;
  value: string | number | null;
  unit: string | null;
  interval: [number, number] | null;
  source: string;
  /** 1 km grid reference of a search sector; shown here, never sent to Claude */
  locator?: string;
}
export interface SitItem {
  kind: "headline" | "damage" | "access" | "search" | "unknown" | "verify";
  title: string;
  text: string;
  evidence: string[];
}
export interface SitBriefData {
  area: string;
  run_id: string | null;
  items: SitItem[];
  evidence: SitEvidence[];
  written_by: "rules" | "claude";
  model: string | null;
  traced: number;
  total: number;
  untraced: string[];
  dropped: { kind: string | null; text: string; reason: string }[];
  ai_error: string | null;
  ai_available: boolean;
  generated_utc: string;
  disclaimer: string;
  notice: string;
}

async function loadSitBrief(area: string, ai: boolean): Promise<SitBriefData> {
  const r = await fetch(`${API_URL}/ops/areas/${encodeURIComponent(area)}/sitbrief?ai=${ai ? 1 : 0}`, {
    headers: authHeaders(),
    signal: AbortSignal.timeout(ai ? 180_000 : 60_000),
  });
  if (!r.ok) {
    let detail = `situation brief: ${r.status}`;
    try {
      const j = (await r.json()) as { detail?: unknown };
      if (typeof j.detail === "string") detail = j.detail;
    } catch {
      /* not JSON */
    }
    if (r.status === 401 || r.status === 403) detail = "Responder access is needed to read the situation brief.";
    throw new Error(detail);
  }
  return (await r.json()) as SitBriefData;
}

const PRINT_CSS = `@media print {
  body * { visibility: hidden; }
  [data-sitbrief], [data-sitbrief] * { visibility: visible; }
  [data-sitbrief] { position: absolute; left: 0; top: 0; width: 100%; padding: 0 12mm; }
}`;

const fmt = (v: SitEvidence["value"]) => (typeof v === "number" ? v.toLocaleString() : (v ?? ""));
function evidenceLine(e: SitEvidence): string {
  const parts = [`${e.label}: ${fmt(e.value)}${e.unit ? ` ${e.unit}` : ""}`];
  if (e.interval) parts.push(`range ${e.interval[0].toLocaleString()} to ${e.interval[1].toLocaleString()}`);
  if (e.locator) parts.push(`grid ${e.locator}`);
  parts.push(`from ${e.source}`);
  return parts.join(" · ");
}

function EvidenceRow({ e }: { e: SitEvidence }) {
  return (
    <div className="flex items-baseline gap-2 text-xs leading-snug">
      <span className="tnum w-8 shrink-0 font-mono font-semibold text-accent">{e.id}</span>
      <span className="min-w-0 flex-1 text-ink">
        {e.label}:{" "}
        <b className="tnum font-mono">
          {fmt(e.value)}
          {e.unit ? ` ${e.unit}` : ""}
        </b>
        {e.interval && (
          <span className="tnum font-mono text-ink-dim">
            {" "}
            (range {e.interval[0].toLocaleString()} to {e.interval[1].toLocaleString()})
          </span>
        )}
        {e.locator && <span className="font-mono text-ink-dim"> · {e.locator}</span>}
      </span>
      <span className="shrink-0 font-mono text-[11px] text-ink-faint">{e.source}</span>
    </div>
  );
}

export default function SitBrief({ area }: { area: string }) {
  const [d, setD] = useState<SitBriefData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<string | null>(null); // "itemIndex:E3"
  const [showAll, setShowAll] = useState(false);

  const load = useCallback(
    (ai: boolean) => {
      setBusy(true);
      setErr(null);
      loadSitBrief(area, ai)
        .then((x) => {
          setD(x);
          setOpen(null);
        })
        .catch((e: Error) => setErr(e.message))
        .finally(() => setBusy(false));
    },
    [area],
  );
  useEffect(() => {
    setD(null);
    load(false);
  }, [load]);

  if (!d && err)
    return (
      <div className="pt-4">
        <Empty icon="file" title="No situation brief">
          {err}
        </Empty>
      </div>
    );
  if (!d) return <div className="skel mt-4 h-48" />;

  const byId = new Map(d.evidence.map((e) => [e.id, e]));
  const allTraced = d.traced === d.total;
  const byline =
    d.written_by === "claude"
      ? `Written by Claude, ${d.traced} of ${d.total} figures traced`
      : "Written by rules";

  return (
    <article data-sitbrief className="pb-4 print:pb-0 print:text-black">
      {/* print only the brief, wherever the console mounts it */}
      <style>{PRINT_CSS}</style>
      <header className="flex flex-wrap items-center gap-2 pt-3">
        <Tag
          tone={d.written_by === "claude" ? (allTraced ? "ok" : "warn") : "neutral"}
          title={
            d.written_by === "claude"
              ? `${d.model ?? "Claude"} wrote this from the evidence list only. Code checked every figure against the evidence.`
              : `Fixed rules wrote this from the evidence list. ${d.traced} of ${d.total} figures traced.`
          }
        >
          <Icon name={d.written_by === "claude" ? "check" : "file"} className="h-3 w-3" />
          {byline}
        </Tag>
        <span className="tnum font-mono text-xs text-ink-faint" title={d.generated_utc}>
          written {ago(d.generated_utc)}
        </span>
        <div className="ml-auto flex items-center gap-2 print:hidden">
          {d.ai_available && d.written_by !== "claude" && (
            <Button size="sm" variant="secondary" onClick={() => load(true)} busy={busy} disabled={busy}>
              Write with Claude
            </Button>
          )}
          {d.written_by === "claude" && (
            <Button size="sm" variant="ghost" onClick={() => load(false)} disabled={busy}>
              {busy ? <Spinner /> : null}
              Rules version
            </Button>
          )}
          <Button size="sm" variant="ghost" icon={<Icon name="download" className="h-3.5 w-3.5" />} onClick={() => window.print()}>
            Print
          </Button>
        </div>
      </header>

      {err && <p className="mt-2 text-xs text-st-bad print:hidden">{err}</p>}
      {d.ai_error && (
        <p className="mt-2 rounded border border-st-warn/40 bg-st-warn/10 p-2 text-xs leading-snug text-ink print:hidden">
          {d.ai_error}. Showing the brief written by rules.
        </p>
      )}

      <ol className="mt-3 space-y-3">
        {d.items.map((it, i) => (
          <li key={`${it.kind}-${i}`} className="break-inside-avoid border-l-2 border-line-strong pl-3">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">{it.title}</div>
            <p className={cx("mt-0.5 leading-relaxed text-ink", it.kind === "headline" ? "text-[15px] font-semibold" : "text-sm")}>
              {it.text}
            </p>
            {it.evidence.length > 0 && (
              <div className="mt-1 flex flex-wrap items-center gap-1">
                <span className="text-[11px] text-ink-faint">Evidence</span>
                {it.evidence.map((id) => {
                  const e = byId.get(id);
                  const key = `${i}:${id}`;
                  return (
                    <button
                      key={id}
                      type="button"
                      title={e ? evidenceLine(e) : id}
                      aria-expanded={open === key}
                      onClick={() => setOpen(open === key ? null : key)}
                      className={cx(
                        "tnum h-5 rounded-sm border px-1.5 font-mono text-[11px] font-semibold",
                        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent",
                        open === key ? "border-accent bg-accent-soft text-accent" : "border-line-strong text-ink-dim hover:text-ink",
                      )}
                    >
                      {id}
                    </button>
                  );
                })}
              </div>
            )}
            {open?.startsWith(`${i}:`) && byId.get(open.split(":")[1]) && (
              <div className="mt-1.5 rounded border border-line bg-surface-2 p-2 print:hidden">
                <EvidenceRow e={byId.get(open.split(":")[1])!} />
              </div>
            )}
          </li>
        ))}
      </ol>

      {d.dropped.length > 0 && (
        <p className="mt-3 text-xs leading-snug text-ink-dim">
          {d.dropped.length === 1 ? "One item Claude wrote was" : `${d.dropped.length} items Claude wrote were`} left
          out because a figure could not be traced to the evidence
          {d.untraced.length > 0 ? ` (${d.untraced.join(", ")})` : ""}.
        </p>
      )}

      <p className="mt-3 rounded border border-st-bad/40 p-2 text-xs font-semibold text-ink">{d.disclaimer}</p>
      <p className="mt-1 text-[11px] leading-snug text-ink-faint">{d.notice}</p>

      <section className="mt-4 break-before-auto">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-ink">Evidence</h3>
          <span className="text-xs text-ink-faint">
            {d.evidence.length} area-level facts{d.run_id ? ` from run ${d.run_id}` : ""}
          </span>
          <Button size="sm" variant="ghost" className="ml-auto print:hidden" onClick={() => setShowAll((v) => !v)}>
            {showAll ? "Hide" : "Show all"}
          </Button>
        </div>
        <div className={cx("mt-2 space-y-1 border-t border-line pt-2", showAll ? "block" : "hidden print:block")}>
          {d.evidence.map((e) => (
            <EvidenceRow key={e.id} e={e} />
          ))}
        </div>
      </section>
    </article>
  );
}

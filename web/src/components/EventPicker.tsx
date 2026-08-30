import { useEffect, useMemo, useRef, useState } from "react";
import { HAZARD_LABEL } from "../lib/events";
import HazardIcon from "./HazardIcon";
import { assessCommands, type CatalogEvent } from "../lib/catalog";
import type { IngestState } from "../lib/useAssess";
import type { EventConfig } from "../lib/types";

interface Props {
  events: EventConfig[]; // ingested
  catalog: CatalogEvent[]; // all 55 Maxar events
  value: string;
  online: boolean | null;
  jobs: Record<string, IngestState>;
  onChange: (id: string) => void;
  onIngest: (ev: { id: string; name: string; center: [number, number] | null }) => void;
  align?: "left" | "right";
}

/**
 * The disaster selector. Lists the events already assessed (click → open) and,
 * below, every other event Maxar Open Data covers (click → ingest, or show the
 * command when there's no pipeline server). One search box over all of it.
 */
export default function EventPicker({
  events,
  catalog,
  value,
  online,
  jobs,
  onChange,
  onIngest,
  align = "right",
}: Props) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [cmdFor, setCmdFor] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const current = events.find((e) => e.id === value) ?? null;
  const ingestedIds = useMemo(() => new Set(events.map((e) => e.id)), [events]);

  const s = q.trim().toLowerCase();
  const readyList = useMemo(
    () =>
      events.filter(
        (e) =>
          !s ||
          e.name.toLowerCase().includes(s) ||
          (e.region ?? "").toLowerCase().includes(s) ||
          HAZARD_LABEL[e.hazard].toLowerCase().includes(s),
      ),
    [events, s],
  );
  const catalogList = useMemo(
    () =>
      catalog
        .filter((e) => !ingestedIds.has(e.id))
        .filter(
          (e) => !s || e.name.toLowerCase().includes(s) || e.hazard.includes(s) || e.id.toLowerCase().includes(s),
        )
        .slice(0, s ? 20 : 8),
    [catalog, ingestedIds, s],
  );

  useEffect(() => {
    if (open) inputRef.current?.focus();
    else {
      setQ("");
      setCmdFor(null);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const doIngest = (e: CatalogEvent) => {
    if (online) onIngest({ id: e.id, name: e.name, center: e.center });
    else setCmdFor((c) => (c === e.id ? null : e.id));
  };

  return (
    <div ref={rootRef} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className={`pressable flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs ${
          current ? "border-line bg-surface-2 text-ink" : "border-accent/50 bg-accent/10 text-ink"
        }`}
      >
        <HazardIcon hazard={current?.hazard ?? "other"} size={13} className="text-ink-dim" />
        <span className="max-w-[13rem] truncate">{current?.name ?? "Choose a disaster"}</span>
        <svg width="10" height="10" viewBox="0 0 12 12" className="text-ink-faint" aria-hidden>
          <path d="M2 4l4 4 4-4" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" />
        </svg>
      </button>

      {open && (
        <div
          className={`panel enter-pop absolute z-40 mt-1.5 w-[25rem] max-w-[calc(100vw-2rem)] p-2.5 ${
            align === "right" ? "right-0" : "left-0"
          }`}
        >
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search any disaster — flood, Nepal, wildfire…"
            className="w-full rounded-md border border-line bg-canvas px-2.5 py-2 text-xs text-ink outline-none placeholder:text-ink-faint focus-visible:border-accent"
          />

          <div className="mt-2.5 max-h-[62vh] space-y-4 overflow-y-auto">
            <div>
              <div className="section-title mb-1.5 px-1">Assessed</div>
              <ul role="listbox" className="space-y-0.5">
                {readyList.map((e) => {
                  const active = e.id === value;
                  const buildings = e.areas.reduce((n, a) => n + (a.n_buildings ?? 0), 0);
                  return (
                    <li key={e.id}>
                      <button
                        role="option"
                        aria-selected={active}
                        onClick={() => {
                          onChange(e.id);
                          setOpen(false);
                        }}
                        className={`pressable flex w-full items-start gap-2.5 rounded-md px-2.5 py-2 text-left ${
                          active ? "bg-surface-2 text-ink" : "text-ink-dim hover:bg-surface-2 hover:text-ink"
                        }`}
                      >
                        <HazardIcon hazard={e.hazard} size={14} className="mt-0.5 shrink-0 text-ink-faint" />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm text-ink">{e.name}</span>
                          <span className="tnum block text-2xs text-ink-faint">
                            {HAZARD_LABEL[e.hazard]}
                            {e.region ? ` · ${e.region}` : ""}
                            {buildings ? ` · ${buildings.toLocaleString()} buildings` : ""}
                          </span>
                        </span>
                        {active && <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />}
                      </button>
                    </li>
                  );
                })}
                {readyList.length === 0 && (
                  <li className="px-2.5 py-1.5 text-2xs text-ink-faint">No assessed event matches.</li>
                )}
              </ul>
            </div>

            <div>
              <div className="mb-1.5 flex items-baseline justify-between px-1">
                <span className="section-title">Maxar Open Data catalogue</span>
                <span className="cap">{online == null ? "" : online ? "ingest live" : "commands"}</span>
              </div>
              <ul className="space-y-0.5">
                {catalogList.map((e) => {
                  const job = jobs[e.id];
                  return (
                    <li key={e.id} className="rounded-md hover:bg-surface-2">
                      <div className="flex items-start gap-2.5 px-2.5 py-2">
                        <HazardIcon hazard={e.hazard} size={14} className="mt-0.5 shrink-0 text-ink-faint" />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm text-ink">{e.name}</span>
                          <span className="tnum block text-2xs text-ink-faint">
                            {HAZARD_LABEL[(e.hazard as keyof typeof HAZARD_LABEL) ?? "other"] ?? e.hazard}
                            {e.capture_dates?.length
                              ? ` · imagery ${e.capture_dates[e.capture_dates.length - 1]}`
                              : ""}
                          </span>
                          {job?.phase === "running" && (
                            <span className="tnum mt-1 block text-2xs text-accent">
                              running · {job.step}
                            </span>
                          )}
                          {job?.phase === "error" && (
                            <span className="mt-1 block text-2xs text-dmg2">{job.error}</span>
                          )}
                        </span>
                        <button
                          onClick={() => doIngest(e)}
                          disabled={job?.phase === "running" || !e.center}
                          className="pressable shrink-0 self-center rounded-md border border-line px-2.5 py-1 text-2xs text-ink-dim hover:border-accent hover:text-ink disabled:opacity-40"
                        >
                          {job?.phase === "running" ? "…" : online ? "Ingest" : "How"}
                        </button>
                      </div>
                      {cmdFor === e.id && (
                        <pre className="mx-2.5 mb-2 overflow-x-auto rounded bg-canvas px-2.5 py-2 text-[10px] leading-relaxed text-ink-dim">
                          {assessCommands({ id: e.id, center: e.center, name: e.name })}
                        </pre>
                      )}
                    </li>
                  );
                })}
                {catalogList.length === 0 && (
                  <li className="px-2.5 py-1.5 text-2xs text-ink-faint">
                    {catalog.length ? "No other Maxar event matches." : "Catalogue not loaded."}
                  </li>
                )}
              </ul>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

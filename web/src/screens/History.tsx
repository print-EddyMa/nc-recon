import { useEffect, useMemo, useRef, useState } from "react";
import { ncFemaHistory, type FemaDeclaration, type NCHistory } from "../lib/nc";
import { archivedRadarImage, dayFrames } from "../lib/radar";
import { prefersReducedMotion } from "../lib/motion";
import type { EventConfig } from "../lib/types";

interface Props {
  areas: { event: EventConfig; area: EventConfig["areas"][number] }[];
  onOpenAssess: () => void;
  onOpenArea: (areaId: string) => void;
}

const DAY = 86_400_000;
// matches nc.ts FEMA_SINCE_YEAR so a 1990-1992 declaration isn't positioned
// off the left edge of the (un-scrollable-past-0) track
const START = Date.UTC(1990, 0, 1);

/** colour + label per FEMA incident type, quiet enough to read as one system */
const TYPE_STYLE: Record<string, { color: string; short: string }> = {
  Hurricane: { color: "#4a80f6", short: "Hurricane" },
  "Tropical Storm": { color: "#5b9bd5", short: "Tropical storm" },
  "Tropical Depression": { color: "#5b9bd5", short: "Tropical depression" },
  Flood: { color: "#2f9e8f", short: "Flood" },
  "Severe Storm": { color: "#7a8794", short: "Severe storm" },
  Fire: { color: "#e56a2b", short: "Fire" },
  "Severe Ice Storm": { color: "#8fb8d8", short: "Ice storm" },
  Snowstorm: { color: "#9db4c8", short: "Snow" },
  "Winter Storm": { color: "#9db4c8", short: "Winter storm" },
  "Mud/Landslide": { color: "#a8794a", short: "Landslide" },
  Biological: { color: "#8a8f98", short: "Biological" },
};
const styleFor = (t: string) =>
  TYPE_STYLE[t] ?? { color: "#8a8f98", short: t };

/** the storms most people in NC would name, labelled at every zoom level */
const LANDMARK =
  /helene|florence|matthew|michael|floyd|fran|hugo|isabel|dorian|irene|ivan|frances|isaias|fred|ophelia/i;
const isLandmark = (d: FemaDeclaration) =>
  d.declarationType === "DR" && LANDMARK.test(d.declarationTitle);

/** post-event Maxar imagery plausibly exists for ~2016 onward */
const hasImageryEra = (d: FemaDeclaration) => d.fyDeclared >= 2016;

const fmtDate = (s: string) =>
  new Date(s).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });

/** FEMA titles are verbose ("HURRICANE FLOYD MAJOR DISASTER DECLARATIONS") */
const cleanTitle = (s: string) =>
  s
    .replace(/\s*(major disaster|emergency)\s+declarations?/i, "")
    .replace(/^remnants of\s+/i, "")
    .replace(/^potential tropical cyclone\s+/i, "PTC ")
    .trim();

/** the bit that fits above a marker */
const shortTitle = (s: string) =>
  cleanTitle(s).replace(/^(Hurricane|Tropical Storm|Tropical Depression)\s+/i, "");

export default function History({ areas, onOpenAssess, onOpenArea }: Props) {
  const [history, setHistory] = useState<NCHistory | null>(null);
  const [pxPerDay, setPxPerDay] = useState(0.13);
  const [selected, setSelected] = useState<FemaDeclaration | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const zoomRaf = useRef(0);
  const pxRef = useRef(pxPerDay);
  pxRef.current = pxPerDay;

  useEffect(() => {
    let alive = true;
    ncFemaHistory().then((h) => {
      if (!alive) return;
      setHistory(h);
      setSelected((cur) => cur ?? h.all.find(isLandmark) ?? h.all[0] ?? null);
    });
    return () => {
      alive = false;
    };
  }, []);

  const now = Date.now();
  const spanDays = (now - START) / DAY;
  const trackW = Math.max(900, spanDays * pxPerDay);
  const xOf = (iso: string) => ((Date.parse(iso) - START) / DAY) * pxPerDay;

  // lane assignment for labelled markers so their text doesn't collide
  const rows = useMemo(() => {
    const list = (history?.all ?? [])
      .filter((d) => d.declarationDate)
      .slice()
      .sort((a, b) => Date.parse(a.declarationDate) - Date.parse(b.declarationDate));
    const laneEnds: number[] = [];
    return list.map((d) => {
      const x = xOf(d.declarationDate);
      const labelled = isLandmark(d) || pxPerDay > 0.8;
      const w = labelled ? Math.max(44, shortTitle(d.declarationTitle).length * 6) : 10;
      let lane = 0;
      if (labelled) {
        while (lane < laneEnds.length && laneEnds[lane] > x) lane++;
        laneEnds[lane] = x + w;
      }
      return { d, x, lane, labelled };
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [history, pxPerDay]);

  // year (and, when zoomed in, month) gridlines
  const ticks = useMemo(() => {
    const out: { x: number; label: string; major: boolean }[] = [];
    const y0 = 1990;
    const y1 = new Date(now).getFullYear();
    const monthly = pxPerDay > 1.4;
    for (let y = y0; y <= y1; y++) {
      out.push({ x: ((Date.UTC(y, 0, 1) - START) / DAY) * pxPerDay, label: String(y), major: true });
      if (monthly) {
        for (let m = 1; m < 12; m++)
          out.push({
            x: ((Date.UTC(y, m, 1) - START) / DAY) * pxPerDay,
            label: new Date(Date.UTC(y, m, 1)).toLocaleDateString(undefined, { month: "short" }),
            major: false,
          });
      }
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pxPerDay]);

  const zoomAt = (factor: number, clientX?: number) => {
    const el = scrollRef.current;
    const cur = pxRef.current;
    const next = Math.min(6, Math.max(0.03, cur * factor));
    if (el && clientX != null) {
      const rect = el.getBoundingClientRect();
      const anchorDay = (el.scrollLeft + clientX - rect.left) / cur;
      requestAnimationFrame(() => {
        el.scrollLeft = anchorDay * next - (clientX - rect.left);
      });
    }
    setPxPerDay(next);
  };

  // wheel-to-zoom, as a non-passive native listener so preventDefault holds
  // (React registers onWheel as passive)
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (!e.deltaY || e.ctrlKey) return;
      e.preventDefault();
      if (zoomRaf.current) return;
      zoomRaf.current = window.setTimeout(() => (zoomRaf.current = 0), 40);
      zoomAt(e.deltaY < 0 ? 1.18 : 1 / 1.18, e.clientX);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // scroll the selected marker into view when it changes
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || !selected) return;
    const x = xOf(selected.declarationDate);
    if (x < el.scrollLeft + 40 || x > el.scrollLeft + el.clientWidth - 40)
      el.scrollTo({ left: Math.max(0, x - el.clientWidth / 2), behavior: "smooth" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, pxPerDay]);

  const presets: [string, number][] = [
    ["30 years", 0.045],
    ["Decade", 0.13],
    ["Year", 0.6],
    ["Month", 2.2],
  ];

  return (
    <div className="flex h-full flex-col overflow-y-auto lg:flex-row lg:overflow-hidden">
      {/* ---- timeline ---- */}
      <div className="flex min-h-0 min-w-0 shrink-0 flex-col px-5 py-4 md:px-8 lg:flex-1">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <div>
            <p className="cap text-ink-faint">North Carolina · federally-declared disasters</p>
            <h1 className="font-display text-xl font-semibold text-ink">
              {history ? `${history.total} declarations since ${history.sinceYear}` : "Disaster history"}
            </h1>
          </div>
          <div className="flex items-center gap-1">
            {presets.map(([label, v]) => (
              <button
                key={label}
                onClick={() => setPxPerDay(v)}
                className={`pressable rounded-md border px-2 py-1 text-2xs ${
                  Math.abs(pxPerDay - v) < 0.02
                    ? "border-accent bg-accent/10 text-ink"
                    : "border-line text-ink-dim hover:text-ink"
                }`}
              >
                {label}
              </button>
            ))}
            <button
              onClick={() => zoomAt(1 / 1.4)}
              className="pressable ml-1 grid h-7 w-7 place-items-center rounded-md border border-line text-ink-dim hover:text-ink"
              aria-label="Zoom out"
            >
              −
            </button>
            <button
              onClick={() => zoomAt(1.4)}
              className="pressable grid h-7 w-7 place-items-center rounded-md border border-line text-ink-dim hover:text-ink"
              aria-label="Zoom in"
            >
              +
            </button>
          </div>
        </div>
        <p className="mt-1 text-2xs text-ink-faint">
          Scroll to pan, scroll-wheel over the track to zoom. Click an event to open it.
        </p>

        <div
          ref={scrollRef}
          className="mt-3 h-[400px] shrink-0 overflow-x-auto overflow-y-hidden rounded-lg border border-line bg-surface sm:h-[460px]"
          tabIndex={0}
          aria-label="Disaster timeline, scroll to pan"
        >
          <div className="relative h-full min-w-full" style={{ width: trackW }}>
            {/* gridlines */}
            {ticks.map((t, i) => (
              <div
                key={i}
                className={`absolute top-0 bottom-0 ${t.major ? "border-l border-line" : "border-l border-line/40"}`}
                style={{ left: t.x }}
              >
                <span
                  className={`absolute bottom-1 left-1 tnum text-2xs ${t.major ? "text-ink-faint" : "text-ink-faint/60"}`}
                >
                  {t.label}
                </span>
              </div>
            ))}
            {/* baseline */}
            <div className="absolute inset-x-0 bottom-8 border-t border-line-strong" />

            {/* markers */}
            {rows.map(({ d, x, lane, labelled }) => {
              const st = styleFor(d.incidentType);
              const sel = selected?.disasterNumber === d.disasterNumber;
              // landmarks rise tall + labelled; other major disasters sit mid;
              // emergency / fire-mgmt declarations stay low. capped so the label
              // never clips off the top of the (overflow-hidden) track
              const base = labelled ? 108 : d.declarationType === "DR" ? 62 : 36;
              const stickH = base + Math.min(lane, 5) * 42;
              return (
                <button
                  key={d.disasterNumber}
                  onClick={() => setSelected(d)}
                  className="pressable group absolute bottom-8 -translate-x-1/2"
                  style={{ left: x }}
                  aria-label={`${d.declarationTitle}, ${fmtDate(d.declarationDate)}`}
                >
                  <span
                    className="block w-px"
                    style={{ height: stickH, background: sel ? "rgb(var(--accent))" : "rgb(var(--line-strong))" }}
                  />
                  <span
                    className="absolute left-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-surface"
                    style={{
                      top: -stickH,
                      width: labelled ? 12 : 9,
                      height: labelled ? 12 : 9,
                      background: st.color,
                      boxShadow: sel ? "0 0 0 3px rgb(var(--accent) / 0.4)" : undefined,
                    }}
                  />
                  {labelled && (
                    <span
                      className={`absolute left-1/2 -translate-x-1/2 whitespace-nowrap rounded px-1 text-2xs ${
                        sel ? "bg-accent text-accent-ink" : "bg-surface text-ink-dim group-hover:text-ink"
                      }`}
                      style={{ top: -stickH - 17 }}
                    >
                      {shortTitle(d.declarationTitle)}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* legend */}
        <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
          {[...new Set((history?.all ?? []).map((d) => d.incidentType))].slice(0, 8).map((t) => (
            <span key={t} className="flex items-center gap-1.5 text-2xs text-ink-faint">
              <span className="h-2 w-2 rounded-full" style={{ background: styleFor(t).color }} />
              {styleFor(t).short}
            </span>
          ))}
        </div>

        {/* what the record shows — a short read + the type breakdown as bars */}
        {history && history.byType.length > 0 && (
          <div className="mt-4 grid gap-x-10 gap-y-4 border-t border-line pt-4 md:grid-cols-[1fr_minmax(15rem,20rem)]">
            <p className="measure text-xs leading-relaxed text-ink-dim">
              Since {history.sinceYear}, North Carolina has drawn{" "}
              <span className="font-semibold text-ink">{history.total}</span> federal disaster
              declarations. Events from 2016 on can be run through the damage pipeline; older ones
              open the archived NWS radar for that day (the archive reaches back to 1995).
            </p>
            <dl className="space-y-1.5">
              {history.byType.slice(0, 6).map((t) => {
                const w = (t.count / history.byType[0].count) * 100;
                return (
                  <div key={t.type} className="flex items-center gap-2.5 text-2xs">
                    <dt className="w-24 shrink-0 truncate text-ink-dim" title={t.type}>
                      {styleFor(t.type).short}
                    </dt>
                    <dd className="bar-track relative m-0 h-2.5 flex-1">
                      <span
                        className="bar-fill absolute inset-y-0 left-0"
                        style={{ width: `${Math.max(w, 3)}%`, background: styleFor(t.type).color }}
                      />
                    </dd>
                    <span className="tnum w-6 shrink-0 text-right font-medium text-ink">
                      {t.count}
                    </span>
                  </div>
                );
              })}
            </dl>
          </div>
        )}
      </div>

      {/* ---- detail ---- */}
      <aside className="w-full shrink-0 overflow-y-auto border-t border-line bg-surface px-5 py-4 md:px-6 lg:w-[24rem] lg:border-l lg:border-t-0">
        {selected ? (
          <EventDetail d={selected} areas={areas} onOpenAssess={onOpenAssess} onOpenArea={onOpenArea} />
        ) : (
          <p className="text-sm text-ink-faint">Select an event on the timeline.</p>
        )}
      </aside>
    </div>
  );
}

function EventDetail({
  d,
  areas,
  onOpenAssess,
  onOpenArea,
}: {
  d: FemaDeclaration;
  areas: Props["areas"];
  onOpenAssess: () => void;
  onOpenArea: (id: string) => void;
}) {
  const st = styleFor(d.incidentType);
  const declLabel =
    d.declarationType === "DR" ? "Major disaster" : d.declarationType === "EM" ? "Emergency" : "Fire mgmt";
  // already-assessed areas whose event shares a storm name with this declaration
  // (FEMA titles it "Tropical Storm Helene", the app calls it "Hurricane Helene")
  const STOP = new Set([
    "hurricane", "tropical", "storm", "storms", "severe", "major", "disaster",
    "declaration", "declarations", "fire", "flood", "flooding", "winter", "snow",
    "ice", "potential", "cyclone", "remnants", "north", "carolina",
  ]);
  const nameWords = (s: string) =>
    (s.toLowerCase().match(/[a-z]{4,}/g) ?? []).filter((w) => !STOP.has(w));
  const dWords = new Set(nameWords(d.declarationTitle));
  const matches = areas.filter(({ event }) =>
    nameWords(event.name).some((w) => dWords.has(w)),
  );
  const imgEra = hasImageryEra(d);

  // Lead with the name the rest of the product uses (events.json, e.g.
  // "Hurricane Helene") when an assessed event maps to this declaration; keep
  // FEMA's own title as a sub-note so the official record still shows.
  const femaTitle = cleanTitle(d.declarationTitle);
  const eventName = matches.length ? matches[0].event.name : null;
  const showFemaNote = !!eventName && eventName.toLowerCase() !== femaTitle.toLowerCase();

  return (
    <div>
      <div className="flex items-center gap-2">
        <span className="h-2.5 w-2.5 rounded-full" style={{ background: st.color }} />
        <span className="cap text-ink-faint">
          {st.short} · {declLabel}
        </span>
      </div>
      <h2 className="mt-1 font-display text-lg font-semibold leading-tight text-ink">
        {eventName ?? femaTitle}
      </h2>
      {showFemaNote && (
        <p className="mt-0.5 text-2xs text-ink-faint">FEMA declaration title: {femaTitle}</p>
      )}
      <dl className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-2xs text-ink-faint">
        <div>
          <dt className="inline text-ink-dim">Declared</dt>{" "}
          <dd className="tnum inline">{fmtDate(d.declarationDate)}</dd>
        </div>
        {d.incidentBeginDate && (
          <div>
            <dt className="inline text-ink-dim">Incident</dt>{" "}
            <dd className="tnum inline">{fmtDate(d.incidentBeginDate)}</dd>
          </div>
        )}
        <div>
          <dt className="inline text-ink-dim">FEMA</dt>{" "}
          <dd className="tnum inline">
            {d.declarationType ?? "DR"}-{d.disasterNumber}
          </dd>
        </div>
      </dl>
      <a
        href={`https://www.fema.gov/disaster/${d.disasterNumber}`}
        target="_blank"
        rel="noreferrer"
        className="pressable mt-2 inline-block text-2xs text-accent hover:underline"
      >
        FEMA declaration page ↗
      </a>

      <div className="mt-4 border-t border-line pt-3">
        {imgEra ? (
          <>
            {matches.length > 0 ? (
              <>
                <p className="text-xs leading-relaxed text-ink-dim">
                  {matches.length === 1 ? "One area has" : `${matches.length} areas have`} been
                  assessed for this event.
                </p>
                <ul className="mt-2.5 divide-y divide-line border-y border-line">
                  {matches.map(({ area }) => (
                    <li key={area.id}>
                      <button
                        onClick={() => onOpenArea(area.id)}
                        className="pressable flex w-full items-center justify-between gap-2 py-2 text-left text-xs text-ink-dim hover:text-ink"
                      >
                        <span className="font-medium text-ink">{area.name}</span>
                        <span className="text-accent">damage map →</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <>
                <p className="text-xs leading-relaxed text-ink-dim">
                  This is recent enough that post-event Maxar Open Data imagery likely
                  exists. Run the damage pipeline on an affected North Carolina area.
                </p>
                <button
                  onClick={onOpenAssess}
                  className="pressable mt-2 w-full rounded-md bg-accent py-2 text-xs font-semibold text-accent-ink"
                >
                  Assess an affected area
                </button>
              </>
            )}
          </>
        ) : (
          <>
            <p className="text-xs leading-relaxed text-ink-dim">
              This predates building-damage satellite coverage. Here is the
              meteorological record instead: archived NWS radar over North
              Carolina for that day.
            </p>
            <HistoricalRadar dateStr={d.incidentBeginDate ?? d.declarationDate} />
          </>
        )}
      </div>
    </div>
  );
}

function HistoricalRadar({ dateStr }: { dateStr: string }) {
  const frames = useMemo(() => dayFrames(dateStr), [dateStr]);
  const [i, setI] = useState(2); // midday
  useEffect(() => {
    if (prefersReducedMotion()) return;
    const t = window.setInterval(() => {
      if (!document.hidden) setI((v) => (v + 1) % frames.length);
    }, 1600);
    return () => window.clearInterval(t);
  }, [frames.length]);

  const src = archivedRadarImage(new Date(frames[i].iso));
  return (
    <figure className="mt-2">
      <div className="relative aspect-[720/460] w-full overflow-hidden rounded-md border border-line bg-surface-2">
        {src ? (
          <img
            src={src}
            alt={`NWS radar over North Carolina, ${dateStr.slice(0, 10)} ${frames[i].label}`}
            className="absolute inset-0 h-full w-full object-cover"
            loading="lazy"
          />
        ) : (
          <div className="grid h-full place-items-center text-2xs text-ink-faint">
            radar archive starts 1995
          </div>
        )}
        <span className="absolute bottom-1 right-1.5 tnum rounded bg-surface/80 px-1 text-2xs text-ink-faint">
          {dateStr.slice(0, 10)} · {frames[i].label}
        </span>
      </div>
      <figcaption className="mt-1 flex items-center justify-between text-2xs text-ink-faint">
        <span>Iowa Environmental Mesonet · NEXRAD archive</span>
        <span className="flex gap-1">
          {frames.map((f, k) => (
            <button
              key={f.iso}
              onClick={() => setI(k)}
              className={`pressable h-1.5 w-1.5 rounded-full ${k === i ? "bg-accent" : "bg-line-strong"}`}
              aria-label={`Radar at ${f.label}`}
            />
          ))}
        </span>
      </figcaption>
    </figure>
  );
}

import { useMemo } from "react";
import { summarize } from "../lib/data";
import { DAMAGE } from "../lib/damage";
import { useReviewDecisions, overrideClasses } from "../lib/review";
import type { AreaConfig, DamageCollection, EventConfig } from "../lib/types";

interface Props {
  event: EventConfig;
  area: AreaConfig;
  fc: DamageCollection | null;
  onOpenMap: () => void;
}

/** Turn the pipeline's model slug into something readable. */
function modelLabel(raw: string): string {
  if (raw.startsWith("fusion:")) return "xView2 CMU classifier + change-detection fusion";
  if (raw.startsWith("xview2_baseline:")) return "xView2 CMU baseline classifier";
  if (raw.startsWith("heuristic:")) return "Change-detection heuristic";
  return raw;
}

export default function Stats({ event, area, fc, onOpenMap }: Props) {
  const { decisions } = useReviewDecisions(area.id);
  const stats = useMemo(() => (fc ? summarize(fc) : null), [fc]);
  const reviewed = useMemo(
    () => (fc ? summarize(fc, overrideClasses(decisions)) : null),
    [fc, decisions],
  );

  if (!fc || !stats) {
    return (
      <div className="mx-auto max-w-4xl px-6 py-10">
        <div className="skel h-4 w-64" />
        <div className="skel mt-4 h-12 w-full max-w-2xl" />
        <div className="skel mt-2 h-12 w-4/5 max-w-2xl" />
        <div className="mt-10 grid grid-cols-2 gap-6 sm:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="skel h-14" />
          ))}
        </div>
      </div>
    );
  }

  const total = stats.total || 1;
  const p = fc.properties;
  const reviewedDelta = reviewed && reviewed.severe !== stats.severe ? reviewed.severe : null;

  return (
    <div className="mx-auto h-full max-w-4xl overflow-y-auto px-6 py-10">
      <p className="cap mb-3">
        Summary · {event.name} · {area.name}
        {area.subtitle ? `, ${area.subtitle}` : ""}
      </p>

      <h1 className="max-w-3xl font-display text-[2rem] leading-[1.12] text-ink">
        <span className="tnum text-dmg2">{stats.severe.toLocaleString()}</span> of{" "}
        <span className="tnum">{stats.total.toLocaleString()}</span> buildings sustained
        major damage or were destroyed.
      </h1>

      <p className="mt-4 max-w-[64ch] text-sm leading-relaxed text-ink-dim">
        {event.name}
        {event.event_date ? `, event date ${event.event_date}. ` : ". "}
        Maxar Open Data captures from <span className="tnum">{p.pre_image.date}</span>{" "}
        and <span className="tnum">{p.post_image.date}</span>.
        {reviewedDelta != null && (
          <>
            {" "}
            After human review the severe count stands at{" "}
            <span className="tnum text-ink">{reviewedDelta.toLocaleString()}</span>.
          </>
        )}
      </p>

      {/* asymmetric figure block: lead percentage + supporting ticks */}
      <div className="mt-10 flex flex-col gap-8 sm:flex-row sm:items-end sm:gap-14">
        <div>
          <div className="cap mb-1.5">Major or destroyed</div>
          <div className="tnum text-6xl font-semibold leading-none text-dmg2">
            {stats.severePct.toFixed(1)}
            <span className="text-3xl text-ink-faint">%</span>
          </div>
        </div>
        <dl className="grid grid-cols-2 gap-x-10 gap-y-5 sm:grid-cols-3">
          <Tick k="Buildings assessed" v={stats.total.toLocaleString()} />
          <Tick k="Destroyed" v={stats.counts[3].toLocaleString()} accent={DAMAGE[3].hex} />
          <Tick k="Footprint area" v={`${stats.assessedAreaKm2.toFixed(2)} km²`} />
        </dl>
      </div>

      <section className="mt-12 border-t border-line pt-6">
        <div className="section-title mb-4">Distribution by damage level</div>
        <div className="space-y-3">
          {DAMAGE.map((d) => {
            const n = stats.counts[d.index];
            const pct = (n / total) * 100;
            return (
              <div key={d.index} className="flex items-center gap-3">
                <span className="w-24 shrink-0 text-xs text-ink-dim">{d.label}</span>
                <span className="relative h-4 flex-1 overflow-hidden rounded-sm bg-surface-2">
                  <span
                    className="absolute inset-y-0 left-0 transition-[width] duration-500 ease-out"
                    style={{ width: `${Math.max(pct, 0.6)}%`, background: d.hex }}
                  />
                </span>
                <span className="tnum w-14 shrink-0 text-right text-sm text-ink">
                  {n.toLocaleString()}
                </span>
                <span className="tnum w-14 shrink-0 text-right text-xs text-ink-faint">
                  {pct.toFixed(1)}%
                </span>
              </div>
            );
          })}
        </div>
      </section>

      <section className="mt-10 flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-line pt-5 text-xs text-ink-faint">
        <button
          onClick={onOpenMap}
          className="pressable rounded-md border border-line px-3 py-1.5 text-ink-dim hover:border-accent hover:text-ink"
        >
          View on map →
        </button>
        {p.review && (
          <span className="tnum">
            {p.review.total_review.toLocaleString()} flagged for review
            {p.review.model_agreement_pct != null
              ? ` · ${p.review.model_agreement_pct}% model agreement`
              : ""}
          </span>
        )}
        <span>
          {modelLabel(p.model)}
          {p.runtime_sec ? ` · ${p.runtime_sec}s` : ""}
        </span>
      </section>

      {p.notes && (
        <p className="mt-4 max-w-[74ch] text-2xs leading-relaxed text-ink-faint">{p.notes}</p>
      )}
    </div>
  );
}

function Tick({ k, v, accent }: { k: string; v: string; accent?: string }) {
  return (
    <div className="border-l border-line pl-3">
      <dt className="cap mb-1">{k}</dt>
      <dd
        className="tnum m-0 text-xl font-semibold text-ink"
        style={accent ? { color: accent } : undefined}
      >
        {v}
      </dd>
    </div>
  );
}

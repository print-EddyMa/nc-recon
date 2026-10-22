/* Checks: the area's calls held up against every published field record and
 * measurement that covers it. Each kind of record answers a different
 * question, so each gets its own shape:
 *   full-level records (inspectors, search teams, FEMA)  agreement both ways
 *   positives-only records (damage points)               how much was found
 *   lidar ground change                                  where the ground moved
 * The caveats are always shown: they carry the honesty. */
import { useEffect, useState } from "react";
import { FEMA, FEMA_LABEL, loadReferences, type AreaReference, type FemaClass } from "../../lib/ops";
import { Disclosure, Empty, Swatch, Tag } from "../ui/kit";

const n0 = (v: unknown) => Math.round(Number(v ?? 0)).toLocaleString();
const pct = (v: unknown) => (v == null ? "n/a" : `${Math.round(Number(v) * 100)}%`);

const KIND: Record<string, string> = {
  dins: "Ground inspection",
  fema_hgda: "FEMA damage assessment",
  sarcop: "Search team calls",
  nemac: "Damage points",
  lidar: "Lidar ground change",
};

export default function References({ areaId, onAny }: { areaId: string; onAny?: (any: boolean) => void }) {
  const [refs, setRefs] = useState<AreaReference[] | null | "none">(null);
  useEffect(() => {
    let live = true;
    loadReferences(areaId)
      .then((d) => {
        if (!live) return;
        setRefs(d.references);
        onAny?.(d.references.length > 0);
      })
      .catch(() => {
        if (!live) return;
        setRefs("none");
        onAny?.(false);
      });
    return () => {
      live = false;
    };
  }, [areaId, onAny]);
  if (refs === null) return <div className="skel mt-4 h-40" />;
  if (refs === "none" || refs.length === 0)
    return (
      <div className="pt-4">
        <Empty icon="check" title="No field record covers this area yet">
          Comparisons appear here when inspectors, search teams or a lidar survey cover the same ground.
        </Empty>
      </div>
    );
  return (
    <div className="divide-y divide-line">
      <p className="pt-4 pb-3 text-xs leading-relaxed text-ink-dim">
        {refs.length} independent record{refs.length > 1 ? "s" : ""} cover this area. None is an accuracy figure:
        each was made at a different time, by a different method.
      </p>
      {refs.map((r) =>
        r.source === "lidar" ? (
          <LidarRef key={r.source} r={r} />
        ) : r.source === "nemac" ? (
          <PositivesRef key={r.source} r={r} />
        ) : (
          <FullRef key={r.source} r={r} />
        ),
      )}
    </div>
  );
}

function Head({ r }: { r: AreaReference }) {
  return (
    <div className="flex items-start gap-2">
      <div className="min-w-0 flex-1">
        <h2 className="text-sm">{KIND[r.source] ?? r.source}</h2>
        {r.reference?.name && (
          <a
            href={r.reference.url}
            target="_blank"
            rel="noreferrer"
            className="text-xs text-ink-dim underline decoration-line-strong underline-offset-2 hover:text-ink"
          >
            {r.reference.name}
          </a>
        )}
      </div>
      {r.role === "TEST" && <Tag tone="accent">held out</Tag>}
    </div>
  );
}

function Caveats({ r, extra }: { r: AreaReference; extra?: string }) {
  return (
    <div className="mt-3">
      <Disclosure title="How to read this" meta={`${r.caveats.length + (extra ? 1 : 0)} notes`}>
        <ul className="list-disc space-y-1 pl-4 text-xs leading-relaxed text-ink-dim">
          {r.caveats.map((c) => (
            <li key={c}>{c}</li>
          ))}
          {extra && <li>{extra}</li>}
        </ul>
      </Disclosure>
    </div>
  );
}

function Pair({ big, of, text }: { big: unknown; of: unknown; text: string }) {
  return (
    <div className="rounded border border-line p-2.5">
      <div className="tnum font-mono text-xl font-semibold text-ink">
        {n0(big)} <span className="text-sm font-normal text-ink-faint">of {n0(of)}</span>
      </div>
      <div className="mt-0.5 text-xs leading-snug text-ink-dim">{text}</div>
    </div>
  );
}

type Full = {
  n: number;
  levels: string[];
  confusion_rows_sar_cols_ncr: number[][];
  same_level: number | null;
  within_one_level: number | null;
  sar_level_in_80pct_set: number | null;
  major_or_destroyed: { both_count: number; sar_count: number; ncr_most_likely_count: number };
};

function FullRef({ r }: { r: AreaReference }) {
  const s = r.summary as unknown as Full | null;
  if (!s || !s.n)
    return (
      <section className="py-4">
        <Head r={r} />
        <p className="mt-2 text-xs text-ink-dim">No record matched an assessed structure.</p>
        <Caveats r={r} />
      </section>
    );
  const m = s.major_or_destroyed;
  const h = r.summary_homes as unknown as Full | null;
  const max = Math.max(1, ...s.confusion_rows_sar_cols_ncr.flat());
  return (
    <section className="py-4">
      <Head r={r} />
      <div className="mt-3 grid grid-cols-2 gap-2">
        <Pair big={m.both_count} of={m.ncr_most_likely_count} text="of our Major or Destroyed calls, the record agrees" />
        <Pair big={m.both_count} of={m.sar_count} text="of the record's Major or Destroyed, found from imagery" />
      </div>
      {h && h.n > 0 && (
        <p className="mt-2 text-xs text-ink-dim">
          Homes only ({n0(h.n)}): agreed {n0(h.major_or_destroyed.both_count)} of{" "}
          {n0(h.major_or_destroyed.ncr_most_likely_count)}; found {n0(h.major_or_destroyed.both_count)} of{" "}
          {n0(h.major_or_destroyed.sar_count)}.
        </p>
      )}
      <p className="mt-2 text-xs text-ink-dim">
        {n0(s.n)} structures in both · same level {pct(s.same_level)} · within one level {pct(s.within_one_level)} ·
        record level inside our 80% set {pct(s.sar_level_in_80pct_set)}
      </p>
      <table className="tnum mt-3 w-full text-xs">
        <caption className="sr-only">Structures by record level (rows) and most likely level from imagery (columns)</caption>
        <thead>
          <tr className="text-ink-faint">
            <th className="text-left font-medium">Record ↓ · imagery →</th>
            {s.levels.map((l) => (
              <th key={l} className="px-0.5 text-center font-medium">
                {l.split(" ")[0]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {s.confusion_rows_sar_cols_ncr.map((row, i) => (
            <tr key={s.levels[i]}>
              <th scope="row" className="py-0.5 pr-1 text-left font-normal text-ink-dim">
                {s.levels[i]}
              </th>
              {row.map((v, j) => (
                <td key={j} className="p-0.5">
                  <div
                    className={`grid h-6 place-items-center rounded-sm font-mono ${
                      i === j ? "font-semibold text-ink ring-1 ring-inset ring-ink/30" : "text-ink-dim"
                    }`}
                    style={{ background: v ? `rgb(var(--accent) / ${0.08 + 0.5 * (v / max)})` : undefined }}
                  >
                    {v}
                  </div>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <Caveats r={r} extra={r.match_rule} />
    </section>
  );
}

type Positives = {
  n: number;
  destroyed_points: number;
  ncr_major_or_destroyed_at_destroyed: number;
  damaged_points: number;
  ncr_any_damage_at_damaged: number;
  ncr_minor_or_worse_at_damaged: number;
  by_cause?: Record<string, { n: number; ncr_any_damage: number; ncr_major_or_destroyed: number }>;
};

/** A record of damaged buildings only: there are no "undamaged" points, so
 * only "how much of what they saw did we find" can be asked of it. */
function PositivesRef({ r }: { r: AreaReference }) {
  const s = r.summary as unknown as Positives | null;
  return (
    <section className="py-4">
      <Head r={r} />
      {s && s.n > 0 ? (
        <>
          <div className="mt-3 space-y-2">
            <Found label="Marked destroyed: we called Major or Destroyed" n={s.destroyed_points} share={s.ncr_major_or_destroyed_at_destroyed} />
            <Found label="Marked damaged: we called any damage" n={s.damaged_points} share={s.ncr_any_damage_at_damaged} />
          </div>
          {s.by_cause && (
            <table className="tnum mt-3 w-full text-xs">
              <caption className="sr-only">Found by cause of damage</caption>
              <thead>
                <tr className="text-xs text-ink-faint">
                  <th className="text-left font-medium">Cause</th>
                  <th className="text-right font-medium">Points</th>
                  <th className="text-right font-medium">Any damage found</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(s.by_cause).map(([k, v]) => (
                  <tr key={k} className="border-t border-line">
                    <td className="py-1 capitalize text-ink">{k}</td>
                    <td className="py-1 text-right font-mono text-ink">{n0(v.n)}</td>
                    <td className="py-1 text-right font-mono text-ink">{pct(v.ncr_any_damage)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      ) : (
        <p className="mt-2 text-xs text-ink-dim">No record matched an assessed structure.</p>
      )}
      <Caveats
        r={r}
        extra="Damaged buildings only: no precision or agreement figure can be computed from this record."
      />
    </section>
  );
}

function Found({ label, n, share }: { label: string; n: number; share: number }) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2 text-xs">
        <span className="text-ink-dim">{label}</span>
        <span className="tnum font-mono text-ink">
          <b>{pct(share)}</b> <span className="text-ink-faint">of {n0(n)}</span>
        </span>
      </div>
      <div className="bar-track mt-1 h-1.5">
        <div className="bar-fill bg-accent" style={{ width: `${Math.round(share * 100)}%` }} />
      </div>
    </div>
  );
}

function LidarRef({ r }: { r: AreaReference }) {
  const fc = r.flag_counts ?? {};
  const by = r.flagged_by_ncr_level ?? {};
  return (
    <section className="py-4">
      <Head r={r} />
      <p className="mt-1 text-xs text-ink-dim">
        Ground around {n0(r.measured)} of {n0(r.structures)} structures measured before and after. Typical change{" "}
        <span className="tnum font-mono text-ink">{(r.typical_change_m ?? 0).toFixed(2)} m</span>.
      </p>
      <div className="mt-3 grid grid-cols-2 gap-2">
        <div className="rounded border border-line p-2.5">
          <div className="tnum font-mono text-xl font-semibold text-ink">{n0(fc.deposit)}</div>
          <div className="text-xs text-ink-dim">with material deposited around them</div>
        </div>
        <div className="rounded border border-line p-2.5">
          <div className="tnum font-mono text-xl font-semibold text-ink">{n0(fc.scour)}</div>
          <div className="text-xs text-ink-dim">with ground scoured away</div>
        </div>
      </div>
      {Object.keys(by).length > 0 && (
        <div className="mt-3">
          <div className="text-xs text-ink-faint">Flagged structures by our most likely level</div>
          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs">
            {FEMA.filter((c) => by[c]).map((c: FemaClass) => (
              <span key={c} className="inline-flex items-center gap-1 text-ink">
                <Swatch c={c} /> {FEMA_LABEL[c]} <b className="tnum font-mono">{by[c]}</b>
              </span>
            ))}
          </div>
        </div>
      )}
      <Caveats r={r} extra={r.rule} />
    </section>
  );
}

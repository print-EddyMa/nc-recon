// The Groma Index: a public, preliminary damage summary for every assessed
// area. Counts with an 80% range, roads cut, people cut off. Nothing about
// any one building. The same records are JSON at /ops/index for other apps.
import { useEffect, useState } from "react";
import { DamageStrip, Spinner } from "../components/ui/kit";
import { FEMA, FEMA_HEX, FEMA_LABEL, type FemaClass } from "../lib/ops";
import { indexUrl, loadIndex, loadIndexRecord, type IndexRecord } from "../lib/owner";
import { HeroTitle, PublicShell } from "./public/Shell";

const n = (v: number | null | undefined) => (v == null ? "n/a" : Math.round(v).toLocaleString("en-US"));
const usd = (v: number) =>
  v >= 1e6 ? `$${(v / 1e6).toFixed(v >= 1e7 ? 0 : 1)}M` : `$${Math.round(v / 1e3).toLocaleString("en-US")}K`;

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="border-t border-line pt-3">
      <dt className="text-xs text-ink-faint">{label}</dt>
      <dd className="tnum mt-1 text-lg text-ink">{value}</dd>
      {note && <dd className="text-xs text-ink-faint">{note}</dd>}
    </div>
  );
}

function Area({ r }: { r: IndexRecord }) {
  const exp = Object.fromEntries(FEMA.map((c) => [c, r.damage[c]?.expected ?? 0])) as Record<FemaClass, number>;
  const sev = r.major_or_destroyed;
  return (
    <article className="grid gap-8 border-t border-line py-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.35fr)] lg:gap-14" aria-labelledby={`h-${r.area}`}>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h2 id={`h-${r.area}`} className="text-[32px] font-medium leading-none tracking-[-0.03em]">
            {r.name}
          </h2>
          <span className="rounded-full border border-line-strong px-2.5 py-0.5 text-[11px] text-ink-dim">{r.status}</span>
        </div>
        <p className="mt-2 text-ink-dim">
          {r.event.name} · {r.event.declarations.join(", ")}
        </p>
        <p className="text-ink-dim">
          {r.county ? `${r.county} County, ` : ""}
          {r.state}
        </p>
        <p className="mt-5 max-w-[46ch] text-sm text-ink-dim">{r.validation}</p>
        <p className="mt-3 text-xs text-ink-faint">
          Imagery after: {r.imagery.after ?? "unknown"} · assessed {r.assessed_utc?.slice(0, 10)}
        </p>
        <a className="btn-pill mt-5" href={indexUrl(r.area)}>
          This record as JSON
        </a>
      </div>
      <div className="min-w-0">
        <p className="tnum text-[clamp(4.5rem,10vw,7.5rem)] font-medium leading-[0.85] tracking-[-0.05em]">
          {n(sev.expected)}
        </p>
        <p className="mt-3 max-w-[40ch] text-ink-dim">
          buildings expected Major or Destroyed, 80% range {n(sev.range_80[0])} to {n(sev.range_80[1])}, of{" "}
          {n(r.buildings.assessed)} assessed.
        </p>
        <DamageStrip counts={exp} height={10} className="mt-5 rounded-full" />
        <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-dim" aria-label="Expected by level">
          {FEMA.map((c) => (
            <li key={c} className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-[2px]" style={{ background: FEMA_HEX[c] }} aria-hidden />
              {FEMA_LABEL[c]} <span className="tnum text-ink">{n(exp[c])}</span>
            </li>
          ))}
        </ul>
        <dl className="mt-6 grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4">
          {r.access && <Stat label="Road segments cut" value={n(r.access.road_segments_blocked)} />}
          {r.access && (
            <Stat label="People cut off" value={n(r.access.people_cut_off.if_debris_blocks_roads)} note="if debris blocks roads" />
          )}
          {r.debris_cubic_yards && (
            <Stat label="Debris, cubic yards" value={`${n(r.debris_cubic_yards.low)} to ${n(r.debris_cubic_yards.high)}`} />
          )}
          {r.building_loss_usd && (
            <Stat label="Building loss" value={`${usd(r.building_loss_usd.low)} to ${usd(r.building_loss_usd.high)}`} />
          )}
        </dl>
      </div>
    </article>
  );
}

export default function IndexPage() {
  const [recs, setRecs] = useState<IndexRecord[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    loadIndex()
      .then((l) => Promise.all(l.areas.map((a) => loadIndexRecord(a.area))))
      .then(setRecs)
      .catch((e: Error) => setErr(e.message));
  }, []);
  const read = recs?.reduce((t, r) => t + r.buildings.assessed, 0) ?? 0;

  return (
    <PublicShell
      current="index"
      hero={
        <div className="grid gap-8 md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
          <div>
            <HeroTitle>The Groma Index</HeroTitle>
            <p className="mt-5 max-w-[50ch] text-lg leading-relaxed text-ink-dim">
              Preliminary damage counts for every area Groma has assessed from public imagery, each with an 80% range.
              Nothing here describes any one building. Newsrooms, aid groups and other apps can read the same
              records as JSON.
            </p>
            <div className="mt-7 flex flex-wrap gap-3">
              <a className="btn-pill primary" href={indexUrl()}>
                Read the JSON
              </a>
              <a className="btn-pill" href="#/check">
                Check a street
              </a>
            </div>
          </div>
          {recs && recs.length > 0 && (
            <dl className="tnum grid grid-cols-2 gap-8 border-t border-line pt-5 md:border-l md:border-t-0 md:pl-8 md:pt-0">
              <div>
                <dt className="text-xs text-ink-faint">Areas</dt>
                <dd className="text-[40px] font-medium leading-none tracking-[-0.03em]">{recs.length}</dd>
              </div>
              <div>
                <dt className="text-xs text-ink-faint">Buildings read</dt>
                <dd className="text-[40px] font-medium leading-none tracking-[-0.03em]">{n(read)}</dd>
              </div>
            </dl>
          )}
        </div>
      }
    >
      {err && (
        <p role="alert" className="text-sm text-st-bad">
          {err}
        </p>
      )}
      {!recs && !err && (
        <div className="flex items-center gap-2 text-ink-dim">
          <Spinner /> Loading the index…
        </div>
      )}
      {recs?.length === 0 && <p className="text-ink-dim">No areas have been assessed yet.</p>}
      {recs?.map((r) => <Area key={r.area} r={r} />)}
    </PublicShell>
  );
}

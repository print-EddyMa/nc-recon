// The owner's evidence record: one building, opened from a private link a
// partner sent (legal aid, the county). Printable; nothing here is public.
import { useEffect, useState } from "react";
import { Spinner } from "../components/ui/kit";
import { FEMA, FEMA_HEX, FEMA_LABEL, type FemaClass } from "../lib/ops";
import { loadRecord, loadRecordChip, type OwnerRecord } from "../lib/owner";
import { PublicShell } from "./public/Shell";

const day = (iso: string | null | undefined) => (iso ? iso.slice(0, 10) : "unknown");
// parcel data stores addresses in capitals; a record a person keeps reads better in title case
const titleCase = (a: string) =>
  a === a.toUpperCase() ? a.toLowerCase().replace(/\b([a-z])/g, (m) => m.toUpperCase()) : a;

export default function Record({ token }: { token: string }) {
  const [rec, setRec] = useState<OwnerRecord | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [chips, setChips] = useState<{ pre: string | null; post: string | null }>({ pre: null, post: null });

  useEffect(() => {
    let live = true;
    const urls: string[] = [];
    loadRecord(token)
      .then(async (r) => {
        if (!live) return;
        setRec(r);
        const [pre, post] = await Promise.all([loadRecordChip(token, "pre"), loadRecordChip(token, "post")]);
        for (const u of [pre, post]) if (u) urls.push(u);
        if (live) setChips({ pre, post });
      })
      .catch((e: Error) => live && setErr(e.message));
    return () => {
      live = false;
      urls.forEach((u) => URL.revokeObjectURL(u));
    };
  }, [token]);

  if (err)
    return (
      <PublicShell current="record">
        <h1 className="text-[36px] font-medium tracking-[-0.03em]">This record cannot be opened</h1>
        <p className="mt-3 max-w-[52ch] text-ink-dim">{err}</p>
        <a href="#/check" className="btn-pill mt-6">
          Check a street instead
        </a>
      </PublicShell>
    );
  if (!rec)
    return (
      <PublicShell current="record">
        <div className="flex items-center gap-2 text-ink-dim">
          <Spinner /> Opening your record…
        </div>
      </PublicShell>
    );

  const lvl = (rec.level ?? null) as FemaClass | null;
  return (
    <PublicShell current="record">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-sm text-ink-faint">Building record · {rec.event}</p>
          <h1 className="mt-2 text-[clamp(2rem,4.5vw,3.25rem)] font-medium leading-[1.05] tracking-[-0.03em]">
            {rec.address ? titleCase(rec.address) : `US National Grid ${rec.usng_10m}`}
          </h1>
          <p className="mt-2 text-ink-dim">
            {rec.county ? `${rec.county} County, ` : ""}
            {rec.state} · US National Grid {rec.usng_10m}
          </p>
        </div>
        <button type="button" onClick={() => window.print()} className="btn-pill print:hidden">
          Print or save as PDF
        </button>
      </div>

      <div className="mt-10 grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <section aria-labelledby="call" className="min-w-0">
          <h2 id="call" className="text-sm text-ink-faint">
            What the imagery shows
          </h2>
          <div className="mt-2 flex flex-wrap items-baseline gap-x-4 gap-y-1">
            <span
              className="inline-block h-4 w-4 translate-y-[-0.2rem] rounded-[3px] ring-1 ring-inset ring-black/15"
              style={{ background: lvl ? FEMA_HEX[lvl] : "#777" }}
              aria-hidden
            />
            <span className="text-[clamp(2.75rem,6vw,4.25rem)] font-medium leading-none tracking-[-0.04em]">{rec.level_label}</span>
            {rec.probability != null && (
              <span className="tnum text-lg text-ink-dim">{Math.round(rec.probability * 100)}% likely</span>
            )}
          </div>
          <p className="mt-4 rounded-xl border border-line bg-surface p-4 text-sm">
            <b className="font-semibold">Not confirmed by anyone at the building.</b> This is a remote assessment from
            imagery
            {rec.confirmed_by_people
              ? `. People reviewing the imagery without seeing Groma's answer agreed on ${rec.people_checked.label}.`
              : rec.needs_review
                ? ". It is flagged for people to check."
                : "."}
          </p>
          {Object.keys(rec.probs).length > 0 && (
            <ul className="mt-5 grid gap-2 text-sm" aria-label="Probability of each damage level">
              {FEMA.map((c) => {
                const v = rec.probs[FEMA_LABEL[c]] ?? 0;
                return (
                  <li key={c} className="grid grid-cols-[7rem_1fr_3rem] items-center gap-3">
                    <span className={c === lvl ? "font-semibold" : "text-ink-dim"}>{FEMA_LABEL[c]}</span>
                    <span className="h-2 overflow-hidden rounded-full bg-surface-2">
                      <span className="block h-full rounded-full" style={{ width: `${v * 100}%`, background: FEMA_HEX[c] }} />
                    </span>
                    <span className="tnum text-right text-ink-dim">{Math.round(v * 100)}%</span>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        <section className="grid min-w-0 grid-cols-2 gap-3 self-start" aria-label="Before and after imagery">
          {(["pre", "post"] as const).map((k) => (
            <figure key={k} className="m-0 min-w-0">
              <div className="aspect-square overflow-hidden rounded-xl border border-line bg-surface-2">
                {chips[k] ? (
                  <img src={chips[k]!} alt={k === "pre" ? "Before the disaster" : "After the disaster"} className="h-full w-full object-cover" />
                ) : (
                  <div className="grid h-full place-items-center text-xs text-ink-faint">Loading image…</div>
                )}
              </div>
              <figcaption className="mt-2 text-xs text-ink-dim">
                <b className="font-semibold text-ink">{k === "pre" ? "Before" : "After"}</b> ·{" "}
                {k === "pre" ? (rec.imagery.before ?? "unknown") : (rec.imagery.after ?? "unknown")}
              </figcaption>
            </figure>
          ))}
        </section>
      </div>

      <div className="mt-12 grid gap-10 border-t border-line pt-10 lg:grid-cols-2">
        <section aria-labelledby="ev">
          <h2 id="ev" className="text-[28px] font-medium tracking-[-0.025em]">
            The evidence
          </h2>
          <ul className="mt-4 divide-y divide-line border-y border-line text-sm">
            {rec.evidence.map((e) => (
              <li key={e.channel} className="grid gap-0.5 py-3 sm:grid-cols-[13rem_1fr] sm:gap-4">
                <span className="font-medium">{e.channel}</span>
                <span className={e.used ? "" : "text-ink-dim"}>{e.says}</span>
              </li>
            ))}
          </ul>
          <p className="mt-4 text-sm text-ink-dim">{rec.validation}</p>
        </section>
        <section aria-labelledby="use">
          <h2 id="use" className="text-[28px] font-medium tracking-[-0.025em]">
            How to use this record
          </h2>
          <ol className="mt-4 grid gap-3 text-sm">
            {rec.uses.map((u, i) => (
              <li key={u} className="grid grid-cols-[2rem_1fr] gap-2">
                <span className="tnum font-mono text-[13px] leading-6 text-ink-faint">{String(i + 1).padStart(2, "0")}</span>
                <span>{u}</span>
              </li>
            ))}
          </ol>
        </section>
      </div>

      <p className="mt-12 border-t border-line pt-4 text-xs text-ink-faint">
        {rec.disclaimer} Assessed {day(rec.assessed_utc)} · run {rec.run_id} · this link works until{" "}
        {day(rec.expires_utc)}.
      </p>
    </PublicShell>
  );
}

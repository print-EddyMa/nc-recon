// The public check: "is my street OK?". Anyone can ask; the answer is banded
// for the buildings around a place, never one home's call. A home's own record
// comes only through a private link from a partner who verified the owner.
import { useEffect, useState, type FormEvent } from "react";
import { Spinner } from "../components/ui/kit";
import { loadOpsAreas, type OpsAreaSummary } from "../lib/ops";
import { lookup, type LookupAnswer } from "../lib/owner";
import { HeroTitle, PublicShell } from "./public/Shell";

const BANDS = ["few", "some", "many", "most"] as const;

function Meter({ label, band }: { label: string; band?: (typeof BANDS)[number] }) {
  const at = band ? BANDS.indexOf(band) : -1;
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span className="text-ink-dim">{label}</span>
        <span className="font-medium capitalize text-ink">{band ?? "n/a"}</span>
      </div>
      <div className="mt-1.5 grid grid-cols-4 gap-1" role="img" aria-label={`${label}: ${band ?? "unknown"}`}>
        {BANDS.map((b, i) => (
          <span
            key={b}
            className={`h-1.5 rounded-full ${i <= at ? "bg-ink" : "bg-surface-2"}`}
            style={i <= at ? { opacity: 0.45 + 0.18 * i } : undefined}
          />
        ))}
      </div>
      <div className="mt-1 grid grid-cols-4 text-[11px] text-ink-faint">
        {BANDS.map((b) => (
          <span key={b}>{b}</span>
        ))}
      </div>
    </div>
  );
}

export default function Check() {
  const [areas, setAreas] = useState<OpsAreaSummary[] | null>(null);
  const [area, setArea] = useState("");
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [ans, setAns] = useState<LookupAnswer | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [link, setLink] = useState("");
  const [linkErr, setLinkErr] = useState<string | null>(null);

  useEffect(() => {
    loadOpsAreas()
      .then((a) => {
        // held-out test areas never answer building-level questions
        const open = a.filter((x) => x.aoi.role !== "TEST");
        setAreas(open);
        if (open.length) setArea(open[0].id);
      })
      .catch((e: Error) => setErr(e.message));
  }, []);

  const ask = async (e: FormEvent) => {
    e.preventDefault();
    if (!area || q.trim().length < 5) return;
    setBusy(true);
    setErr(null);
    setAns(null);
    try {
      setAns(await lookup(area, q.trim()));
    } catch (ex) {
      setErr((ex as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const openLink = (e: FormEvent) => {
    e.preventDefault();
    const m = link.match(/#\/record\/([A-Za-z0-9_.-]+)/) ?? link.trim().match(/^([A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)$/);
    if (m) window.location.hash = `#/record/${m[1]}`;
    else setLinkErr("That does not look like a record link. Copy the whole link you were sent.");
  };

  const label = (a: OpsAreaSummary) => `${a.aoi.name ?? a.id.replace(/_/g, " ")}`;

  return (
    <PublicShell
      current="check"
      hero={
        <>
          <HeroTitle>Is my street OK?</HeroTitle>
          <p className="mt-5 max-w-[46ch] text-lg leading-relaxed text-ink-dim">
            Type an address to see how the buildings around it look in imagery taken after the disaster. To protect
            homes from looting, this never shows one home's damage.
          </p>
          <form
            onSubmit={ask}
            className="mt-8 grid max-w-3xl gap-3 sm:grid-cols-[minmax(0,13rem)_minmax(0,1fr)_auto]"
            aria-label="Check a street"
          >
            <label className="grid min-w-0 gap-1.5">
              <span className="text-xs text-ink-faint">Area</span>
              <select
                value={area}
                onChange={(e) => setArea(e.target.value)}
                className="field-lg"
                disabled={!areas?.length}
              >
                {!areas && <option>Loading…</option>}
                {areas?.length === 0 && <option>No areas assessed yet</option>}
                {areas?.map((a) => (
                  <option key={a.id} value={a.id}>
                    {label(a)}
                  </option>
                ))}
              </select>
            </label>
            <label className="grid min-w-0 gap-1.5">
              <span className="text-xs text-ink-faint">Street address</span>
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="123 Main Street"
                autoComplete="street-address"
                maxLength={120}
                className="field-lg"
              />
            </label>
            <div className="flex items-end">
              <button type="submit" className="btn-pill primary w-full sm:w-auto" disabled={busy || !area || q.trim().length < 5}>
                {busy ? <Spinner /> : null} Check
              </button>
            </div>
          </form>
          {err && (
            <p role="alert" className="mt-4 text-sm text-st-bad">
              {err}
            </p>
          )}
          {ans && (
            <section aria-live="polite" className="mt-8 max-w-3xl rounded-2xl border border-line bg-canvas p-5 sm:p-6">
              <p className="text-[clamp(1.5rem,2.6vw,2rem)] font-medium leading-tight tracking-[-0.025em] text-ink">{ans.text}</p>
              {ans.answer === "banded" && (
                <div className="mt-5 grid gap-5 sm:grid-cols-2">
                  <Meter label="Badly damaged or destroyed" band={ans.severe_band} />
                  <Meter label="Any visible damage" band={ans.any_damage_band} />
                </div>
              )}
              {ans.note && <p className="mt-4 text-sm text-ink-dim">{ans.note}</p>}
              {ans.answer === "banded" && (
                <p className="mt-3 text-xs text-ink-faint">
                  {ans.buildings_band} buildings within about {ans.radius_m} m · {ans.event} · assessed{" "}
                  {ans.assessed_utc?.slice(0, 10)}
                </p>
              )}
            </section>
          )}
        </>
      }
    >
      <div className="grid gap-10 md:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] md:gap-16">
        <section aria-labelledby="own">
          <h2 id="own" className="text-[28px] font-medium tracking-[-0.025em]">
            Your own home
          </h2>
          <p className="mt-3 max-w-[52ch] text-ink-dim">
            Legal aid groups and county offices can send owners and renters a private record for their home: the
            damage call, before and after images and the evidence, to use with FEMA or an insurer. If you were sent
            one, open it here.
          </p>
          <form onSubmit={openLink} className="mt-5 flex max-w-xl gap-2">
            <input
              value={link}
              onChange={(e) => {
                setLink(e.target.value);
                setLinkErr(null);
              }}
              placeholder="Paste your record link"
              aria-label="Record link"
              className="field-lg"
            />
            <button type="submit" className="btn-pill" disabled={!link.trim()}>
              Open
            </button>
          </form>
          {linkErr && (
            <p role="alert" className="mt-2 text-sm text-st-bad">
              {linkErr}
            </p>
          )}
        </section>
        <section aria-labelledby="how" className="border-t border-line pt-8 md:border-l md:border-t-0 md:pl-10 md:pt-0">
          <h2 id="how" className="text-[28px] font-medium tracking-[-0.025em]">
            How to read it
          </h2>
          <ul className="mt-3 grid gap-3 text-ink-dim">
            <li>
              <b className="font-semibold text-ink">From the air, not the ground.</b> Groma compares public imagery from
              before and after. Water inside a house does not show from above.
            </li>
            <li>
              <b className="font-semibold text-ink">Banded on purpose.</b> "Some" or "many" describes the buildings
              around a place, so nobody can use this to find an empty or damaged house.
            </li>
            <li>
              <b className="font-semibold text-ink">Preliminary.</b> People check the uncertain calls; the county's
              inspectors have the last word.
            </li>
          </ul>
          <a href="#/index" className="btn-pill mt-6">
            Damage counts for every area <span aria-hidden>→</span>
          </a>
        </section>
      </div>
    </PublicShell>
  );
}

/* Respond: what an area needs, laid out the way FEMA's Community Lifelines
 * toolkit structures a report (status, impact, actions), for the EOC, the
 * Guard and field teams. Every figure here is an estimate from open data;
 * the panel says so where it matters (grey means unknown, never green;
 * landing zones are reconnaissance candidates; worst case is a bound). */
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";
import {
  ago,
  buildResponse,
  downloadResponseKml,
  loadResponse,
  loadResponseStatus,
  type Lifeline,
  type LifelineColour,
  type ResponseProducts,
} from "../../lib/ops";
import { Button, Disclosure, Empty, Icon, Spinner, Tag } from "../ui/kit";

const n0 = (v: number | null | undefined) => Math.round(v ?? 0).toLocaleString();
const usd = (v: number) =>
  v >= 1e9 ? `$${(v / 1e9).toFixed(1)}B` : v >= 1e6 ? `$${(v / 1e6).toFixed(1)}M` : `$${Math.round(v / 1e3)}k`;

/** FEMA lifeline colours, each paired with the shape DHS S&T's lifeline tool
 * uses, so status survives colour blindness and a greyscale printer. */
const LL: Record<LifelineColour, { word: string; fill: string; text: string }> = {
  green: { word: "Stable", fill: "#5E9C42", text: "text-st-ok" },
  yellow: { word: "Strained", fill: "#FBBA16", text: "text-st-warn" },
  red: { word: "Disrupted", fill: "#C52038", text: "text-st-bad" },
  grey: { word: "Unknown", fill: "#919395", text: "text-ink-dim" },
};
export function StatusShape({ s, size = 14 }: { s: LifelineColour; size?: number }) {
  const f = LL[s].fill;
  return (
    <svg viewBox="0 0 16 16" width={size} height={size} aria-hidden className="shrink-0">
      {s === "green" && <rect x="2.5" y="2.5" width="11" height="11" rx="1.5" fill={f} />}
      {s === "yellow" && <path d="M8 2l6.5 11.5h-13z" fill={f} stroke="#5c4300" strokeWidth="0.8" strokeLinejoin="round" />}
      {s === "red" && <path d="M8 14L1.5 2.5h13z" fill={f} />}
      {s === "grey" && (
        <>
          <circle cx="8" cy="8" r="6" fill={f} />
          <path d="M6.4 6.4a1.7 1.7 0 113 1c-.6.4-1.4.8-1.4 1.6M8 11.3v.1" stroke="#fff" strokeWidth="1.4" strokeLinecap="round" fill="none" />
        </>
      )}
    </svg>
  );
}


export default function Respond({
  areaId,
  onFocus,
}: {
  areaId: string;
  /** centre the map here (USNG cell, cluster, landing zone) */
  onFocus: (ll: [number, number]) => void;
}) {
  const [r, setR] = useState<ResponseProducts | null | "none">(null);
  const [building, setBuilding] = useState(false);
  const load = useCallback(() => {
    loadResponse(areaId)
      .then(setR)
      .catch(() => setR("none"));
  }, [areaId]);
  useEffect(load, [load]);

  // a build runs on the server: watch its status until it lands
  useEffect(() => {
    if (!building) return;
    const t = window.setInterval(async () => {
      try {
        const s = await loadResponseStatus(areaId);
        if (s.status === "idle") {
          setBuilding(false);
          if (s.error) toast.error(`Response products: ${s.error}`);
          load();
        }
      } catch {
        /* keep waiting */
      }
    }, 3000);
    return () => window.clearInterval(t);
  }, [building, areaId, load]);

  const build = async () => {
    try {
      await buildResponse(areaId);
      setBuilding(true);
    } catch (e) {
      const m = (e as Error).message;
      if (m.includes("409")) setBuilding(true);
      else toast.error(/40[13]/.test(m) ? "Responder access is needed to build response products." : m);
    }
  };
  const kml = async () => {
    try {
      const b = await downloadResponseKml(areaId);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(b);
      a.download = `groma-${areaId}-response-plan.kml`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  if (r === null) return <div className="skel mt-4 h-48" />;
  if (r === "none")
    return (
      <div className="pt-4">
        <Empty
          icon="route"
          title={building ? "Building response products…" : "No response products for this area yet"}
          action={
            <Button variant="primary" size="sm" onClick={build} busy={building} disabled={building}>
              Build them now
            </Button>
          }
        >
          Lifelines, roads and who is cut off, landing-zone candidates, priority sectors, losses and debris, and
          supplies for the first 72 to 96 hours. Takes a minute or two.
        </Empty>
      </div>
    );

  const s = r.summary;
  const sc = r.access?.scenarios ?? s.cut_off;
  return (
    <div className="pb-4">
      <div className="flex flex-wrap items-center gap-2 pt-3">
        <Button size="sm" variant="primary" icon={<Icon name="download" className="h-3.5 w-3.5" />} onClick={kml}>
          Plan for TAK / Google Earth
        </Button>
        <Button size="sm" variant="ghost" icon={building ? <Spinner /> : <Icon name="refresh" className="h-3.5 w-3.5" />} onClick={build} disabled={building}>
          {building ? "Rebuilding…" : "Rebuild"}
        </Button>
        <span className="tnum ml-auto font-mono text-xs text-ink-faint" title={r.generated_utc}>
          built {ago(r.generated_utc)}
        </span>
      </div>

      {/* --- what was read --- */}
      {s.coverage != null && (
        <div className="mt-3 rounded border border-line p-2.5 text-xs">
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-ink">
              Read <b className="tnum font-mono">{n0(s.buildings_assessed)}</b> of{" "}
              <span className="tnum font-mono">{n0(s.buildings_assessed + (s.buildings_not_assessed ?? 0))}</span> buildings
            </span>
            <span className="tnum font-mono font-semibold text-ink">{Math.round((s.coverage ?? 0) * 100)}%</span>
          </div>
          <div className="bar-track mt-1.5 h-1">
            <div className="bar-fill bg-accent" style={{ width: `${Math.round((s.coverage ?? 0) * 100)}%` }} />
          </div>
          {s.buildings_not_assessed > 0 && (
            <p className="mt-1.5 text-ink-faint">
              {n0(s.buildings_not_assessed)} have no outline and were not read: unknown, never undamaged.
            </p>
          )}
          {(s.reading_notes ?? []).length > 0 && (
            <ul className="mt-1.5 list-disc space-y-0.5 pl-4 text-ink-dim">
              {s.reading_notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* --- status: lifelines --- */}
      <Block title="Lifelines" note="Estimated from open data. Grey is unknown, never fine.">
        <ul className="divide-y divide-line border-y border-line">
          {(r.resources?.lifelines ?? s.lifelines.map((l) => ({ ...l, facilities: 0, disrupted: 0, at_risk: 0, not_assessed: 0, first_look: [] }) as Lifeline)).map(
            (l) => (
              <LifelineRow key={l.lifeline} l={l} onFocus={onFocus} />
            ),
          )}
        </ul>
        {r.resources?.status_rule && <p className="mt-2 text-xs leading-snug text-ink-faint">{r.resources.status_rule}</p>}
      </Block>

      {/* --- water and power, same list style --- */}
      {(r.water || r.power) && (
        <Block title="Water and power" note="Public water systems over the area, private wells, live outages.">
          <ul className="divide-y divide-line border-y border-line">
            {(r.water?.systems ?? []).map((w) => (
              <WaterRow key={w.pwsid} w={w} />
            ))}
            {r.water?.private_wells && r.water.private_wells.residential_buildings > 0 && (
              <li className="py-1.5 text-[13px]">
                <div className="flex items-center gap-2">
                  <StatusShape s={r.water.private_wells.major_or_destroyed_expected > 0 ? "yellow" : "grey"} size={12} />
                  <span className="min-w-0 flex-1 truncate text-ink">Private wells</span>
                  <span className="tnum shrink-0 text-right font-mono text-xs text-ink-dim">
                    {n0(r.water.private_wells.residential_buildings)} homes · ~{n0(r.water.private_wells.people_est)} ppl
                  </span>
                </div>
                <p className="mt-0.5 pl-5 text-xs text-ink-faint">{r.water.private_wells.advice}</p>
              </li>
            )}
            {r.water && r.water.systems.length === 0 && !r.water.private_wells?.residential_buildings && (
              <li className="py-1.5 text-xs text-ink-faint">{r.water.note}</li>
            )}
            <li className="py-1.5 text-[13px]">
              <div className="flex items-center gap-2">
                <StatusShape s={r.power?.active && (r.power.counties ?? []).some((c) => c.meters_out > 0) ? "yellow" : "grey"} size={12} />
                <span className="min-w-0 flex-1 truncate text-ink">Power</span>
                <span className="text-xs font-semibold text-ink-dim">
                  {r.power?.active ? `${n0((r.power.counties ?? []).reduce((t, c) => t + c.meters_out, 0))} meters out` : r.power?.active === false ? "Not live" : "Unknown"}
                </span>
              </div>
              {r.power?.active &&
                (r.power.counties ?? [])
                  .filter((c) => c.meters_out > 0)
                  .map((c) => (
                    <div key={`${c.utility}-${c.county}`} className="tnum flex justify-between pl-5 font-mono text-xs text-ink-dim">
                      <span>
                        {c.county} · {c.utility}
                      </span>
                      <span>
                        {n0(c.meters_out)}
                        {c.estimated_restoration ? ` · back ${c.estimated_restoration}` : ""}
                      </span>
                    </div>
                  ))}
              {r.power?.note && <p className="mt-0.5 pl-5 text-xs text-ink-faint">{r.power.note}</p>}
            </li>
          </ul>
          {r.water?.note && r.water.systems.length > 0 && <p className="mt-2 text-xs text-ink-faint">{r.water.note}</p>}
        </Block>
      )}

      {/* --- impact: access --- */}
      {sc && (
        <Block title="Who is cut off" note="No road path out of a box 6 km around the area.">
          <div className="space-y-2.5">
            <Scenario label="Known road blocks" detail="Mapped landslides and reported closures" c={sc.known_blocks} max={s.buildings_assessed} />
            <Scenario
              label="Plus debris"
              detail="Roads beside destroyed buildings also blocked"
              c={sc.plus_debris}
              max={s.buildings_assessed}
              tag="realistic"
            />
            <Scenario
              label="Worst case"
              detail="Every bridge out: a planning bound, not a finding"
              c={sc.worst_case}
              max={s.buildings_assessed}
              tag="bound"
            />
          </div>
          {r.access && (
            <p className="mt-2.5 text-xs text-ink-faint">
              {n0(r.access.roads.blocked)} road segments blocked · {n0(r.access.roads.debris)} beside debris ·{" "}
              {n0(r.access.roads.bridge)} bridges unverified · OpenStreetMap roads
            </p>
          )}
          {r.access && r.access.isolated_clusters.length > 0 && (
            <Disclosure title="Cut-off clusters" meta={`${r.access.isolated_clusters.length}`}>
              <ul className="divide-y divide-line">
                {r.access.isolated_clusters.slice(0, 8).map((c) => (
                  <li key={c.cluster}>
                    <button className="flex w-full items-center gap-2 py-1.5 text-left text-xs hover:bg-surface-2" onClick={() => onFocus(c.center)}>
                      <Icon name="pin" className="h-3.5 w-3.5 text-ink-faint" />
                      <span className="tnum flex-1 font-mono text-ink">{c.usng}</span>
                      <span className="tnum font-mono text-ink-dim">
                        {n0(c.people_est)} ppl · {n0(c.buildings)} bldgs
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </Disclosure>
          )}
        </Block>
      )}

      {/* --- actions: sectors --- */}
      {r.sectors.length > 0 && (
        <Block title="Search priority by grid square" note="US National Grid 1 km squares, most people in severe damage first.">
          <table className="tnum w-full text-xs">
            <thead>
              <tr className="text-xs text-ink-faint">
                <th className="pb-1 text-left font-medium">#</th>
                <th className="pb-1 text-left font-medium">USNG 1 km</th>
                <th className="pb-1 text-right font-medium" title="People expected in Major or Destroyed buildings">
                  In severe
                </th>
                <th className="pb-1 text-right font-medium" title="Buildings expected at Major or Destroyed">
                  ≥ Major
                </th>
                <th className="pb-1 text-right font-medium">Cut off</th>
              </tr>
            </thead>
            <tbody>
              {r.sectors.slice(0, 8).map((x) => (
                <tr key={x.usng_1km} className="cursor-pointer border-t border-line hover:bg-surface-2" onClick={() => onFocus(x.center)}>
                  <td className="py-1.5 font-mono font-semibold text-ink">{x.priority}</td>
                  <td className="py-1.5 font-mono text-ink">{x.usng_1km}</td>
                  <td className="py-1.5 text-right font-mono font-semibold text-ink">{n0(x.people_in_severe_expected)}</td>
                  <td className="py-1.5 text-right font-mono text-ink-dim">{n0(x.major_or_destroyed_expected)}</td>
                  <td className="py-1.5 text-right font-mono text-ink-dim">{x.cut_off_people ? n0(x.cut_off_people) : "·"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Block>
      )}

      {/* --- actions: landing zones --- */}
      {r.landing && r.landing.candidates.length > 0 && (
        <Block title="Helicopter landing candidates" note={undefined}>
          <p className="mb-2 flex gap-2 rounded border border-st-warn/40 bg-st-warn/10 p-2 text-xs leading-snug text-ink">
            <Icon name="alert" className="mt-px h-3.5 w-3.5 text-st-warn" />
            <span>
              {r.landing.caveat ??
                "Map candidates for reconnaissance, not approved landing zones. Use the aviation unit's own standard."}
            </span>
          </p>
          <ul className="divide-y divide-line">
            {r.landing.candidates.slice(0, 6).map((z) => (
              <li key={z.usng}>
                <button className="flex w-full items-start gap-2.5 py-2 text-left hover:bg-surface-2" onClick={() => onFocus([z.lon, z.lat])}>
                  <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full border-2 border-accent font-mono text-[10px] font-bold text-accent">
                    H
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-1.5">
                      <span className="tnum font-mono text-xs font-semibold text-ink">{z.usng}</span>
                      {z.marginal && <Tag tone="warn">marginal</Tag>}
                    </span>
                    <span className="block text-xs text-ink-dim">
                      {z.clear_diameter_m} m clear · {z.slope_deg}° · {z.cover} · fits {z.fits.join(", ")}
                    </span>
                    {z.nearest_need && (
                      <span className="block text-xs text-ink-faint">
                        {z.nearest_need.distance_m} m from {z.nearest_need.label}
                      </span>
                    )}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </Block>
      )}

      {/* --- needs --- */}
      <Block title="Supplies, first 72 to 96 hours" note={r.needs.note}>
        <div className="grid grid-cols-3 gap-2">
          <Need v={n0(r.needs.water_litres_per_day)} unit="L water / day" />
          <Need v={n0(r.needs.meals_per_day)} unit="meals / day" />
          <Need v={n0(r.needs.shelter_ft2_standard)} unit="ft² shelter" />
        </div>
        <p className="mt-2 text-xs text-ink-dim">
          For {n0(r.needs.people_served)} people ({n0(r.needs.people_displaced_expected)} displaced, {n0(r.needs.people_cut_off)} cut off).{" "}
          {r.needs.distribution_points.map((d) => `${d.count} ${d.type} distribution point${d.count > 1 ? "s" : ""}`).join(", ")}.
        </p>
      </Block>

      {/* --- money --- */}
      {r.money && (
        <Block title="Losses and debris" note={undefined}>
          <div className="grid grid-cols-2 gap-2">
            <div className="rounded border border-line p-2.5">
              <div className="tnum font-mono text-lg font-semibold text-ink">
                {usd(r.money.building_loss_usd.low)}–{usd(r.money.building_loss_usd.high)}
              </div>
              <div className="text-xs text-ink-dim">building and contents loss</div>
            </div>
            <div className="rounded border border-line p-2.5">
              <div className="tnum font-mono text-lg font-semibold text-ink">
                {n0(r.money.debris_cy.low / 1000)}k–{n0(r.money.debris_cy.high / 1000)}k
              </div>
              <div className="text-xs text-ink-dim">cubic yards of debris</div>
            </div>
          </div>
          <Disclosure title="How these are estimated">
            <ul className="list-disc space-y-1 pl-4 text-xs leading-relaxed text-ink-dim">
              <li>{r.money.building_loss_usd.note}</li>
              <li>Damage ratios: {r.money.ratio_source}.</li>
              <li>Debris: {r.money.debris_cy.method}</li>
              <li>
                Public Assistance threshold:{" "}
                {r.money.public_assistance_threshold.county_threshold_usd
                  ? `${r.money.public_assistance_threshold.county ?? "county"} ${usd(r.money.public_assistance_threshold.county_threshold_usd)} (FY${r.money.public_assistance_threshold.fiscal_year})`
                  : r.money.public_assistance_threshold.note}
              </li>
            </ul>
          </Disclosure>
        </Block>
      )}

      {(r.notes.length > 0 || Object.keys(r.errors).length > 0) && (
        <Disclosure title="Notes" meta={r.notes.length + Object.keys(r.errors).length}>
          <ul className="list-disc space-y-1 pl-4 text-xs leading-relaxed text-ink-dim">
            {r.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
            {Object.entries(r.errors).map(([k, v]) => (
              <li key={k} className="text-st-bad">
                {k}: {v}
              </li>
            ))}
          </ul>
        </Disclosure>
      )}
      <p className="mt-3 text-xs leading-snug text-ink-faint">{r.disclaimer}</p>
    </div>
  );
}

function Block({ title, note, children }: { title: string; note?: string; children: ReactNode }) {
  return (
    <section className="border-b border-line py-4">
      <h2 className="text-sm">{title}</h2>
      {note && <p className="mb-2.5 mt-0.5 text-xs text-ink-faint">{note}</p>}
      {!note && <div className="mb-2.5" />}
      {children}
    </section>
  );
}

/** One lifeline as a list row: shape and name, the status word in its
 * colour, the count. Rows with detail open in place. */
function LifelineRow({ l, onFocus }: { l: Lifeline; onFocus: (ll: [number, number]) => void }) {
  const [open, setOpen] = useState(false);
  const count =
    l.facilities > 0
      ? `${l.disrupted ? `${l.disrupted} of ` : ""}${l.facilities}`
      : l.bridges_unverified
        ? `${l.bridges_unverified} bridges`
        : "none found";
  const more = l.first_look.length > 0 || !!l.roads_note || !!l.note;
  return (
    <li>
      <button
        className="flex w-full items-center gap-2 py-1.5 text-left text-[13px] hover:bg-surface-2 disabled:hover:bg-transparent"
        onClick={() => setOpen((v) => !v)}
        disabled={!more}
        aria-expanded={more ? open : undefined}
      >
        <StatusShape s={l.status} size={12} />
        <span className="min-w-0 flex-1 truncate text-ink">{l.label}</span>
        <span className={`w-20 shrink-0 text-xs font-semibold ${LL[l.status].text}`}>{LL[l.status].word}</span>
        <span className="tnum w-20 shrink-0 text-right font-mono text-xs text-ink-dim">{count}</span>
        <Icon name="chevron" className={`h-3 w-3 shrink-0 text-ink-faint transition-transform ${more ? "" : "invisible"} ${open ? "rotate-90" : ""}`} />
      </button>
      {open && (
        <div className="space-y-1 pb-2 pl-5 text-xs">
          {l.roads_note && <p className="text-ink-dim">{l.roads_note}</p>}
          {l.bridges_unverified ? <p className="text-ink-dim">{l.bridges_unverified} bridges not verified.</p> : null}
          {l.note && <p className="text-ink-dim">{l.note}</p>}
          {l.first_look.map((f, i) => (
            <button
              key={i}
              className="flex w-full items-center gap-1.5 rounded px-1 py-0.5 text-left hover:bg-surface-2"
              onClick={() => onFocus([f.lon, f.lat])}
            >
              <Icon name="pin" className="h-3 w-3 text-ink-faint" />
              <span className="flex-1 text-ink">{f.name}</span>
              <span className="text-ink-faint">{f.reasons.join("; ")}</span>
            </button>
          ))}
        </div>
      )}
    </li>
  );
}

type WaterSystem = NonNullable<ResponseProducts["water"]>["systems"][number];
function WaterRow({ w }: { w: WaterSystem }) {
  const [open, setOpen] = useState(false);
  const risk = w.status === "at_risk";
  return (
    <li>
      <button className="flex w-full items-center gap-2 py-1.5 text-left text-[13px] hover:bg-surface-2" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        <StatusShape s={risk ? "yellow" : "green"} size={12} />
        <span className="min-w-0 flex-1 truncate text-ink" title={w.name}>
          {w.name}
        </span>
        <span className={`w-20 shrink-0 text-xs font-semibold ${risk ? "text-st-warn" : "text-st-ok"}`}>{risk ? "At risk" : "No sign"}</span>
        <span className="tnum w-20 shrink-0 text-right font-mono text-xs text-ink-dim">
          {w.population_served != null ? `${n0(w.population_served)} ppl` : "n/a"}
        </span>
        <Icon name="chevron" className={`h-3 w-3 shrink-0 text-ink-faint transition-transform ${open ? "rotate-90" : ""}`} />
      </button>
      {open && (
        <div className="space-y-0.5 pb-2 pl-5 text-xs text-ink-dim">
          <p>
            {n0(w.buildings_assessed_inside)} buildings read inside · ~{n0(w.major_or_destroyed_expected)} at Major or Destroyed ·{" "}
            <span className="font-mono">{w.pwsid}</span>
          </p>
          {w.reasons.map((x) => (
            <p key={x}>{x}</p>
          ))}
          {w.flagged_facilities.map((f, i) => (
            <p key={i} className="text-ink">
              {f.name ?? f.kind.replace(/_/g, " ")}: {f.status.replace(/_/g, " ")}
            </p>
          ))}
        </div>
      )}
    </li>
  );
}

function Scenario({
  label,
  detail,
  c,
  max,
  tag,
}: {
  label: string;
  detail: string;
  c: { isolated_buildings: number; isolated_people_est: number; isolated_major_or_destroyed: number };
  max: number;
  tag?: "realistic" | "bound";
}) {
  const w = Math.min(100, (c.isolated_buildings / Math.max(1, max)) * 100);
  return (
    <div>
      <div className="flex items-baseline gap-2">
        <span className="text-xs font-semibold text-ink">{label}</span>
        {tag && <Tag tone={tag === "realistic" ? "accent" : "neutral"}>{tag}</Tag>}
        <span className="tnum ml-auto font-mono text-xs text-ink">
          <b>{n0(c.isolated_people_est)}</b> <span className="text-ink-faint">people · {n0(c.isolated_buildings)} bldgs</span>
        </span>
      </div>
      <div className="bar-track mt-1 h-1.5">
        <div className={`bar-fill ${tag === "bound" ? "bg-ink-faint" : "bg-st-bad"}`} style={{ width: `${w}%` }} />
      </div>
      <div className="mt-0.5 text-xs text-ink-faint">{detail}</div>
    </div>
  );
}

function Need({ v, unit }: { v: string; unit: string }) {
  return (
    <div className="rounded border border-line p-2">
      <div className="tnum font-mono text-base font-semibold text-ink">{v}</div>
      <div className="text-xs leading-tight text-ink-dim">{unit}</div>
    </div>
  );
}

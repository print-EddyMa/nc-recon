/**
 * What NC Recon is: a North Carolina disaster instrument with two halves — live
 * risk monitoring (before / during) and on-demand imagery-based damage
 * assessment (after). No sample data is bundled; every number in the app comes
 * from a live feed or a pipeline run. This screen is the reference document:
 * what each feed is, where it comes from, and how the damage model decides.
 */
interface Props {
  onEnter: () => void;
}

interface Source {
  field: string;
  source: string;
  detail: string;
}

const RISK_SOURCES: Source[] = [
  {
    field: "River flooding",
    source: "NOAA NWPS",
    detail:
      "National Water Model flood-category forecasts for every NC forecast gauge, plus observed stage.",
  },
  {
    field: "Streamflow",
    source: "USGS NWIS",
    detail:
      "Live discharge and gage height at NC streamgages, checked against the period-of-record percentiles.",
  },
  {
    field: "Official alerts",
    source: "NWS",
    detail: "Active watches, warnings, and advisories for North Carolina, rolled up to county.",
  },
  {
    field: "Fire weather",
    source: "NC ECONet / RAWS",
    detail:
      "Temperature, wind, rainfall, and RAWS fuel-moisture from the NC State Climate Office CLOUDS API (free key).",
  },
  {
    field: "Active storms",
    source: "NHC",
    detail: "Forecast cone, track line, and watch/warning zones — shown only while an Atlantic storm is active.",
  },
  {
    field: "Ground truth",
    source: "NCDOT DriveNC",
    detail: "Traffic-camera locations and road closures near the current risk.",
  },
  {
    field: "Disaster history",
    source: "OpenFEMA",
    detail: "Federally declared disasters in North Carolina since 1990, for context on what has happened here before.",
  },
];

const DAMAGE_PARTS: Source[] = [
  {
    field: "Imagery",
    source: "Maxar Open Data",
    detail:
      "Pre- and post-event captures for any catalogue event that covers North Carolina, fetched only when you assess an area.",
  },
  {
    field: "Footprints",
    source: "NC OneMap → OSM",
    detail: "Authoritative NC statewide building footprints where available; OpenStreetMap elsewhere.",
  },
  {
    field: "Damage model",
    source: "xView2 CMU baseline",
    detail:
      "A ResNet-50 classifier trained on xBD: no damage → minor → major → destroyed, fused with an independent change-detection pass.",
  },
  {
    field: "Confidence",
    source: "2 models + NC priors",
    detail:
      "Each building’s tier is fused from the model margin, cross-model agreement, and NC context — flood stage, FEMA declaration, terrain. Disagreements go to review.",
  },
];

export default function About({ onEnter }: Props) {
  return (
    <main id="main" className="h-full overflow-y-auto">
      <div className="mx-auto w-full max-w-4xl px-6 py-12 md:px-10 md:py-16">
        <p className="eyebrow mb-4">About NC Recon · North Carolina</p>

        <h1 className="max-w-[22ch] font-display text-display font-semibold text-ink">
          One instrument for the disaster, before and after.
        </h1>

        <p className="measure mt-5 text-[0.95rem] leading-relaxed text-ink-dim">
          NC Recon watches North Carolina for the conditions that precede a disaster — river-flood
          forecasts, fire weather, official warnings, storm tracks, road closures. Once post-event
          satellite imagery exists, it rates the damage to every building on a four-level scale and
          routes the uncertain calls to a human review queue.{" "}
          <button onClick={onEnter} className="pressable text-accent underline underline-offset-2 hover:text-ink">
            Open the live map
          </button>
          .
        </p>

        {/* -------- before / during -------- */}
        <section className="mt-14">
          <h2 className="section-title mb-1 text-[0.95rem]">Before and during — the risk monitor</h2>
          <p className="measure mb-5 text-xs text-ink-faint">
            Seven live feeds, keyless except fire weather. Each falls back to a committed snapshot
            when its upstream is unreachable, so the map is never blank.
          </p>
          <SourceTable rows={RISK_SOURCES} />
        </section>

        {/* -------- after -------- */}
        <section className="mt-14">
          <h2 className="section-title mb-1 text-[0.95rem]">After — damage assessment</h2>
          <p className="measure mb-5 text-xs text-ink-faint">
            Runs on demand against one North Carolina area with a clean pre/post imagery pair.
          </p>
          <SourceTable rows={DAMAGE_PARTS} />
        </section>

        {/* -------- how the model decides -------- */}
        <section className="mt-14">
          <h2 className="section-title mb-4 text-[0.95rem]">How a building gets its damage class</h2>
          <ModelDiagram />
          <p className="measure mt-5 text-xs leading-relaxed text-ink-faint">
            Two models see every building. The CNN classifier reads the post-event chip directly; an
            independent change-detection pass compares pre and post. Where they land within one level
            of each other, the building is reported at high confidence. Where they differ by two or
            more levels — or the footprint is too small to read — it goes to the review queue instead
            of being reported as certain. NC context priors only move borderline tiers; they never
            change the damage class.
          </p>
        </section>

        <hr className="rule mt-14" />
        <p className="mt-5 text-2xs leading-relaxed text-ink-faint">
          No assessment data ships with the app. Areas appear on the damage map only after the
          pipeline has run for them, locally or against a hosted service. Damage classes are model
          output, not a field survey.
        </p>
      </div>
    </main>
  );
}

function SourceTable({ rows }: { rows: Source[] }) {
  return (
    <dl className="border-t border-line">
      {rows.map((r) => (
        <div
          key={r.field}
          className="grid grid-cols-[8.5rem_1fr] gap-x-5 gap-y-1 border-b border-line py-3.5 sm:grid-cols-[9rem_9rem_1fr]"
        >
          <dt className="text-sm font-medium text-ink">{r.field}</dt>
          <dd className="tnum order-3 text-xs leading-relaxed text-ink-dim sm:order-2 sm:col-span-1 sm:text-[0.8125rem]">
            <span className="font-mono text-2xs uppercase tracking-wide text-ink-faint sm:hidden">
              {r.source} —{" "}
            </span>
            <span className="hidden font-medium text-ink-dim sm:inline">{r.source}</span>
          </dd>
          <dd className="order-2 col-span-2 text-xs leading-relaxed text-ink-dim sm:order-3 sm:col-span-1 sm:pl-0">
            {r.detail}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** The fusion pipeline, drawn as the real mechanism — imagery in, a damage
 * class + confidence tier out, with the review branch shown explicitly. */
function ModelDiagram() {
  return (
    <figure className="card overflow-x-auto px-5 py-5">
      <svg
        viewBox="0 0 720 190"
        className="h-auto w-full min-w-[560px] text-ink-dim"
        role="img"
        aria-label="Pipeline: pre and post imagery and building footprints feed a CNN classifier and a change-detection pass; the two are fused into a damage class with a confidence tier; buildings where the passes disagree go to the review queue."
      >
        {/* inputs */}
        <Node x={8} y={20} w={128} h={34} label="Pre / post imagery" />
        <Node x={8} y={78} w={128} h={34} label="Building footprints" />
        {/* models */}
        <Node x={210} y={12} w={150} h={34} label="CNN classifier" accent />
        <Node x={210} y={86} w={150} h={34} label="Change detection" accent />
        {/* fusion */}
        <Node x={430} y={49} w={120} h={40} label="Fusion" strong />
        {/* outputs */}
        <Node x={596} y={12} w={116} h={34} label="Damage class" />
        <Node x={596} y={72} w={116} h={34} label="High confidence" />
        <Node x={596} y={128} w={116} h={44} label="Review queue" warn />

        <g fill="none" stroke="currentColor" strokeWidth="1.25" opacity="0.55">
          <path d="M136 37 H196 M196 37 V29 H204" />
          <path d="M136 95 H196 M196 95 V103 H204" />
          <path d="M136 37 H172 M172 37 V103 H204" opacity="0" />
          <path d="M360 29 H396 M396 29 V60 H424" />
          <path d="M360 103 H396 M396 103 V78 H424" />
          <path d="M550 60 H574 M574 60 V29 H590" />
          <path d="M550 69 H582 M582 69 V89 H590" />
          <path d="M550 78 H568 M568 78 V150 H590" />
        </g>
      </svg>
    </figure>
  );
}

function Node({
  x,
  y,
  w,
  h,
  label,
  accent,
  strong,
  warn,
}: {
  x: number;
  y: number;
  w: number;
  h: number;
  label: string;
  accent?: boolean;
  strong?: boolean;
  warn?: boolean;
}) {
  const stroke = warn
    ? "rgb(var(--meter))"
    : accent || strong
      ? "rgb(var(--accent))"
      : "rgb(var(--line-strong))";
  return (
    <g>
      <rect
        x={x}
        y={y}
        width={w}
        height={h}
        rx={7}
        fill={strong ? "rgb(var(--accent-soft))" : "rgb(var(--surface-2))"}
        stroke={stroke}
        strokeWidth={strong ? 1.5 : 1}
      />
      <text
        x={x + w / 2}
        y={y + h / 2}
        textAnchor="middle"
        dominantBaseline="central"
        fontSize="12"
        fontFamily="Geist, ui-sans-serif, system-ui, sans-serif"
        fontWeight={strong ? 600 : 500}
        fill="rgb(var(--ink))"
      >
        {label}
      </text>
    </g>
  );
}

/**
 * What NCResQ is: a North Carolina disaster application with two halves,  * live risk monitoring (before / during) and on-demand imagery-based damage
 * assessment (after). No sample data is bundled; every number here comes from a
 * live feed or a pipeline run.
 */
interface Props {
  onEnter: () => void;
}

export default function About({ onEnter }: Props) {
  return (
    <main id="main" className="relative min-h-full overflow-y-auto">
      <Contours />

      <div className="relative mx-auto w-full max-w-5xl px-6 py-12 md:py-16">
        <p className="cap mb-7 flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-accent" />
          About NCResQ · North Carolina
        </p>

        <h1 className="font-display text-[1.9rem] leading-[1.15] text-ink md:text-[2.4rem]">
          A disaster picture for North Carolina, before and after
        </h1>

        <p className="mt-5 max-w-[54ch] text-sm leading-relaxed text-ink-dim">
          NCResQ watches North Carolina for the conditions that precede a
          disaster, river-flood forecasts, fire weather, official warnings, road
          closures, and, once post-event satellite imagery exists, assesses the
          damage building by building on a four-level scale, routing the uncertain
          calls to a human review queue.
        </p>

        <div className="mt-8">
          <button
            onClick={onEnter}
            className="pressable group inline-flex items-center gap-2.5 rounded-md bg-accent py-2.5 pl-5 pr-2.5 text-sm font-semibold text-accent-ink"
          >
            Open the NC risk monitor
            <span className="grid h-7 w-7 place-items-center rounded bg-accent-ink/12 transition-transform duration-200 ease-out group-hover:translate-x-0.5">
              <svg width="13" height="13" viewBox="0 0 16 16" fill="none" aria-hidden>
                <path
                  d="M3 8h10M9 4l4 4-4 4"
                  stroke="currentColor"
                  strokeWidth="1.7"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </span>
          </button>
        </div>

        <section className="mt-14 border-t border-line pt-8">
          <div className="cap mb-4">The risk half, live NC feeds</div>
          <dl className="grid grid-cols-2 gap-x-10 gap-y-6 md:grid-cols-3">
            <Item k="River flooding" v="NOAA NWPS" d="National Water Model flood-category forecasts for every NC forecast gauge, plus observed stage." />
            <Item k="Streamflow" v="USGS NWIS" d="Live discharge and gage height at NC streamgages, flagged against the period-of-record percentiles." />
            <Item k="Official alerts" v="NWS" d="Active watches, warnings and advisories for North Carolina, rolled up to county." />
            <Item k="Fire weather" v="ECONet / RAWS" d="Temperature, wind, rainfall and RAWS fuel-moisture from the NC State Climate Office CLOUDS API (free key)." />
            <Item k="Active storms" v="NHC" d="Forecast cone, track line and watch/warning zones, shown only while an Atlantic storm is active." />
            <Item k="Ground truth" v="NCDOT DriveNC" d="Traffic-camera locations and road closures near whatever the current risk is." />
            <Item k="History" v="OpenFEMA" d="Federally-declared disasters in North Carolina, for context on what has happened here before." />
          </dl>
        </section>

        <section className="mt-12 border-t border-line pt-8">
          <div className="cap mb-4">The damage half, on-demand assessment</div>
          <dl className="grid grid-cols-2 gap-x-10 gap-y-6 md:grid-cols-4">
            <Item k="Imagery" v="Maxar Open Data" d="Pre/post captures for any event in the Maxar Open Data catalogue that covers North Carolina, fetched only when you assess an area." />
            <Item k="Footprints" v="NC OneMap + OSM" d="Authoritative NC statewide building footprints where available, OpenStreetMap elsewhere." />
            <Item k="Damage model" v="ResNet-50 · xBD" d="The xView2 CMU baseline classifier (no damage → minor → major → destroyed), fused with an independent change-detection pass." />
            <Item k="Confidence" v="2 models + priors" d="Each building's tier is fused from the model margin, cross-model agreement, and NC context (flood stage, FEMA declaration, terrain). Disagreements go to review." />
          </dl>
          <p className="mt-6 max-w-[74ch] text-xs leading-relaxed text-ink-faint">
            No assessment data is bundled with the app. Areas appear on the damage
            map only after the pipeline has run for them, locally, or against a
            hosted assessment service. Damage classes are model output, not a field
            survey; the review queue exists because a person stays on the ambiguous
            calls.
          </p>
        </section>
      </div>
    </main>
  );
}

function Item({ k, v, d }: { k: string; v: string; d: string }) {
  return (
    <div className="border-l border-line pl-3.5">
      <dt className="cap mb-1">{k}</dt>
      <dd className="m-0">
        <span className="tnum block text-base font-semibold text-ink">{v}</span>
        <span className="mt-1 block text-2xs leading-relaxed text-ink-faint">{d}</span>
      </dd>
    </div>
  );
}

function Contours() {
  // a quiet topographic backdrop, no glow, low contrast
  return (
    <svg
      aria-hidden
      className="pointer-events-none absolute inset-0 h-full w-full opacity-[0.06]"
      preserveAspectRatio="xMidYMid slice"
      viewBox="0 0 800 600"
    >
      {Array.from({ length: 16 }).map((_, i) => (
        <path
          key={i}
          d={`M-60 ${52 + i * 38} C 150 ${-4 + i * 38 + (i % 3) * 14}, 300 ${140 + i * 38}, 520 ${44 + i * 38} S 880 ${8 + i * 38}, 920 ${76 + i * 38}`}
          fill="none"
          stroke="currentColor"
          strokeWidth={i % 4 === 0 ? 1.2 : 0.6}
        />
      ))}
    </svg>
  );
}

import { useMemo } from "react";
import { summarize } from "../lib/data";
import type { AreaConfig, DamageCollection, EventConfig, HazardType } from "../lib/types";
import type { CatalogEvent } from "../lib/catalog";
import type { IngestState } from "../lib/useAssess";
import { DAMAGE } from "../lib/damage";
import BeforeAfterImage from "../components/BeforeAfterImage";
import EventPicker from "../components/EventPicker";

interface Props {
  event: EventConfig;
  area: AreaConfig;
  fc: DamageCollection | null;
  events: EventConfig[];
  catalog: CatalogEvent[];
  online: boolean | null;
  jobs: Record<string, IngestState>;
  onPickEvent: (id: string) => void;
  onIngest: (ev: { id: string; name: string; center: [number, number] | null }) => void;
  onEnter: () => void;
}

const HAZARD_BLURB: Partial<Record<HazardType, string>> = {
  hurricane:
    "Hurricane-force wind and river flooding tore through the affected towns and cut road access for days.",
  cyclone:
    "The cyclone's wind and storm surge cut across the coast, isolating communities before responders could reach them.",
  wildfire:
    "Wind-driven fire moved block by block through the neighbourhood, leaving a checkerboard of intact and destroyed structures.",
  flood:
    "Floodwater rose through streets and ground floors, and the damage is only legible once the water drops.",
  earthquake:
    "The shock collapsed some structures outright and left others standing but unsafe — a distinction only close inspection reveals.",
};

export default function Landing({
  event,
  area,
  fc,
  events,
  catalog,
  online,
  jobs,
  onPickEvent,
  onIngest,
  onEnter,
}: Props) {
  const stats = useMemo(() => (fc ? summarize(fc) : null), [fc]);
  const blurb =
    HAZARD_BLURB[event.hazard] ??
    "The event's footprint is only legible by comparing imagery from before and after.";

  return (
    <main id="main" className="relative min-h-full overflow-y-auto">
      <Contours />

      <div className="relative mx-auto w-full max-w-6xl px-6 py-12 md:py-16">
        <div className="mb-7 flex items-center justify-between gap-3">
          <p className="cap flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-accent" />
            Rapid damage assessment · {event.name}
            {event.event_date ? ` · ${event.event_date}` : ""}
          </p>
          <EventPicker
            events={events}
            catalog={catalog}
            value={event.id}
            online={online}
            jobs={jobs}
            onChange={onPickEvent}
            onIngest={onIngest}
          />
        </div>

        <div className="grid items-start gap-12 md:grid-cols-[1.05fr_0.95fr]">
          <div>
            <h1 className="font-display text-[2.5rem] leading-[1.04] text-ink md:text-[3.5rem]">
              Every building, triaged from orbit.
            </h1>

            <p className="mt-6 max-w-[46ch] text-[0.95rem] leading-relaxed text-ink-dim">
              {blurb} TerraTriage pairs pre- and post-event satellite imagery, finds
              every structure, rates its damage on a four-level scale, and routes the
              uncertain calls to a human review queue — turning two photographs into a
              map a response coordinator can act on.
            </p>

            <div className="mt-8 flex flex-wrap items-center gap-4">
              <button
                onClick={onEnter}
                className="pressable group inline-flex items-center gap-2.5 rounded-full bg-accent py-2.5 pl-5 pr-2.5 text-sm font-semibold text-[#05171a]"
              >
                Open the live monitor
                <span className="grid h-7 w-7 place-items-center rounded-full bg-[#05171a]/12 transition-transform duration-200 ease-out group-hover:translate-x-0.5">
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
              <span className="tnum text-xs text-ink-faint">
                {area.name}
                {area.subtitle ? `, ${area.subtitle}` : ""}
              </span>
            </div>
          </div>

          <BeforeAfterImage
            area={area}
            eventName={event.name}
            preDate={fc?.properties.pre_image.date}
            postDate={fc?.properties.post_image.date}
          />
        </div>

        <dl className="stagger mt-14 grid grid-cols-2 gap-x-10 gap-y-6 sm:grid-cols-4">
          <HeroStat label="Buildings assessed" value={stats ? stats.total.toLocaleString() : "—"} />
          <HeroStat
            label="Major or destroyed"
            value={stats ? `${stats.severePct.toFixed(0)}%` : "—"}
            accent={DAMAGE[2].hex}
          />
          <HeroStat
            label="Flagged for review"
            value={fc?.properties.review ? fc.properties.review.total_review.toLocaleString() : "—"}
          />
          <HeroStat label="Damage levels" value="4" />
        </dl>

        <section className="mt-14 border-t border-line pt-8">
          <div className="cap mb-4">What it's built on</div>
          <dl className="grid grid-cols-2 gap-x-10 gap-y-6 md:grid-cols-4">
            <Provenance
              k="Training data"
              v="~850,000 buildings"
              d="xBD / xView2 — labelled pre- and post-event building polygons across ~45,000 km² of 0.3 m satellite imagery, 19 disasters, 6 hazard types."
            />
            <Provenance
              k="Damage model"
              v="ResNet-50 · xBD"
              d="The xView2 CMU baseline classifier, trained on the xBD Joint Damage Scale (no damage → minor → major → destroyed)."
            />
            <Provenance
              k="Confidence"
              v="2 models + OSM"
              d="Each building's tier is fused from the CNN's softmax margin, an independent change-detection pass, and an OpenStreetMap footprint check. Disagreements go to human review."
            />
            <Provenance
              k="Coverage"
              v="55 events, live"
              d="Any disaster in the Maxar Open Data catalogue, ingested on demand. A live USGS + GDACS monitor tracks hazards worldwide before imagery exists."
            />
          </dl>
          <p className="mt-6 max-w-[74ch] text-xs leading-relaxed text-ink-faint">
            Imagery: Maxar Open Data. Footprints: OpenStreetMap. Model & training set:
            xView2 / xBD (Gupta et al., 2019). Multi-source fusion + human-in-the-loop
            review follow the pattern the Humanitarian OpenStreetMap Team uses in
            production. Damage classes are the model's output, not a field survey —
            the review queue exists because AI-assisted assessment keeps a person on
            the ambiguous calls.
          </p>
        </section>
      </div>
    </main>
  );
}

function Provenance({ k, v, d }: { k: string; v: string; d: string }) {
  return (
    <div className="border-l border-line pl-3.5">
      <dt className="cap mb-1">{k}</dt>
      <dd className="m-0">
        <span className="tnum block text-lg font-semibold text-ink">{v}</span>
        <span className="mt-1 block text-2xs leading-relaxed text-ink-faint">{d}</span>
      </dd>
    </div>
  );
}

function HeroStat({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="border-l border-line pl-3.5">
      <dt className="cap mb-1.5">{label}</dt>
      <dd className="tnum m-0 text-2xl font-semibold" style={accent ? { color: accent } : undefined}>
        {value}
      </dd>
    </div>
  );
}

function Contours() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      {/* ambient depth — a single soft light from upper-right, no hard section edges */}
      <div
        className="absolute -right-1/4 -top-1/3 h-[80vh] w-[80vh] rounded-full opacity-[0.5]"
        style={{
          background:
            "radial-gradient(circle, rgba(76,181,194,0.10), rgba(76,181,194,0) 62%)",
        }}
      />
      {/* topographic contour lines — a quiet cartographic backdrop */}
      <svg
        className="absolute inset-0 h-full w-full opacity-[0.10]"
        preserveAspectRatio="xMidYMid slice"
        viewBox="0 0 800 600"
      >
        {Array.from({ length: 18 }).map((_, i) => (
          <path
            key={i}
            d={`M-60 ${52 + i * 34} C 150 ${-4 + i * 34 + (i % 3) * 14}, 300 ${140 + i * 34}, 520 ${44 + i * 34} S 880 ${8 + i * 34}, 920 ${76 + i * 34}`}
            fill="none"
            stroke="#4cb5c2"
            strokeWidth={i % 4 === 0 ? 1.5 : 0.7}
          />
        ))}
      </svg>
    </div>
  );
}

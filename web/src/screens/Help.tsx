/* Hallmark · screen: Help · macrostructure: Long Document with a sticky
 * contents rail. Plain, printable, one section per job; every map mark and
 * every key on the other screens is explained here. */
import { DISCLAIMER, FEMA, FEMA_LABEL } from "../lib/ops";
import { StatusShape } from "../components/ops/Respond";
import { Kbd, Swatch } from "../components/ui/kit";
import type { ReactNode } from "react";

const SECTIONS: [string, string][] = [
  ["what", "What it does"],
  ["run", "Run an assessment"],
  ["map", "Reading the map"],
  ["numbers", "Numbers you can report"],
  ["respond", "Respond: lifelines, access, landing zones"],
  ["checks", "Checks against field records"],
  ["review", "Review and Verify"],
  ["limits", "What it cannot see"],
  ["keys", "Keyboard"],
  ["access", "Access and privacy"],
  ["sources", "Data sources"],
];

export default function Help() {
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto grid max-w-5xl gap-10 px-5 py-8 md:grid-cols-[200px_minmax(0,1fr)]">
        <nav aria-label="Contents" className="hidden md:block print:hidden">
          <div className="sticky top-6">
            <div className="label mb-2">Contents</div>
            <ol className="space-y-1 text-[13px]">
              {SECTIONS.map(([id, t]) => (
                <li key={id}>
                  <a href={`#help-${id}`} className="text-ink-dim hover:text-ink" onClick={(e) => jump(e, id)}>
                    {t}
                  </a>
                </li>
              ))}
            </ol>
          </div>
        </nav>

        <article className="max-w-[68ch] text-[15px] leading-relaxed text-ink">
          <h1 className="title-display text-[28px] tracking-[0.04em]">Using Groma</h1>
          <p className="mt-3 flex gap-2 rounded border border-st-warn/40 bg-st-warn/10 px-3 py-2 text-sm font-medium">
            {DISCLAIMER}
          </p>

          <Section id="what" title="What it does">
            <p>
              For any place in the United States and a declared (or provisional) event, Groma pulls before- and
              after-event imagery, finds every structure in the area, and estimates each one's FEMA damage level
              with a probability. Uncertain and severe calls go to people. It also estimates who is displaced and
              cut off, which lifelines are strained, where a helicopter could land, what it will cost, and what
              supplies the first days need; and it exports everything for GIS, TAK and field teams.
            </p>
          </Section>

          <Section id="run" title="Run an assessment">
            <ol className="list-decimal space-y-1.5 pl-5">
              <li>
                <b>Assess → New assessment</b> (or <Kbd>N</Kbd>). Pick the event. Not listed? Type its FEMA
                disaster number: Groma reads the declaration, picks the hazards and finds matching imagery, and
                shows the draft before anything is registered. No declaration yet? Enter it by hand as a
                provisional event.
              </li>
              <li>
                Name the place and click <b>Pick the centre on the map</b>, or type coordinates. The green square
                is the ground the assessment will cover; outlined boxes are areas already assessed.
              </li>
              <li>Choose the size. Small (0.8 km across) takes about 2 minutes; large (2.4 km) 10 or more.</li>
              <li>
                <b>Check imagery</b> names the before image (state orthos where they exist, otherwise USDA NAIP,
                always flown before the incident) and the after image (state post-event orthos, NOAA emergency
                aerials or Maxar). If nothing covers the point, it cannot be assessed yet.
              </li>
              <li>
                <b>Run assessment</b>. One runs at a time; the rest queue. <b>In progress</b> shows each step for
                every analyst on the server, and the area opens when it is done.
              </li>
            </ol>
            <p className="mt-2">
              If the server restarts mid-run, the job shows as Interrupted and nothing partial is kept. <b>Run
              again</b> (the ⋯ menu of an operational area) reassesses from the imagery it already has; labels are
              kept. Before and after windows come from the incident date and are enforced: an image taken before
              the incident is never used as the "after".
            </p>
          </Section>

          <Section id="map" title="Reading the map">
            <ul className="space-y-1.5">
              {FEMA.map((c) => (
                <li key={c} className="flex items-center gap-2">
                  <Swatch c={c} className="h-3.5 w-3.5" /> <b>{FEMA_LABEL[c]}</b>
                </li>
              ))}
              <li className="flex items-center gap-2">
                <Swatch c="none" className="h-3.5 w-3.5" />
                <span>
                  <b>Not assessed</b>: in the inventory but with no outline, so imagery was never read. Counted, never
                  dropped.
                </span>
              </li>
              <li className="flex items-center gap-2">
                <span className="h-3.5 w-3.5 shrink-0 rounded-[2px] border-2 border-review" />
                <span>
                  <b>Blue outline</b>: needs a person. The structure panel says why.
                </span>
              </li>
            </ul>
            <p className="mt-2">
              Colour is the most likely level; fill strength is confidence, so faint fills are uncertain. Read the
              probability bar on the structure, not the colour alone. The legend is also a filter: click a level to
              hide it, or show only what needs review.
            </p>
            <p className="mt-2">
              <b>After / Before / Swipe / Map</b> puts the assessment's own images under the structures, with their
              capture dates. <b>Swipe</b> draws a divider you drag across the same ground; holding <Kbd>B</Kbd>{" "}
              flips to the before image for as long as the key is down. A date shown as a range means the source does
              not publish the exact day.
            </p>
            <p className="mt-2">
              <b>2D / 3D</b>: 3D stands each building up at its inventory height (stories × 3 m, USACE National
              Structure Inventory). About half the buildings have no recorded height: they are drawn flat with a dashed
              outline, never guessed. <b>Terrain</b> adds the ground's relief. Drag with the right mouse button (or
              Ctrl) to tilt and turn.
            </p>
          </Section>

          <Section id="numbers" title="Numbers you can report">
            <ul className="list-disc space-y-1.5 pl-5">
              <li>
                Report <b>expected counts with their 80% range</b>, not a count of coloured buildings. The range is
                conditional on probabilities that are not yet calibrated, so treat it as a floor on the real
                uncertainty.
              </li>
              <li>
                <b>Likely displaced</b> counts seasonal and vacant homes as occupied (pushes up) and leaves out homes
                that could not be read (pushes down). Both are stated beside it.
              </li>
              <li>The need index ranks census tracts for attention. It is not an eligibility determination.</li>
              <li>
                Every figure carries an absolute as-of time. Quote it with the number, the way an operational period
                is quoted.
              </li>
            </ul>
          </Section>

          <Section id="respond" title="Respond: lifelines, access, landing zones">
            <p>
              The <b>Respond</b> tab of an area follows FEMA's Community Lifelines: status first, then who is
              affected, then what to do. Status uses FEMA's colours, each with its own shape so it reads without
              colour:
            </p>
            <ul className="mt-2 grid grid-cols-2 gap-1.5 text-sm">
              {(
                [
                  ["green", "Stable: facilities found, none flagged"],
                  ["yellow", "Strained: one disrupted, or a critical one at risk"],
                  ["red", "Disrupted: a critical facility is down"],
                  ["grey", "Unknown: nothing found or nothing checked. Never read as fine."],
                ] as const
              ).map(([s, t]) => (
                <li key={s} className="flex items-start gap-2">
                  <span className="mt-1">
                    <StatusShape s={s} />
                  </span>
                  {t}
                </li>
              ))}
            </ul>
            <ul className="mt-3 list-disc space-y-1.5 pl-5">
              <li>
                <b>Who is cut off</b> gives three scenarios: known road blocks; plus debris (roads beside destroyed
                buildings, the realistic middle); and worst case (every bridge out, a planning bound, not a finding).
              </li>
              <li>
                <b>Search priority</b> ranks US National Grid 1 km squares by people in severe damage. Click a row to
                centre the map.
              </li>
              <li>
                <b>Helicopter landing candidates</b> are reconnaissance candidates from slope, clearing and land
                cover, never approved landing zones: wires, poles and soft ground are not in the data. Use the
                aviation unit's own standard.
              </li>
              <li>
                <b>Losses, debris and supplies</b> use published FEMA and CAL FIRE factors; each says how it was
                computed. <b>Plan for TAK / Google Earth</b> downloads the sectors, landing candidates, cut-off
                clusters and flagged facilities as KML.
              </li>
            </ul>
          </Section>

          <Section id="checks" title="Checks against field records">
            <p>
              Where inspectors, search teams or a lidar survey covered the same ground, <b>Checks</b> sets the calls
              beside their records: agreement both ways for full records (CAL FIRE inspections, FEMA damage
              assessments, search-team categories), how much was found for damage-only records, and where the ground
              moved for lidar. None of these is an accuracy figure; each says why. FEMA assistance by ZIP code sits
              here too: FEMA's figures cover whole ZIP codes and count households that registered, so look for gross
              disagreement only.
            </p>
          </Section>

          <Section id="review" title="Review and Verify">
            <p>
              The review queue is ordered by chance of Major or Destroyed times expected occupants. Open a structure,
              compare Before and After, and record what the imagery shows. A short note can be saved with a label.
              Labels are the only way accuracy gets measured; until enough exist, the overview says "Accuracy not yet
              validated" and shows no numbers. Follow docs/ops/LABELING_PROTOCOL.md. Areas marked TEST are held out:
              never tune on them.
            </p>
            <p className="mt-2">
              <b>Verify</b> is the blind version for teams: each building goes to three people who see only the Before
              and After images, never the model's call. Where Civil Air Patrol flew the event, Verify also shows their
              photos taken toward the building in the days after it. Two agreeing answers settle it; disagreements go
              to an analyst. Settled answers become labels only when someone releases them (
              <code>run.py truth-release</code>). See docs/truth/README.md.
            </p>
          </Section>

          <Section id="limits" title="What it cannot see">
            <ul className="list-disc space-y-1 pl-5">
              <li>Flood damage inside a home is usually invisible from above.</li>
              <li>Roofs under tree canopy, cloud, haze or shadow (flagged per structure).</li>
              <li>Homes built after the building-outline source was made.</li>
              <li>Anything the after-event imagery does not cover.</li>
              <li>The damage model was trained on other disasters and is not yet validated on held-out ground.</li>
            </ul>
          </Section>

          <Section id="keys" title="Keyboard">
            <table className="w-full text-sm">
              <tbody>
                {(
                  [
                    [["N"], "New assessment"],
                    [["B"], "Hold to see the before image"],
                    [["0", "4"], "Record a damage level (open structure)"],
                    [["x"], "Can't tell"],
                    [["j", "k"], "Next, previous in the queue"],
                    [["Esc"], "Close the structure, or cancel picking"],
                  ] as [string[], string][]
                ).map(([ks, t]) => (
                  <tr key={t} className="border-t border-line">
                    <td className="w-32 py-1.5">
                      {ks.map((k, i) => (
                        <span key={k}>
                          {i > 0 && <span className="px-1 text-ink-faint">{ks.length === 2 && ks[0] === "0" ? "–" : " "}</span>}
                          <Kbd>{k}</Kbd>
                        </span>
                      ))}
                    </td>
                    <td className="py-1.5 text-ink-dim">{t}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>

          <Section id="access" title="Access and privacy">
            <p>
              Building-level results, image chips, addresses, labels, exports, briefs and response products need the
              service token: set it with the key in the top bar; it stays in this browser. The public summary holds
              no addresses and withholds counts under 5.
            </p>
            <p className="mt-2">
              Everything works with no keys. Optional free keys add layers on the Conditions map: NASA FIRMS (active
              fire) and NC State Climate Office CLOUDS (current conditions). A free Census API key on the server
              (NCR_CENSUS_API_KEY) adjusts displacement for seasonal homes. No paid service is used.
            </p>
          </Section>

          <Section id="sources" title="Data sources">
            <p>
              USGS Water Data, NOAA NWPS, NWS and NHC, OpenFEMA, FEMA USA Structures, USACE National Structure
              Inventory, OpenStreetMap (ODbL), state orthoimagery (NC OneMap), USDA NAIP, NOAA NGS Emergency Response
              Imagery, Maxar Open Data (CC BY-NC 4.0), NIFC fire perimeters, USGS ShakeMap, NC Geological Survey
              landslides, CDC/ATSDR SVI. The status dot in the top bar shows each source's state and when it was last
              checked. Details: docs/ops/DATA_SOURCES.md.
            </p>
          </Section>
        </article>
      </div>
    </div>
  );
}

function jump(e: React.MouseEvent, id: string) {
  e.preventDefault();
  document.getElementById(`help-${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section id={`help-${id}`} className="scroll-mt-6 border-t border-line pt-6 mt-8 first-of-type:mt-6">
      <h2 className="mb-2 text-lg">{title}</h2>
      {children}
    </section>
  );
}

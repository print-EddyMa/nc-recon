import { DISCLAIMER, FEMA, FEMA_HEX, FEMA_LABEL, NOT_ASSESSED_HEX } from "../lib/ops";

/** Operator help: how to read and use the outputs, what they cannot tell you,
 * and where the data comes from. Plain text, printable. */
export default function Help() {
  return (
    <div className="h-full overflow-y-auto">
      <article className="mx-auto max-w-3xl px-5 py-6 text-[15px] leading-relaxed text-ink">
        <h1 className="font-display text-2xl font-semibold">Using NC Recon</h1>
        <p className="mt-2 rounded-md border border-line bg-warn px-3 py-2 font-medium text-warn-ink">
          {DISCLAIMER}
        </p>

        <h2 className="mt-6 text-lg font-semibold">What it does</h2>
        <p className="mt-1">
          For a point in North Carolina and a declared (or provisional) event, NC
          Recon pulls before- and after-event imagery, finds every structure in
          the area, and estimates each one's FEMA damage level with a
          probability. Uncertain and severe calls go to a human review queue.
          It also estimates how many people may be displaced and where need is
          highest, and it exports everything for GIS and field teams.
        </p>

        <h2 className="mt-6 text-lg font-semibold">Run a new assessment</h2>
        <ol className="mt-1 list-decimal space-y-1 pl-5">
          <li>Operations → <b>New assessment</b>. Pick the event.</li>
          <li>
            Enter a place name and coordinates, or click <b>Pick on map</b>. The
            blue square on the map is the ground the assessment will cover; the
            outlined boxes are areas already assessed.
          </li>
          <li>
            Choose the area size. Small (0.8 km across) runs in about 2 minutes;
            large (2.4 km) can take 10 minutes or more.
          </li>
          <li>
            <b>Check imagery</b> shows which after-event imagery covers the point
            (NC OneMap post-event orthos, NOAA emergency aerials, or Maxar
            satellite). If none does, the tool cannot assess that spot yet.
          </li>
          <li>
            Submit. One assessment runs at a time; others wait in line.{" "}
            <b>In progress</b> shows each step and how long it has run, for
            every analyst on this server, and <b>Cancel</b> stops one. The new
            area opens when it finishes.
          </li>
        </ol>
        <p className="mt-2">
          If the server restarts while an assessment is running, it is listed as
          Interrupted and nothing partial is kept: run it again.
        </p>
        <p className="mt-2">
          <b>Run again</b> on an operational area assesses it again from the
          imagery it already has, after a calibration or a software update.
          Labels are kept.
        </p>
        <p className="mt-2">
          Event not listed? Register a <b>provisional event</b> with its start
          date (and FEMA disaster number when declared). Before/after windows
          are derived from that date and enforced: an image taken before the
          incident can never be used as the "after" image.
        </p>

        <h2 className="mt-6 text-lg font-semibold">Reading the map</h2>
        <ul className="mt-2 space-y-1">
          {FEMA.map((c) => (
            <li key={c} className="flex items-center gap-2">
              <span className="inline-block h-4 w-4 rounded-sm border border-line" style={{ background: FEMA_HEX[c] }} />
              <b>{FEMA_LABEL[c]}</b>
            </li>
          ))}
          <li className="flex items-center gap-2">
            <span className="inline-block h-4 w-4 rounded-full" style={{ background: NOT_ASSESSED_HEX }} />
            <b>Not assessed</b>: in the structure inventory, but no building
            outline exists, so imagery was never read. Counted, never dropped.
          </li>
          <li className="flex items-center gap-2">
            <span className="inline-block h-4 w-4 rounded-sm border-2 border-accent" />
            <b>Blue outline</b>: needs human review. The card says why.
          </li>
        </ul>
        <p className="mt-2">
          Colour is the <i>most likely</i> level. Fill strength shows confidence:
          faint fills are uncertain. Use the probability bar on each structure
          card, not the colour alone.
        </p>
        <p className="mt-2">
          <b>Imagery under the structures</b> switches the map between the
          After and Before images this assessment actually read, with their
          capture dates. Over imagery the fills thin to a tint so the roof stays
          visible. A date shown as a range means the source does not publish the
          exact day.
        </p>

        <h2 className="mt-6 text-lg font-semibold">Numbers you can report</h2>
        <ul className="mt-1 list-disc space-y-1 pl-5">
          <li>
            Use <b>expected counts with their 80% range</b>, not a count of
            coloured buildings. The range is conditional on the model's
            probabilities, which are not yet calibrated, so treat it as a floor
            on the real uncertainty.
          </li>
          <li>
            <b>People likely displaced</b> is not an upper or lower bound: it
            counts seasonal and vacant homes as occupied (pushes up) and
            excludes homes that could not be assessed (pushes down). Both are
            stated beside the number.
          </li>
          <li>
            The need index ranks census tracts for attention. It is not an
            eligibility determination.
          </li>
        </ul>

        <h2 className="mt-6 text-lg font-semibold">FEMA assistance by ZIP code</h2>
        <p className="mt-1">
          Once Individual Assistance is being paid, each area can show how many
          owner households FEMA approved in the ZIP codes it touches, beside
          the homes this assessment expects at Major or Destroyed there. FEMA's
          figures cover the whole ZIP code and count households that
          registered, so the two will not match. Look for gross disagreement:
          heavy damage called where FEMA approved almost nobody, or the
          reverse.
        </p>

        <h2 className="mt-6 text-lg font-semibold">Review and ground truth</h2>
        <p className="mt-1">
          The review queue is ordered by chance of Major/Destroyed times
          expected occupants. Open a structure, compare Before and After, and
          record what the imagery shows (keys <b>0–4</b>, <b>x</b> = can't
          tell, <b>j/k</b> = next/previous). A short note can be saved with a
          label. Labels are the only way the
          system's accuracy gets measured; until enough exist, the accuracy
          panel says "Not yet validated" and shows no numbers. Follow
          docs/ops/LABELING_PROTOCOL.md. Areas marked TEST are held out: never
          tune on them.
        </p>
        <p className="mt-2">
          <b>Verify</b> is the blind version for teams: each building goes to
          three people who see only the Before and After images, never the
          model's call. Two agreeing answers settle it; disagreements go to an
          analyst. Settled answers become labels only when someone releases
          them (<code>run.py truth-release</code>). See docs/truth/README.md.
        </p>

        <h2 className="mt-6 text-lg font-semibold">What it cannot see</h2>
        <ul className="mt-1 list-disc space-y-1 pl-5">
          <li>Flood damage inside a home is usually invisible from above.</li>
          <li>Roofs under tree canopy, cloud, haze or shadow (flagged per structure).</li>
          <li>Homes built after the building-outline source was made.</li>
          <li>Anything the after-event imagery does not cover.</li>
          <li>
            The damage model only looks at the after-event image and was
            trained on other disasters; it has not been validated in NC.
          </li>
        </ul>

        <h2 className="mt-6 text-lg font-semibold">Access and privacy</h2>
        <p className="mt-1">
          Building-level results, image chips, addresses, labels, exports and the
          situation brief require the service token (enter it once under
          Operations → Responder access; it stays in this browser). The public
          tract summary contains no addresses and withholds counts under 5.
        </p>

        <h2 className="mt-6 text-lg font-semibold">Keys</h2>
        <p className="mt-1">
          Everything works with no keys. Optional free keys add layers on the
          Conditions map: NASA FIRMS (active fire) and NC State Climate Office
          CLOUDS (current conditions). A free Census API key on the server
          (NCR_CENSUS_API_KEY) adjusts displacement for seasonal homes. No paid
          service is used.
        </p>

        <h2 className="mt-6 text-lg font-semibold">Data sources</h2>
        <p className="mt-1">
          USGS Water Data, NOAA NWPS/NWS/NHC, NCDOT DriveNC, OpenFEMA, FEMA USA
          Structures, USACE National Structure Inventory, OpenStreetMap (ODbL),
          NC OneMap orthoimagery, NOAA NGS Emergency Response Imagery, Maxar
          Open Data (CC BY-NC 4.0), CDC/ATSDR SVI. The Data sources panel
          shows each source's state and when it was last checked; <b>Check
          again</b> re-tests them. Details: docs/ops/DATA_SOURCES.md.
        </p>
      </article>
    </div>
  );
}

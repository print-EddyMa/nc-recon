/**
 * Ops mode (Phase J): the pipeline's `terratriage.ops` output, served by
 * `server.py` under /ops. Five FEMA ordinal classes with probabilities, a
 * review flag with reasons, per-channel evidence, USNG and provenance.
 *
 * Needs the pipeline service (`VITE_API_URL`). Responder-only calls (labels,
 * addresses, exports) send the bearer token the analyst pasted in the Ops
 * screen; with no token configured server-side they only work from localhost.
 */
import { API_URL } from "./catalog";

export const DISCLAIMER =
  "Decision-support tool. Not an official FEMA or state emergency management damage assessment. Verify on the ground.";

export const FEMA = [
  "no_damage",
  "affected",
  "minor",
  "major",
  "destroyed",
] as const;
export type FemaClass = (typeof FEMA)[number];

export const FEMA_LABEL: Record<FemaClass, string> = {
  no_damage: "No damage",
  affected: "Affected",
  minor: "Minor",
  major: "Major",
  destroyed: "Destroyed",
};

/** ColorBrewer YlOrRd (colour-blind + print safe); no damage = neutral grey.
 * Deliberately NOT the 4-class xView2 ramp of the demo screens: this is a
 * different (FEMA) vocabulary and must not be confused with it. */
export const FEMA_HEX: Record<FemaClass, string> = {
  no_damage: "#9e9e9e",
  affected: "#fecc5c",
  minor: "#fd8d3c",
  major: "#f03b20",
  destroyed: "#bd0026",
};
export const NOT_ASSESSED_HEX = "#555555";

export interface Evidence {
  id: string;
  available: boolean;
  status: string;
  weight: number;
  reasons: string[];
  likelihood?: number[];
  unavailable_reason?: string;
  detail?: Record<string, unknown>;
}

export interface OpsProps {
  ncr_id: string;
  source_ids: Record<string, string | number>;
  footprint_source: string | null;
  area_m2?: number;
  centroid: [number, number];
  usng_1m: string;
  usng_10m: string;
  damage_level: FemaClass | null;
  damage_probs: Record<FemaClass, number> | null;
  confidence: number | null;
  needs_review: boolean;
  review_reasons: string[];
  prediction_set: FemaClass[] | null;
  reason_codes: string[];
  evidence: Evidence[];
  evidence_unavailable: Record<string, string>;
  occupancy: string | null;
  primary_occupancy?: string | null;
  flags: Record<string, boolean>;
  occupants?: {
    nsi_estimate?: number;
    usa_structures_median?: number | null;
    usa_structures_ci95?: (number | null)[];
    period?: string;
  } | null;
  stories?: number | null;
  foundation_height_ft?: number | null;
  ground_elev_m_navd88?: number | null;
  flood_zone?: string | null;
  footprint_image_date?: string | null;
}

export type OpsFeature = GeoJSON.Feature<
  GeoJSON.Polygon | GeoJSON.Point,
  OpsProps
>;

export interface OpsRunProps {
  schema: string;
  run_id: string;
  generated_utc: string;
  disclaimer: string;
  event: { id: string; name: string; declarations: string[]; incident_begin: string };
  aoi: {
    id: string;
    /** the name an analyst gave the area, when one was recorded */
    name?: string;
    role: "TUNE" | "TEST" | "OPS" | string;
    county: string;
    center?: [number, number];
  };
  pair_context: Record<string, unknown> & { reasons: string[] };
  counts: Record<FemaClass, number>;
  expected_counts: Record<FemaClass, number>;
  expected_counts_80pct: Record<FemaClass, [number, number]>;
  n_structures: number;
  n_needs_review: number;
  not_assessed: { total: number; residential: number };
  calibration: Record<string, string | number>;
  warnings: string[];
  provenance: Record<string, unknown>;
}

export interface OpsCollection
  extends GeoJSON.FeatureCollection<GeoJSON.Polygon | GeoJSON.Point, OpsProps> {
  properties: OpsRunProps;
}

export type OpsAreaSummary = Pick<
  OpsRunProps,
  | "run_id"
  | "generated_utc"
  | "event"
  | "aoi"
  | "counts"
  | "expected_counts"
  | "expected_counts_80pct"
  | "n_structures"
  | "n_needs_review"
  | "not_assessed"
  | "calibration"
  | "warnings"
> & {
  id: string;
  /** [west, south, east, north] of the assessed structures */
  bbox?: [number, number, number, number] | null;
};

export interface HealthRow {
  source: string;
  status: "ok" | "stale" | "down" | "unconfigured";
  latency_ms: number | null;
  data_age_s: number | null;
  detail: string;
  checked_utc: string;
}

const TOKEN_KEY = "terratriage:responderToken";
const LABELER_KEY = "terratriage:labeler";

function ls(key: string): string {
  try {
    return localStorage.getItem(key) ?? "";
  } catch {
    return "";
  }
}
function lsSet(key: string, v: string) {
  try {
    if (v) localStorage.setItem(key, v);
    else localStorage.removeItem(key);
  } catch {
    /* private window */
  }
}
export const responderToken = () => ls(TOKEN_KEY);
export const setResponderToken = (v: string) => lsSet(TOKEN_KEY, v.trim());
export const labelerName = () => ls(LABELER_KEY);
export const setLabelerName = (v: string) => lsSet(LABELER_KEY, v.trim());

export function authHeaders(): HeadersInit {
  const t = responderToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

/** An offline server refuses network routes with 503 and a sentence saying why. */
async function refusal(r: Response, fallback: string): Promise<string> {
  if (r.status !== 503) return fallback;
  try {
    const j = (await r.json()) as { detail?: unknown };
    return typeof j.detail === "string" ? j.detail : fallback;
  } catch {
    return fallback;
  }
}

async function getJSON<T>(path: string, auth = false): Promise<T> {
  const r = await fetch(`${API_URL}${path}`, {
    signal: AbortSignal.timeout(60_000),
    headers: auth ? authHeaders() : undefined,
  });
  if (!r.ok) throw new Error(await refusal(r, `${path}: ${r.status}`));
  return (await r.json()) as T;
}

export const loadOpsAreas = () => getJSON<OpsAreaSummary[]>("/ops/areas");
export const loadOpsArea = (id: string) =>
  getJSON<OpsCollection>(`/ops/areas/${encodeURIComponent(id)}`, true);
export interface HealthBoard {
  checked_utc: string;
  sources: HealthRow[];
  /** a background re-check is running; `checked_utc` will move when it lands */
  refreshing?: boolean;
}
export const loadHealth = (recheck = false) =>
  getJSON<HealthBoard>(`/ops/health${recheck ? "?recheck=1" : ""}`);
export const loadReport = () => getJSON<Record<string, unknown>>("/ops/report");
export const loadLabels = (area: string) =>
  getJSON<{ ncr_id: string; label: string; labeler: string }[]>(
    `/ops/labels/${encodeURIComponent(area)}`,
    true,
  );
export const loadResponder = (area: string) =>
  getJSON<{ structures: Record<string, { address: string }> }>(
    `/ops/areas/${encodeURIComponent(area)}/responder`,
    true,
  );

export interface Impact {
  residential_structures_assessed: number;
  occupancy_adjustment: string;
  expected_displaced: { p10: number; median: number; p90: number };
  need_index_terms_missing: string[];
  bias_note?: string;
  unassessed_residential?: { structures: number; occupants_nsi: number };
  tracts: {
    tract: string;
    location: string | null;
    structures: number | null;
    expected_displaced: number | null;
    svi_percentile: number | null;
    need_index: number | null;
  }[];
  note: string;
}
export const loadImpact = (area: string) =>
  getJSON<Impact>(`/ops/areas/${encodeURIComponent(area)}/impact`);
/** FEMA Individual Assistance by ZIP code beside this assessment's own
 * numbers for the same ZIPs. Context, not validation (see `caveat`). */
export interface FemaReference {
  status: "OK" | "NO_FEMA_DATA" | "NO_DECLARATION";
  declarations: string[];
  unplaced_structures: number;
  caveat: string;
  warnings: string[];
  zips: {
    zip: string;
    structures: number;
    homes_assessed: number;
    expected_major_plus: number;
    fema: {
      owners: {
        registrations: number;
        approved: number;
        approved_over_25k: number;
        max_grants: number;
      } | null;
      renters: { registrations: number; approved: number } | null;
    } | null;
  }[];
  source: { name: string; url: string };
}
export const loadFemaReference = (area: string) =>
  getJSON<FemaReference>(`/ops/areas/${encodeURIComponent(area)}/fema-assistance`, true);

/** The calls beside the Helene search-and-rescue field categories for
 * the same structures. A comparison, not validation (see `caveats`). */
export interface FieldReference {
  area: string;
  role: string | null;
  county: string | null;
  reference: { name: string; url: string };
  match_rule: string;
  credible_set: string;
  counts: { waypoints: number; matched: number; unmatched: number; not_structure: number; superseded_visits: number };
  summary: {
    n: number;
    levels: string[];
    confusion_rows_sar_cols_ncr: number[][];
    same_level: number | null;
    within_one_level: number | null;
    kappa: number | null;
    sar_level_in_80pct_set: number | null;
    major_or_destroyed: {
      both_count: number;
      sar_count: number;
      ncr_most_likely_count: number;
      ncr_expected_count: number;
      precision: number | null;
      recall: number | null;
    };
  };
  summary_homes?: {
    n: number;
    major_or_destroyed: { both_count: number; sar_count: number; ncr_most_likely_count: number };
  };
  caveats: string[];
}
export const loadFieldReference = (area: string) =>
  getJSON<FieldReference>(`/ops/areas/${encodeURIComponent(area)}/field-reference`, true);

export const publicUrl = (area: string) =>
  `${API_URL}/ops/areas/${encodeURIComponent(area)}/public.geojson`;

const chipUrl = (area: string, ncrId: string, kind: "pre" | "post") =>
  `${API_URL}/ops/areas/${encodeURIComponent(area)}/chip/${ncrId}/${kind}.png`;

/** XYZ tile template for the before / after imagery an assessment read.
 * Responder-only: pair it with `opsRequestHeaders` in the map's
 * `transformRequest`, since a tile request cannot otherwise carry the token. */
export const imageryTileUrl = (area: string, kind: "pre" | "post") =>
  `${API_URL}/ops/areas/${encodeURIComponent(area)}/tiles/${kind}/{z}/{x}/{y}`;
export const isOpsUrl = (url: string) => url.startsWith(`${API_URL}/ops/`);
export const opsRequestHeaders = (): Record<string, string> => {
  const t = responderToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
};

/** One before / after image as recorded in the run's provenance. */
export interface ImageryRecord {
  role: "pre" | "post";
  source?: string;
  license?: string;
  acquired_utc?: string | null;
  date_label?: string;
  date_min?: string | null;
  date_max?: string | null;
  geometry?: { date?: string | null };
}

/** The capture date as far as it is known: a day, a range, or the program
 * label when the source publishes no date. Never an invented day. */
export function imageryDate(r: ImageryRecord | undefined): string {
  if (!r) return "date unknown";
  if (r.acquired_utc) return r.acquired_utc.slice(0, 10);
  if (r.geometry?.date) return r.geometry.date;
  if (r.date_min && r.date_max)
    return r.date_min === r.date_max ? r.date_min : `${r.date_min} to ${r.date_max}`;
  return r.date_label?.split(/[;,(]/)[0].trim() || "date unknown";
}

/** Chips are responder-only, and an <img> cannot send the bearer header, so
 * fetch with the header and hand back an object URL (caller revokes it). */
export async function loadChip(
  area: string,
  ncrId: string,
  kind: "pre" | "post",
): Promise<string> {
  const r = await fetch(chipUrl(area, ncrId, kind), { headers: authHeaders() });
  if (!r.ok) throw new Error(`chip ${r.status}`);
  return URL.createObjectURL(await r.blob());
}

/** Open the (responder-only) brief in a new tab via a blob, so the token
 * travels in a header rather than the URL. */
export async function openBrief(area: string): Promise<void> {
  const w = window.open("", "_blank");
  const r = await fetch(
    `${API_URL}/ops/areas/${encodeURIComponent(area)}/brief.html`,
    { headers: authHeaders() },
  );
  if (!r.ok) {
    w?.close();
    throw new Error(
      r.status === 401 || r.status === 403
        ? "Responder token required for the brief"
        : `brief failed (${r.status})`,
    );
  }
  const url = URL.createObjectURL(new Blob([await r.text()], { type: "text/html" }));
  if (w) w.location.href = url;
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

// ---------------------------------------------------------------------------
// Groma Verify (docs/truth/README.md): blind verification tasks.
// A task carries no model output, by design.
// ---------------------------------------------------------------------------
export interface VerifyTask {
  area: string;
  ncr_id: string | null;
  done?: boolean;
  judgments_so_far?: number;
  needed?: number;
  remaining_in_area?: number;
  imagery?: { pre?: string; post?: string };
}
export interface VerifyAreaStatus {
  area: string;
  aoi_role: string;
  candidates: number;
  judgments: number;
  verifiers: number;
  verified: number;
  escalated: number;
  unverifiable: number;
  in_progress: number;
  released: number;
  median_seconds_per_judgment: number | null;
}
const VERIFIER_KEY = "terratriage:verifier";
export const verifierName = () => ls(VERIFIER_KEY);
export const setVerifierName = (v: string) => lsSet(VERIFIER_KEY, v.trim());
export const nextVerifyTask = (area: string, worker: string, role: "verifier" | "analyst") =>
  getJSON<VerifyTask>(
    `/ops/truth/next?area=${encodeURIComponent(area)}&worker=${encodeURIComponent(worker)}&role=${role}`,
    true,
  );
export const loadVerifyStatus = (area: string) =>
  getJSON<VerifyAreaStatus>(`/ops/truth/areas/${encodeURIComponent(area)}`, true);

/** Civil Air Patrol frames that probably show a building (reviewer context). */
export interface CapPhoto {
  key: string;
  kind: "oblique" | "nadir";
  date: string;
  dist_m: number;
  /** expected horizontal position of the building in an oblique, 0..1 */
  x_frac: number | null;
  url: string;
  mission: string | null;
}
export interface CapPhotos {
  photos: CapPhoto[];
  note: string | null;
  source: string;
  caveat: string;
}
export const loadCapPhotos = (area: string, ncrId: string) =>
  getJSON<CapPhotos>(`/ops/photos/${encodeURIComponent(area)}/${encodeURIComponent(ncrId)}`, true);
export async function loadCapThumb(area: string, key: string): Promise<string> {
  const r = await fetch(`${API_URL}/ops/photos/${encodeURIComponent(area)}/thumb/${encodeURIComponent(key)}.jpg`, {
    headers: authHeaders(),
    signal: AbortSignal.timeout(180_000),
  });
  if (!r.ok) throw new Error(`photo: ${r.status}`);
  return URL.createObjectURL(await r.blob());
}
export async function postJudgment(body: {
  area: string;
  ncr_id: string;
  label: string;
  worker: string;
  role: "verifier" | "analyst";
  seconds: number;
}): Promise<{ ok: boolean; status: { status: string; label?: string | null } | null }> {
  const r = await fetch(`${API_URL}/ops/truth/judgments`, {
    method: "POST",
    headers: { "content-type": "application/json", ...authHeaders() },
    body: JSON.stringify({ ...body, kind: "remote", blind: true }),
  });
  if (!r.ok) {
    throw new Error(
      r.status === 401 || r.status === 403
        ? "Responder token required (Operations > Responder access)"
        : r.status === 409
          ? "You already judged this building"
          : `not saved (${r.status})`,
    );
  }
  return r.json();
}

export async function postLabel(body: {
  area: string;
  ncr_id: string;
  label: string;
  labeler: string;
  notes?: string;
}): Promise<{ ok: boolean; aoi_role: string }> {
  const r = await fetch(`${API_URL}/ops/labels`, {
    method: "POST",
    headers: { "content-type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const msg = r.status === 401 || r.status === 403
      ? "Responder token required to record labels"
      : `label not saved (${r.status})`;
    throw new Error(msg);
  }
  return r.json();
}

export function downloadExport(area: string): Promise<void> {
  return downloadZip(area, "export.zip", `groma-${area}-responder.zip`);
}

/** Initial damage assessment packet in FEMA's PDA formats: Excel, GeoPackage
 * and the PDA narrative, pre-filled from the run (responder only). */
export function downloadIda(area: string): Promise<void> {
  return downloadZip(area, "ida.zip", `groma-${area}-ida.zip`);
}

async function downloadZip(area: string, file: string, name: string): Promise<void> {
  const r = await fetch(
    `${API_URL}/ops/areas/${encodeURIComponent(area)}/${file}`,
    { headers: authHeaders() },
  );
  if (!r.ok) {
    if (r.status === 401 || r.status === 403)
      throw new Error("Responder token required for building-level exports");
    // the server says why in plain words (e.g. an area with no structures)
    const detail = await r
      .json()
      .then((j: { detail?: unknown }) => (typeof j.detail === "string" ? j.detail : null))
      .catch(() => null);
    throw new Error(detail ?? `export failed (${r.status})`);
  }
  const blob = await r.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
}

/** P(>= Major), the review-queue priority driver. */
export const pSevere = (p: OpsProps) =>
  p.damage_probs ? p.damage_probs.major + p.damage_probs.destroyed : 0;

export const occupantsOf = (p: OpsProps): number =>
  p.occupants?.nsi_estimate ?? p.occupants?.usa_structures_median ?? 0;

/** Review order: P(>= Major) x expected occupants (occupied homes first). */
export const reviewPriority = (p: OpsProps) =>
  pSevere(p) * Math.max(0.5, occupantsOf(p));

export function fmtAge(s: number | null): string {
  if (s == null) return "";
  if (s < 3600) return `${Math.round(s / 60)} min old`;
  if (s < 172800) return `${(s / 3600).toFixed(1)} h old`;
  return `${Math.round(s / 86400)} d old`;
}


// --------------------------------------------------------------------------- //
// events + new assessments
// --------------------------------------------------------------------------- //
export interface OpsEvent {
  id: string;
  name: string;
  state: string;
  declarations: string[];
  incident_begin: string;
  provisional: boolean;
  pre_window: [string, string];
  post_window: [string, string];
  post_sources: string[];
  aois: { id: string; role: string; county: string; center: [number, number] }[];
}

export const loadEvents = () => getJSON<OpsEvent[]>("/ops/events");

export const checkCoverage = (event: string, lon: number, lat: number) =>
  getJSON<{ covered: boolean; post_source?: string; reason?: string }>(
    `/ops/coverage?event=${encodeURIComponent(event)}&lon=${lon}&lat=${lat}`,
    true,
  );

export interface Job {
  id: string;
  area: string;
  event: string;
  name: string;
  /** a new area, or an existing one run again on its stored imagery */
  kind?: "assess" | "reassess";
  status: "queued" | "running" | "done" | "failed" | "cancelled" | "lost";
  step: string;
  post_source: string | null;
  error: string | null;
  warnings?: string[];
  log: string[];
  created: number;
  started?: number | null;
  finished: number | null;
}

export const jobActive = (j: Job) => j.status === "queued" || j.status === "running";

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    let msg = `${r.status}`;
    try {
      const j = (await r.json()) as { detail?: unknown };
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* not json */
    }
    if (r.status === 401 || r.status === 403) msg = "Responder token required";
    throw new Error(msg);
  }
  return (await r.json()) as T;
}

export const submitAssessment = (body: {
  event: string;
  name: string;
  lon: number;
  lat: number;
  half_m: number;
}) => postJSON<Job>("/ops/assess", body);

export const jobStatus = (id: string) => getJSON<Job>(`/ops/assess/${id}`, true);

/** Recent assessment jobs, newest first (kept across server restarts). */
export const loadJobs = () => getJSON<Job[]>("/ops/jobs", true);

export async function cancelJob(id: string): Promise<Job> {
  const r = await fetch(`${API_URL}/ops/assess/${encodeURIComponent(id)}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!r.ok)
    throw new Error(
      r.status === 401 || r.status === 403 ? "Responder token required" : `cancel failed (${r.status})`,
    );
  return (await r.json()) as Job;
}

/** "45 s" / "3 min" / "1 h 05 min", for how long a job has been going. */
export function fmtDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s} s`;
  if (s < 3600) return `${Math.round(s / 60)} min`;
  return `${Math.floor(s / 3600)} h ${String(Math.round((s % 3600) / 60)).padStart(2, "0")} min`;
}

export const createEvent = (body: {
  id: string;
  name: string;
  incident_begin: string;
  disaster_numbers: number[];
  eri_prefix?: string;
}) => postJSON<OpsEvent>("/ops/events", body);

export const POST_SOURCE_LABEL: Record<string, string> = {
  nc_helene_2025: "NC OneMap post-Helene aerial orthos (leaf-off, 6 in)",
  eri: "NOAA NGS emergency response aerials",
  maxar: "Maxar Open Data satellite",
};

/** "12 min ago" / "3 h ago" / date, for data-as-of labels. */
export function ago(iso: string | number | null | undefined): string {
  if (!iso) return "unknown";
  const t = typeof iso === "number" ? iso * 1000 : Date.parse(iso);
  if (!Number.isFinite(t)) return "unknown";
  const s = (Date.now() - t) / 1000;
  if (s < 90) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 48 * 3600) return `${Math.round(s / 3600)} h ago`;
  return new Date(t).toLocaleDateString();
}

/** Assess an operational area again from the imagery it already has. */
export const reassessArea = (area: string) =>
  postJSON<Job>(`/ops/areas/${encodeURIComponent(area)}/reassess`, {});

export async function deleteArea(area: string): Promise<void> {
  const r = await fetch(`${API_URL}/ops/areas/${encodeURIComponent(area)}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!r.ok) throw new Error(r.status === 401 || r.status === 403 ? "Responder token required" : `delete failed (${r.status})`);
}

// --------------------------------------------------------------------------- //
// any-hazard events from a FEMA declaration (UI, fork 3)
// --------------------------------------------------------------------------- //
export interface FemaEventDraft {
  event_id: string;
  name: string;
  state: string;
  hazards: string[];
  disaster_number: number;
  incident_begin: string;
  designated_areas: string[];
  post_days: [number, number];
  eri_prefix: string | null;
  maxar_event: string | null;
  candidates?: Record<string, { folder: string; score: number; why: string[] }[]>;
  notes: string[];
}
/** Draft (write=false) or register (write=true) an event from its FEMA number. */
export const eventFromFema = (disaster_number: number, write = false) =>
  postJSON<{ event: OpsEvent | null; draft: FemaEventDraft }>("/ops/events/from-fema", {
    disaster_number,
    write,
  });

/** Coverage answer including the before-event source where the API gives it. */
export const checkCoverageFull = (event: string, lon: number, lat: number) =>
  getJSON<{ covered: boolean; post_source?: string; pre_source?: string; reason?: string }>(
    `/ops/coverage?event=${encodeURIComponent(event)}&lon=${lon}&lat=${lat}`,
    true,
  );

export const PRE_SOURCE_LABEL: Record<string, string> = {
  nc_2020_2023: "NC OneMap statewide orthos (leaf-off, 6 in)",
  naip: "USDA NAIP aerial (leaf-on, 0.3-0.6 m)",
};

export const HAZARD_LABEL: Record<string, string> = {
  riverine_flood: "River flooding",
  flash_flood: "Flash flooding",
  coastal_surge: "Storm surge",
  wind: "Wind",
  tornado: "Tornado",
  wildfire: "Wildfire",
  earthquake: "Earthquake",
  landslide: "Landslide",
  volcanic: "Volcanic",
  winter: "Winter storm",
  other: "Other",
};

/** Every stored comparison of an area with a published field record or
 * measurement (responder): DINS, FEMA historical, SARCOP, NEMAC, lidar. */
export interface AreaReference {
  source: "dins" | "fema_hgda" | "nemac" | "sarcop" | "lidar" | string;
  role?: string;
  generated_utc?: string;
  reference?: { name: string; url: string };
  match_rule?: string;
  counts?: Record<string, number>;
  caveats: string[];
  summary?: Record<string, unknown> | null;
  summary_homes?: Record<string, unknown> | null;
  // lidar ground change
  rule?: string;
  typical_change_m?: number;
  measured?: number;
  structures?: number;
  flag_counts?: Record<string, number>;
  flagged_by_ncr_level?: Partial<Record<FemaClass, number>>;
}
export const loadReferences = (area: string) =>
  getJSON<{ area: string; references: AreaReference[] }>(
    `/ops/areas/${encodeURIComponent(area)}/references`,
    true,
  );

// --------------------------------------------------------------------------
// Response products (pipeline ops/response/, routes in ops/response_api.py)
// --------------------------------------------------------------------------
export type LifelineColour = "red" | "yellow" | "green" | "grey";
export type FacilityStatus = "disrupted" | "at_risk" | "no_evidence" | "not_assessed";

export interface CutOffScenario {
  isolated_buildings: number;
  isolated_people_est: number;
  isolated_major_or_destroyed: number;
}
export interface ResponseSector {
  priority: number;
  usng_1km: string;
  center: [number, number];
  buildings: number;
  major_or_destroyed_expected: number;
  people_in_severe_expected: number;
  people: number;
  cut_off_buildings: number;
  cut_off_people: number;
  needs_review: number;
  review_share: number;
}
export interface LandingZone {
  lon: number;
  lat: number;
  usng: string;
  clear_diameter_m: number;
  slope_deg: number;
  elevation_m: number;
  cover: string;
  marginal: boolean;
  fits: string[];
  nearest_need: { label: string; distance_m: number; weight: number } | null;
  score: number;
}
export interface Lifeline {
  lifeline: string;
  label: string;
  status: LifelineColour;
  facilities: number;
  disrupted: number;
  at_risk: number;
  not_assessed: number;
  first_look: { name: string; kind: string; status: FacilityStatus; reasons: string[]; lon: number; lat: number }[];
  roads_note?: string;
  bridges_unverified?: number;
  note?: string;
}
export interface ResponseFacility {
  id: string;
  kind: string;
  lifeline: string;
  name: string | null;
  lon: number;
  lat: number;
  status: FacilityStatus;
  reasons: string[];
  critical: boolean;
  min_to_hospital: number | null;
}
export interface UsdRange {
  low: number;
  high: number;
}
export interface ResponseProducts {
  schema: "groma.response/1";
  area: string;
  run_id: string;
  generated_utc: string;
  disclaimer: string;
  summary: {
    area: string;
    event: string;
    hazards: string[];
    buildings_assessed: number;
    /** Inventory points with no footprint: unknown, never undamaged. */
    buildings_not_assessed: number;
    /** assessed / (assessed + not assessed) */
    coverage: number;
    reading_notes: string[];
    major_or_destroyed_expected: number;
    people_in_severe_expected: number;
    cut_off: { known_blocks: CutOffScenario; plus_debris: CutOffScenario; worst_case: CutOffScenario } | null;
    lifelines: { lifeline: string; label: string; status: LifelineColour }[];
    landing_zone_candidates: number;
    water_systems_at_risk: number;
    private_well_homes: number | null;
    building_loss_usd: (UsdRange & { buildings_valued: number; buildings_without_value: number; note: string }) | null;
    debris_cy: (UsdRange & { destroyed_expected: number; method: string }) | null;
    top_sectors: Pick<ResponseSector, "priority" | "usng_1km" | "major_or_destroyed_expected" | "people_in_severe_expected" | "cut_off_people">[];
  };
  access: {
    box: number[];
    roads: { ways: number; segments: number; blocked: number; debris: number; bridge: number; exits: number };
    hospitals: { name: string | null; id: string; lon: number; lat: number }[];
    scenarios: { known_blocks: CutOffScenario; plus_debris: CutOffScenario; worst_case: CutOffScenario };
    isolated_clusters: { cluster: number; buildings: number; people_est: number; major_or_destroyed: number; center: [number, number]; usng: string }[];
    method: string;
  } | null;
  resources: { lifelines: Lifeline[]; status_rule: string; facilities: ResponseFacility[] } | null;
  landing: { candidates: LandingZone[]; params: Record<string, number>; caveat?: string; open_fraction?: number } | null;
  money: {
    building_loss_usd: UsdRange & { buildings_valued: number; buildings_without_value: number; note: string };
    homes_major_or_destroyed_expected: number;
    debris_cy: UsdRange & { destroyed_expected: number; method: string };
    public_assistance_threshold: {
      fiscal_year: number;
      county?: string;
      county_population_2024?: number;
      countywide_per_capita?: number;
      county_threshold_usd?: number;
      statewide_per_capita?: number;
      source?: string;
      note?: string;
    };
    ratio_source: string;
  } | null;
  sectors: ResponseSector[];
  needs: {
    people_served: number;
    people_displaced_expected: number | null;
    people_cut_off: number;
    water_litres_per_day: number;
    meals_per_day: number;
    shelter_ft2_standard: number;
    shelter_ft2_evacuation: number;
    distribution_points: { type: string; count: number; people_per_day_each: number }[];
    note: string;
  };
  water: {
    systems: {
      pwsid: string;
      name: string;
      population_served: number | null;
      boundary: string;
      buildings_assessed_inside: number;
      major_or_destroyed_expected: number;
      people_in_assessed_buildings: number;
      status: "at_risk" | "no_evidence";
      reasons: string[];
      flagged_facilities: { name: string | null; kind: string; status: FacilityStatus }[];
    }[];
    private_wells: { residential_buildings: number; people_est: number; major_or_destroyed_expected: number; advice: string };
    note: string;
  } | null;
  power: {
    /** false: the event is too old for live outage feeds; null: feed unavailable */
    active: boolean | null;
    counties?: { utility: string; county: string; state: string; meters_out: number; estimated_restoration: string | null }[];
    note: string;
  };
  sources: Record<string, { name: string; url?: string; license: string }>;
  notes: string[];
  errors: Record<string, string>;
}
/** Map layers: properties.layer is road | cut_off_cluster | facility | landing_zone | sector. */
export interface ResponseLayers {
  type: "FeatureCollection";
  features: { type: "Feature"; geometry: { type: string; coordinates: unknown }; properties: Record<string, unknown> & { layer: string } }[];
}
const respPath = (area: string) => `/ops/areas/${encodeURIComponent(area)}/response`;
export const loadResponse = (area: string) => getJSON<ResponseProducts>(respPath(area), true);
export const loadResponseLayers = (area: string) => getJSON<ResponseLayers>(`${respPath(area)}/layers`, true);
export const loadResponseStatus = (area: string) =>
  getJSON<{ area: string; status: "building" | "idle"; started_utc: string | null; error: string | null; built: boolean }>(
    `${respPath(area)}/status`,
    true,
  );
export async function buildResponse(area: string): Promise<{ area: string; status: string }> {
  const r = await fetch(`${API_URL}${respPath(area)}`, {
    method: "POST",
    headers: authHeaders(),
    signal: AbortSignal.timeout(30_000),
  });
  if (!r.ok) throw new Error(await refusal(r, `build response: ${r.status}`));
  return r.json();
}
/** KML download URL (opens in Google Earth, ATAK/WinTAK, ArcGIS); needs the responder token header, so fetch it as a blob. */
export async function downloadResponseKml(area: string): Promise<Blob> {
  const r = await fetch(`${API_URL}${respPath(area)}/plan.kml`, { headers: authHeaders() });
  if (!r.ok) throw new Error(`plan.kml: ${r.status}`);
  return r.blob();
}

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

export const OPS_ENABLED =
  import.meta.env.VITE_NCR_OPS_MODE === "1" || !!API_URL;

export const DISCLAIMER =
  "Decision-support tool. Not an official FEMA or NC Emergency Management damage assessment. Verify on the ground.";

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
  aoi: { id: string; role: "TUNE" | "TEST" | string; county: string };
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
> & { id: string };

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

function authHeaders(): HeadersInit {
  const t = responderToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

async function getJSON<T>(path: string, auth = false): Promise<T> {
  const r = await fetch(`${API_URL}${path}`, {
    signal: AbortSignal.timeout(60_000),
    headers: auth ? authHeaders() : undefined,
  });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return (await r.json()) as T;
}

export const loadOpsAreas = () => getJSON<OpsAreaSummary[]>("/ops/areas");
export const loadOpsArea = (id: string) =>
  getJSON<OpsCollection>(`/ops/areas/${encodeURIComponent(id)}`);
export const loadHealth = () =>
  getJSON<{ checked_utc: string; sources: HealthRow[] }>("/ops/health");
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

export const chipUrl = (area: string, ncrId: string, kind: "pre" | "post") =>
  `${API_URL}/ops/areas/${encodeURIComponent(area)}/chip/${ncrId}/${kind}.png`;

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

export async function downloadExport(area: string): Promise<void> {
  const r = await fetch(
    `${API_URL}/ops/areas/${encodeURIComponent(area)}/export.zip`,
    { headers: authHeaders() },
  );
  if (!r.ok) {
    throw new Error(
      r.status === 401 || r.status === 403
        ? "Responder token required for building-level exports"
        : `export failed (${r.status})`,
    );
  }
  const blob = await r.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `nc-recon-${area}-responder.zip`;
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

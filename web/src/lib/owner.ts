// Owner evidence record and the public check (pipeline ops/owner.py).
// The record link is the credential: it lives in the URL fragment and is sent
// in a POST body, so it never lands in a server log or a Referer header.
import { API_URL } from "./catalog";

export interface EvidenceLine {
  channel: string;
  says: string;
  used: boolean;
}

export interface OwnerRecord {
  area: string;
  ncr_id: string;
  address: string | null;
  usng_10m: string | null;
  event: string | null;
  declarations: string[];
  county: string | null;
  state: string;
  level: string | null;
  level_label: string;
  probability: number | null;
  probs: Record<string, number>;
  needs_review: boolean;
  people_checked: { status: string; label: string | null; judgments: number };
  field_confirmed: boolean;
  confirmed_by_people: boolean;
  imagery: { before: string | null; after: string | null };
  evidence: EvidenceLine[];
  validation: string;
  run_id: string | null;
  assessed_utc: string | null;
  uses: string[];
  disclaimer: string;
  expires_utc: string;
}

export interface LookupAnswer {
  area: string;
  answer: "banded" | "too_few" | "not_found";
  text: string;
  note?: string;
  severe_band?: "few" | "some" | "many" | "most";
  any_damage_band?: "few" | "some" | "many" | "most";
  buildings_band?: string;
  radius_m?: number;
  event?: string | null;
  assessed_utc?: string | null;
  center?: [number, number];
}

async function detail(r: Response, fallback: string): Promise<string> {
  try {
    const j = (await r.json()) as { detail?: unknown };
    return typeof j.detail === "string" ? j.detail : fallback;
  } catch {
    return fallback;
  }
}

async function post(path: string, body: unknown, headers: HeadersInit = {}): Promise<Response> {
  return fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(60_000),
  });
}

export async function loadRecord(token: string): Promise<OwnerRecord> {
  const r = await post("/ops/owner/record", { token });
  if (!r.ok) throw new Error(await detail(r, `record unavailable (${r.status})`));
  return r.json();
}

export async function loadRecordChip(token: string, kind: "pre" | "post"): Promise<string | null> {
  const r = await post("/ops/owner/chip", { token, kind });
  if (!r.ok) return null;
  return URL.createObjectURL(await r.blob());
}

/** POST, so the address someone types never sits in a URL an access log keeps. */
export async function lookup(area: string, q: string): Promise<LookupAnswer> {
  const r = await post("/ops/lookup", { area, q });
  if (r.status === 429) throw new Error("Too many checks from this connection. Wait a minute and try again.");
  if (!r.ok) throw new Error(await detail(r, `check failed (${r.status})`));
  return r.json();
}

export interface OwnerLink {
  token: string;
  id: string;
  expires_utc: string;
  days: number;
  path: string;
}

/** Responder only: issue a record link for one building. */
export async function issueOwnerLink(
  area: string,
  ncr_id: string,
  days: number,
  auth: HeadersInit,
): Promise<OwnerLink> {
  const r = await post("/ops/owner/links", { area, ncr_id, days }, auth);
  if (!r.ok) {
    if (r.status === 401 || r.status === 403) throw new Error("Responder token required to create owner links");
    throw new Error(await detail(r, `link not created (${r.status})`));
  }
  return r.json();
}

export async function revokeOwnerLink(id: string, auth: HeadersInit): Promise<void> {
  const r = await post("/ops/owner/links/revoke", { id }, auth);
  if (!r.ok) throw new Error(await detail(r, `link not withdrawn (${r.status})`));
}

/** The full link a partner sends to an owner: this app's address plus the fragment. */
export function recordUrl(path: string): string {
  return `${window.location.origin}${window.location.pathname}${path}`;
}

export interface IndexLevel {
  label: string;
  expected: number;
  range_80: [number, number];
  most_likely: number | null;
}

export interface IndexRecord {
  schema: string;
  area: string;
  name: string;
  status: string;
  event: { id: string; name: string; declarations: string[]; incident_begin: string | null };
  state: string;
  county: string | null;
  hazards: string[];
  assessed_utc: string | null;
  imagery: { before: string | null; after: string | null };
  buildings: { assessed: number; not_assessed: number | null; needs_review: number | null };
  damage: Record<string, IndexLevel>;
  major_or_destroyed: { expected: number; range_80: [number, number] };
  access: {
    road_segments_blocked: number | null;
    road_segments_debris_possible: number | null;
    bridges_unverified: number | null;
    people_cut_off: { known_blocks: number | null; if_debris_blocks_roads: number | null };
  } | null;
  debris_cubic_yards: { low: number; high: number } | null;
  building_loss_usd: { low: number; high: number } | null;
  validation: string;
  method: string;
  disclaimer: string;
}

export async function loadIndex(): Promise<{ areas: { area: string }[] }> {
  const r = await fetch(`${API_URL}/ops/index`, { signal: AbortSignal.timeout(30_000) });
  if (!r.ok) throw new Error(await detail(r, `index unavailable (${r.status})`));
  return r.json();
}

export async function loadIndexRecord(area: string): Promise<IndexRecord> {
  const r = await fetch(`${API_URL}/ops/index/${encodeURIComponent(area)}`, { signal: AbortSignal.timeout(30_000) });
  if (!r.ok) throw new Error(await detail(r, `index unavailable (${r.status})`));
  return r.json();
}

export const indexUrl = (area?: string) => `${API_URL}/ops/index${area ? `/${encodeURIComponent(area)}` : ""}`;

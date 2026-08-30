import type { EventConfig, HazardType } from "./types";

/** Load the offline event registry written by `run.py events registry`. */
export async function loadEvents(): Promise<EventConfig[]> {
  const res = await fetch(`${import.meta.env.BASE_URL}data/events.json`);
  if (!res.ok) throw new Error(`failed to load events.json: ${res.status}`);
  const raw = (await res.json()) as EventConfig[];
  // keep only events that actually have at least one ingested area
  return raw.filter((e) => e.areas && e.areas.length > 0);
}

export const HAZARD_LABEL: Record<HazardType, string> = {
  hurricane: "Hurricane",
  cyclone: "Cyclone",
  wildfire: "Wildfire",
  flood: "Flood",
  earthquake: "Earthquake",
  tornado: "Tornado",
  volcano: "Volcanic",
  landslide: "Landslide",
  tsunami: "Tsunami",
  other: "Disaster",
};

export const eventById = (events: EventConfig[], id: string) =>
  events.find((e) => e.id === id) ?? events[0] ?? null;

export function areaRef(events: EventConfig[], eventId: string, areaId: string) {
  const ev = eventById(events, eventId);
  if (!ev) return null;
  return ev.areas.find((a) => a.id === areaId) ?? ev.areas[0] ?? null;
}

export const firstAreaOf = (ev: EventConfig | null) => ev?.areas[0] ?? null;

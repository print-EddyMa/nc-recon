import type { EventConfig, HazardType } from "./types";

/**
 * The NC event registry written by `run.py events registry`, the list of North
 * Carolina areas that have actually been assessed by the pipeline. It ships
 * empty; entries appear as areas are assessed (locally or via the hosted
 * service). Nothing is pre-baked.
 */
export async function loadEvents(): Promise<EventConfig[]> {
  const res = await fetch(`${import.meta.env.BASE_URL}data/events.json`);
  if (!res.ok) throw new Error(`failed to load events.json: ${res.status}`);
  const raw = (await res.json()) as EventConfig[];
  return (Array.isArray(raw) ? raw : []).filter((e) => e.areas && e.areas.length > 0);
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

/** Find the event + area for an assessed-area id, scanning the flat registry. */
export function areaLookup(
  events: EventConfig[],
  areaId: string,
): { event: EventConfig; area: EventConfig["areas"][number] } | null {
  for (const event of events) {
    const area = event.areas.find((a) => a.id === areaId);
    if (area) return { event, area };
  }
  return null;
}

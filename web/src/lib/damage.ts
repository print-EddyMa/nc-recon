import type { DamageClass } from "./types";

export interface DamageMeta {
  index: DamageClass;
  key: string;
  label: string;
  short: string;
  hex: string;
  rgb: [number, number, number];
  /** relative extrusion height in metres for the 3D view */
  height: number;
  blurb: string;
}

export const DAMAGE: DamageMeta[] = [
  {
    index: 0,
    key: "no-damage",
    label: "No damage",
    short: "None",
    // a cool green anchor so any damage reads instantly against it
    hex: "#3fa06d",
    rgb: [63, 160, 109],
    height: 5,
    blurb: "Structure intact, no visible envelope or roof compromise.",
  },
  {
    index: 1,
    key: "minor-damage",
    label: "Minor damage",
    short: "Minor",
    hex: "#efb036",
    rgb: [239, 176, 54],
    height: 14,
    blurb: "Partial roof loss, surrounding debris, water at the structure.",
  },
  {
    index: 2,
    key: "major-damage",
    label: "Major damage",
    short: "Major",
    hex: "#e56a2b",
    rgb: [229, 106, 43],
    height: 26,
    blurb: "Partial collapse, significant structural failure, burn-through.",
  },
  {
    index: 3,
    key: "destroyed",
    label: "Destroyed",
    short: "Destroyed",
    hex: "#a81b38",
    rgb: [168, 27, 56],
    height: 40,
    blurb: "Structure no longer standing or scoured from its foundation.",
  },
];

export const damageOf = (c: DamageClass) => DAMAGE[c];

/** severe = major + destroyed, the headline number */
export const isSevere = (c: DamageClass) => c >= 2;

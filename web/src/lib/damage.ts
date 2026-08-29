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
    hex: "#f5d76e",
    rgb: [245, 215, 110],
    height: 6,
    blurb: "Structure intact, no visible envelope or roof compromise.",
  },
  {
    index: 1,
    key: "minor-damage",
    label: "Minor damage",
    short: "Minor",
    hex: "#e8894a",
    rgb: [232, 137, 74],
    height: 14,
    blurb: "Partial roof loss, surrounding debris, water at the structure.",
  },
  {
    index: 2,
    key: "major-damage",
    label: "Major damage",
    short: "Major",
    hex: "#d1495b",
    rgb: [209, 73, 91],
    height: 26,
    blurb: "Partial collapse, significant structural failure, burn-through.",
  },
  {
    index: 3,
    key: "destroyed",
    label: "Destroyed",
    short: "Destroyed",
    hex: "#8b1e3f",
    rgb: [139, 30, 63],
    height: 40,
    blurb: "Structure no longer standing or scoured from its foundation.",
  },
];

export const damageOf = (c: DamageClass) => DAMAGE[c];

/** severe = major + destroyed, the headline number */
export const isSevere = (c: DamageClass) => c >= 2;

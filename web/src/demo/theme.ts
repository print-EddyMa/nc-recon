/** Phase H — the demo is fixed-dark; these are the app tokens (index.css dark
 * block) inlined so the sequence never depends on the runtime theme. */
export const C = {
  bg: "#0F1115",
  surface: "#17191E",
  line: "#2A2E36",
  ink: "#E9EAE8",
  inkDim: "#9EA1A8",
  inkFaint: "#6C7079",
  accent: "#4A80F6",
  accentRGB: [74, 128, 246] as [number, number, number],
};

/** NC live-severity ramp (DESIGN.md — cooler than the damage ramp) */
export const SEV: Record<number, [number, number, number]> = {
  [-1]: [90, 103, 115],
  0: [90, 124, 134],
  1: [245, 215, 110],
  2: [232, 137, 74],
  3: [209, 73, 91],
};

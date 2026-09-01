import type { HazardType } from "../lib/types";

/**
 * One consistent line-icon per hazard family, replaces the emoji glyphs.
 * All 16×16, 1.5px stroke, no fill, currentColor. Deliberately schematic
 * (map-legend register) rather than illustrative.
 */
export default function HazardIcon({
  hazard,
  size = 14,
  className,
}: {
  hazard: HazardType | "fire" | string;
  size?: number;
  className?: string;
}) {
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 16 16",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.5,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    className,
    "aria-hidden": true,
  };
  switch (hazard) {
    case "earthquake":
      return (
        <svg {...common}>
          <path d="M1 8h3l2-4 3 8 2-5 1 3h3" />
        </svg>
      );
    case "hurricane":
    case "cyclone":
      return (
        <svg {...common}>
          <path d="M8 8c0-2 1.6-3.2 3.4-3.2C13 4.8 14 6 14 7.6 14 10.8 11.2 13 7.6 13 4.4 13 2 10.6 2 7 2 3.7 4.7 2 8 2" />
          <circle cx="8" cy="8" r="1.1" fill="currentColor" stroke="none" />
        </svg>
      );
    case "wildfire":
    case "fire":
      return (
        <svg {...common}>
          <path d="M8 14c2.5 0 4-1.7 4-3.8 0-2.4-2-3.5-2-6C7 6 6 7 6 8.6 5.2 8 5 7 5 6c-1 1.2-1 2.6-1 4.2C4 12.3 5.5 14 8 14Z" />
        </svg>
      );
    case "flood":
    case "tsunami":
      return (
        <svg {...common}>
          <path d="M1 6c1.6 0 1.6 1.5 3.2 1.5S5.8 6 7.4 6 9 7.5 10.6 7.5 12.2 6 13.8 6 15 7 15 7" />
          <path d="M1 10c1.6 0 1.6 1.5 3.2 1.5S5.8 10 7.4 10 9 11.5 10.6 11.5 12.2 10 13.8 10 15 11 15 11" />
        </svg>
      );
    case "volcano":
      return (
        <svg {...common}>
          <path d="M2 14h12l-3.5-6h-5L2 14Z" />
          <path d="M8 8V5M8 3.5V2M10.5 5l1-1M5.5 5l-1-1" />
        </svg>
      );
    case "tornado":
      return (
        <svg {...common}>
          <path d="M2 3h12M3 6h10M4.5 9h7M6.5 12h4M8 14.5h1.5" />
        </svg>
      );
    case "landslide":
      return (
        <svg {...common}>
          <path d="M1 13h14M2 13 9 4l4 4" />
          <circle cx="11.5" cy="11" r="1" fill="currentColor" stroke="none" />
          <circle cx="6" cy="12" r="0.8" fill="currentColor" stroke="none" />
        </svg>
      );
    default:
      return (
        <svg {...common}>
          <path d="M8 2 14 13H2L8 2Z" />
          <path d="M8 6.5v3.5M8 11.6v.4" />
        </svg>
      );
  }
}

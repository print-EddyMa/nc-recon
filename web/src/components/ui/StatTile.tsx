import type { ReactNode } from "react";
import { cn } from "../../lib/utils";

type Tone = "neutral" | "accent" | "warn" | "severe";

const TONE: Record<Tone, string> = {
  neutral: "text-ink",
  accent: "text-accent",
  warn: "text-dmg1",
  severe: "text-dmg2",
};

/**
 * Compact stat card for the dashboards, a monospace headline figure over a
 * cartographic caption, with an optional supporting line. Deliberately flat
 * (no card chrome of its own): drop it inside a `.panel`, or a `<div>` grid.
 * Pattern lifted from the 21st.dev "stat card for a damage-summary dashboard"
 * search, restyled to the app's tokens.
 */
export default function StatTile({
  label,
  value,
  sub,
  tone = "neutral",
  align = "left",
  className,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: Tone;
  align?: "left" | "center";
  className?: string;
}) {
  return (
    <div className={cn(align === "center" && "text-center", className)}>
      <div className="mb-1 text-xs font-medium text-ink-dim">{label}</div>
      <div className={cn("tnum text-2xl font-semibold leading-none", TONE[tone])}>{value}</div>
      {sub != null && <div className="mt-1.5 text-2xs leading-relaxed text-ink-faint">{sub}</div>}
    </div>
  );
}

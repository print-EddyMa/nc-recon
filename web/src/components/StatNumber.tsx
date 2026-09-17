import { useCountUp } from "../lib/useCountUp";

interface Props {
  /** a number, or a string. Non-numeric strings ("off", "…") render verbatim. */
  value: number | string;
  className?: string;
  /** animation length in ms; 0 disables the count-up */
  ms?: number;
  /** decimal places to hold while counting (e.g. a percentage) */
  decimals?: number;
}

const NUMERIC = /^-?\d+(\.\d+)?$/;

/** A stat figure that counts up to its value on first paint. Used only for the
 * headline numbers on Home / Summary / Review - see DESIGN.md § Motion. */
export default function StatNumber({ value, className, ms = 600, decimals = 0 }: Props) {
  const raw =
    typeof value === "number"
      ? value
      : NUMERIC.test(value.trim())
        ? parseFloat(value)
        : null;
  const n = useCountUp(raw ?? 0, ms);
  if (raw == null) return <span className={className}>{value}</span>;
  const text = decimals > 0 ? n.toFixed(decimals) : Math.round(n).toLocaleString();
  return <span className={className}>{text}</span>;
}

// Class-name helpers shared by the kit and by markup that needs a button
// look on a non-button element (a link, a popover trigger).
export const cx = (...a: (string | false | null | undefined)[]) => a.filter(Boolean).join(" ");

export type Variant = "primary" | "secondary" | "ghost" | "danger";
const VARIANT: Record<Variant, string> = {
  primary:
    "bg-accent text-accent-ink border-accent hover:bg-accent/90 font-semibold",
  secondary:
    "bg-surface text-ink border-line-strong hover:bg-surface-2 hover:border-ink-faint",
  ghost: "bg-transparent text-ink-dim border-transparent hover:bg-surface-2 hover:text-ink",
  danger: "bg-surface text-st-bad border-line-strong hover:bg-st-bad/10 hover:border-st-bad",
};

export const btnClass = (variant: Variant = "secondary", size: "sm" | "md" = "md", extra = "") =>
  cx(
    "pressable inline-flex shrink-0 items-center justify-center gap-1.5 whitespace-nowrap rounded border",
    "disabled:pointer-events-none disabled:opacity-45",
    size === "sm" ? "h-7 px-2.5 text-[13px]" : "h-8 px-3 text-sm font-medium",
    VARIANT[variant],
    extra,
  );


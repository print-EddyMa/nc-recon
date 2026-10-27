/* Hallmark · component kit: Groma operations console
 * states: default · hover · focus · active · disabled · loading
 * Every control shares one height scale (28 / 32 px), one radius (6 px) and
 * one focus ring (2 px accent, instant). Colours come only from tokens. */
import {
  forwardRef,
  useEffect,
  useId,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type ReactNode,
} from "react";
import { FEMA, FEMA_HEX, FEMA_LABEL, type FemaClass } from "../../lib/ops";
import { btnClass, cx, type Variant } from "./classes";


// --------------------------------------------------------------------------- //
// buttons
// --------------------------------------------------------------------------- //
export const Button = forwardRef<
  HTMLButtonElement,
  ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: Variant;
    size?: "sm" | "md";
    icon?: ReactNode;
    kbd?: string;
    busy?: boolean;
  }
>(function Button({ variant = "secondary", size = "md", icon, kbd, busy, className, children, ...rest }, ref) {
  return (
    <button ref={ref} className={btnClass(variant, size, className)} aria-busy={busy || undefined} {...rest}>
      {busy ? <Spinner /> : icon}
      {children}
      {kbd && <Kbd className="ml-1">{kbd}</Kbd>}
    </button>
  );
});

export function Spinner({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={cx("h-3.5 w-3.5 animate-spin", className)} aria-hidden>
      <circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2" />
      <path d="M14 8a6 6 0 00-6-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function Kbd({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <kbd
      className={cx(
        "inline-grid min-w-[1.25rem] place-items-center rounded-sm border border-line-strong bg-surface-2 px-1",
        "font-mono text-[11px] font-medium leading-[1.1rem] text-ink-dim",
        className,
      )}
    >
      {children}
    </kbd>
  );
}

// --------------------------------------------------------------------------- //
// tags and status
// --------------------------------------------------------------------------- //
export function Tag({
  children,
  tone = "neutral",
  title,
  className,
}: {
  children: ReactNode;
  tone?: "neutral" | "accent" | "ok" | "warn" | "bad" | "review";
  title?: string;
  className?: string;
}) {
  const t = {
    neutral: "border-line-strong text-ink-dim",
    accent: "border-accent/50 bg-accent-soft text-accent",
    ok: "border-st-ok/40 bg-st-ok/10 text-st-ok",
    warn: "border-st-warn/40 bg-st-warn/10 text-st-warn",
    bad: "border-st-bad/40 bg-st-bad/10 text-st-bad",
    review: "border-review/50 bg-review/10 text-review",
  }[tone];
  return (
    <span
      title={title}
      className={cx(
        "inline-flex h-5 items-center gap-1 whitespace-nowrap rounded-sm border px-1.5 text-[11px] font-semibold tracking-wide",
        t,
        className,
      )}
    >
      {children}
    </span>
  );
}

export type Status = "ok" | "warn" | "bad" | "unknown";
const DOT: Record<Status, string> = {
  ok: "bg-st-ok",
  warn: "bg-st-warn",
  bad: "bg-st-bad",
  unknown: "bg-st-unknown",
};
export function Dot({ status, pulse }: { status: Status; pulse?: boolean }) {
  return (
    <span className="relative inline-flex h-2 w-2 shrink-0" aria-hidden>
      {pulse && <span className={cx("absolute inset-0 animate-ping rounded-full opacity-60", DOT[status])} />}
      <span className={cx("relative h-2 w-2 rounded-full", DOT[status])} />
    </span>
  );
}

// --------------------------------------------------------------------------- //
// tabs and segmented control
// --------------------------------------------------------------------------- //
export function Tabs<T extends string>({
  value,
  onChange,
  items,
  label,
  className,
}: {
  value: T;
  onChange: (v: T) => void;
  items: { id: T; label: string; count?: number | null; hidden?: boolean }[];
  label: string;
  className?: string;
}) {
  const shown = items.filter((i) => !i.hidden);
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  return (
    <div role="tablist" aria-label={label} className={cx("flex gap-0.5 overflow-x-auto border-b border-line [scrollbar-width:none]", className)}>
      {shown.map((it, i) => {
        const on = it.id === value;
        return (
          <button
            key={it.id}
            ref={(el) => {
              refs.current[i] = el;
            }}
            role="tab"
            aria-selected={on}
            tabIndex={on ? 0 : -1}
            onClick={() => onChange(it.id)}
            onKeyDown={(e) => {
              if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
              e.preventDefault();
              const n = (i + (e.key === "ArrowRight" ? 1 : shown.length - 1)) % shown.length;
              onChange(shown[n].id);
              refs.current[n]?.focus();
            }}
            className={cx(
              "relative -mb-px inline-flex h-9 shrink-0 items-center gap-1.5 whitespace-nowrap border-b-2 px-2 text-[13px]",
              on ? "border-accent font-semibold text-ink" : "border-transparent text-ink-dim hover:text-ink",
            )}
          >
            {it.label}
            {it.count != null && (
              <span
                className={cx(
                  "tnum rounded-sm px-1 font-mono text-[11px]",
                  on ? "bg-accent-soft text-accent" : "bg-surface-2 text-ink-faint",
                )}
              >
                {it.count.toLocaleString()}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

export function Segmented<T extends string>({
  value,
  onChange,
  items,
  label,
  size = "md",
}: {
  value: T;
  onChange: (v: T) => void;
  items: { id: T; label: ReactNode; title?: string }[];
  label: string;
  size?: "sm" | "md";
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded border border-line-strong bg-surface-2 p-0.5">
      {items.map((it) => (
        <button
          key={it.id}
          onClick={() => onChange(it.id)}
          aria-pressed={value === it.id}
          title={it.title}
          className={cx(
            "pressable inline-flex items-center justify-center gap-1 rounded-sm px-2.5",
            size === "sm" ? "h-6 text-[12px]" : "h-7 text-[13px]",
            value === it.id ? "bg-surface font-semibold text-ink shadow-1" : "text-ink-dim hover:text-ink",
          )}
        >
          {it.label}
        </button>
      ))}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// disclosure, popover, empty state
// --------------------------------------------------------------------------- //
export function Disclosure({
  title,
  meta,
  children,
  defaultOpen,
  onToggle,
}: {
  title: ReactNode;
  meta?: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  onToggle?: (open: boolean) => void;
}) {
  return (
    <details
      open={defaultOpen}
      className="group border-b border-line"
      onToggle={(e) => onToggle?.((e.target as HTMLDetailsElement).open)}
    >
      <summary className="flex cursor-pointer list-none items-center gap-2 py-2.5 text-sm font-semibold text-ink [&::-webkit-details-marker]:hidden">
        <Icon name="chevron" className="h-3.5 w-3.5 text-ink-faint transition-transform group-open:rotate-90" />
        <span className="flex-1">{title}</span>
        {meta && <span className="text-xs font-normal text-ink-faint">{meta}</span>}
      </summary>
      <div className="pb-3 pl-5">{children}</div>
    </details>
  );
}

/** A small anchored panel: opens on click, closes on outside click or Esc,
 * returns focus to its trigger. */
export function Popover({
  trigger,
  children,
  align = "end",
  label,
}: {
  trigger: (p: { open: boolean; toggle: () => void; id: string }) => ReactNode;
  children: ReactNode | ((close: () => void) => ReactNode);
  align?: "start" | "end";
  label: string;
}) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);
  const close = () => setOpen(false);
  return (
    <div ref={box} className="relative">
      {trigger({ open, toggle: () => setOpen((v) => !v), id })}
      {open && (
        <div
          id={id}
          role="dialog"
          aria-label={label}
          className={cx(
            "panel absolute top-[calc(100%+6px)] z-40 w-80 max-w-[calc(100vw-24px)] p-3",
            align === "end" ? "right-0" : "left-0",
          )}
        >
          {typeof children === "function" ? children(close) : children}
        </div>
      )}
    </div>
  );
}

export function Empty({
  icon = "map",
  title,
  children,
  action,
}: {
  icon?: IconName;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-start gap-2 rounded border border-dashed border-line-strong p-4">
      <Icon name={icon} className="h-5 w-5 text-ink-faint" />
      <div className="text-sm font-semibold text-ink">{title}</div>
      {children && <div className="text-sm leading-relaxed text-ink-dim">{children}</div>}
      {action}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// data marks
// --------------------------------------------------------------------------- //
/** Expected structures per FEMA level as one stacked strip. Zero-width
 * segments are dropped; a 1 px surface gap separates neighbours. */
export function DamageStrip({
  counts,
  height = 6,
  className,
  label,
}: {
  counts: Partial<Record<FemaClass, number>>;
  height?: number;
  className?: string;
  label?: string;
}) {
  const total = FEMA.reduce((t, c) => t + (counts[c] ?? 0), 0) || 1;
  return (
    <div
      className={cx("flex w-full overflow-hidden rounded-sm bg-surface-2", className)}
      style={{ height }}
      role="img"
      aria-label={
        label ??
        FEMA.map((c) => `${FEMA_LABEL[c]} ${Math.round(counts[c] ?? 0)}`).join(", ")
      }
    >
      {FEMA.map((c) => {
        const w = ((counts[c] ?? 0) / total) * 100;
        return w > 0 ? (
          <span
            key={c}
            style={{ width: `${w}%`, background: FEMA_HEX[c], boxShadow: "1px 0 0 rgb(var(--surface))" }}
          />
        ) : null;
      })}
    </div>
  );
}

export function Swatch({ c, className }: { c: FemaClass | "none"; className?: string }) {
  return (
    <span
      className={cx("inline-block h-2.5 w-2.5 shrink-0 rounded-[2px] ring-1 ring-inset ring-black/15", className)}
      style={{ background: c === "none" ? "#555555" : FEMA_HEX[c] }}
      aria-hidden
    />
  );
}

/** A figure with its uncertainty: the number first, the range beside it. */
export function Figure({
  value,
  range,
  unit,
  label,
  big,
}: {
  value: string;
  range?: string | null;
  unit?: string;
  label: string;
  big?: boolean;
}) {
  return (
    <div>
      <div className="text-xs font-medium text-ink-dim">{label}</div>
      <div className="flex items-baseline gap-1.5">
        <span className={cx("tnum font-mono font-semibold text-ink", big ? "text-[28px] leading-8" : "text-lg")}>
          {value}
        </span>
        {unit && <span className="text-sm text-ink-dim">{unit}</span>}
      </div>
      {range && <div className="tnum font-mono text-xs text-ink-faint">80% range {range}</div>}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// icons: hand-drawn, 16 px grid, 1.5 stroke, currentColor
// --------------------------------------------------------------------------- //
const PATHS = {
  map: "M2 4l4-1.5 4 1.5 4-1.5v9.5L10 13.5 6 12 2 13.5zM6 2.5V12M10 4v9.5",
  layers: "M8 2l6 3-6 3-6-3zM2 8l6 3 6-3M2 11l6 3 6-3",
  check: "M3 8.5l3 3 7-7",
  alert: "M8 2l6.5 11.5h-13zM8 6.5v3M8 11.6v.1",
  users: "M5.5 7.5a2.25 2.25 0 100-4.5 2.25 2.25 0 000 4.5zM1.5 13.5c.4-2.3 2-3.5 4-3.5s3.6 1.2 4 3.5M11 7a2 2 0 100-4M12.2 10.2c1.3.4 2.1 1.5 2.3 3.3",
  download: "M8 2.5v8M4.5 7.5L8 11l3.5-3.5M2.5 13.5h11",
  file: "M4 1.5h5l3.5 3.5v9.5h-8.5zM9 1.5V5h3.5M6 8.5h4M6 11h4",
  refresh: "M13 3.5v3h-3M3 12.5v-3h3M12.4 6.5A5 5 0 003.6 5M3.6 9.5a5 5 0 008.8 1.5",
  trash: "M2.5 4h11M6 4V2.5h4V4M4 4l.7 9.5h6.6L12 4",
  key: "M10 7.5a3 3 0 10-2.9-2.2L2 10.5V13h2.5v-1.5H6V10h1.5l.6-.6A3 3 0 0010 7.5zM10.75 4.75v.01",
  sliders: "M2.5 4h7M12.5 4h1M2.5 8h2M7.5 8h6M2.5 12h8M13 12h.5M11 2.5v3M5.5 6.5v3M11.5 10.5v3",
  search: "M7 12a5 5 0 100-10 5 5 0 000 10zM10.5 10.5L14 14",
  plus: "M8 3v10M3 8h10",
  x: "M4 4l8 8M12 4l-8 8",
  chevron: "M6 3.5L10.5 8 6 12.5",
  arrowLeft: "M13 8H3M7 4L3 8l4 4",
  eye: "M1.5 8S4 3.5 8 3.5 14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8zM8 10a2 2 0 100-4 2 2 0 000 4z",
  compare: "M8 1.5v13M2.5 3.5h3.5v9H2.5zM10 3.5h3.5v9H10",
  target: "M8 14a6 6 0 100-12 6 6 0 000 12zM8 11a3 3 0 100-6 3 3 0 000 6zM8 0.5v3M8 12.5v3M0.5 8h3M12.5 8h3",
  route: "M3.5 12.5a1.5 1.5 0 100-3 1.5 1.5 0 000 3zM12.5 6.5a1.5 1.5 0 100-3 1.5 1.5 0 000 3zM5 11h4.5a2 2 0 000-4h-3a2 2 0 010-4H11",
  signal: "M8 9.5a1 1 0 100-2 1 1 0 000 2zM5.2 11.3a4 4 0 010-5.6M10.8 5.7a4 4 0 010 5.6M3 13.5a7 7 0 010-10M13 3.5a7 7 0 010 10",
  info: "M8 14.5a6.5 6.5 0 100-13 6.5 6.5 0 000 13zM8 7.5V11M8 5v.1",
  shield: "M8 1.5l5.5 2v4c0 3.3-2.3 5.8-5.5 7-3.2-1.2-5.5-3.7-5.5-7v-4z",
  clock: "M8 14.5a6.5 6.5 0 100-13 6.5 6.5 0 000 13zM8 4.5V8l2.5 1.5",
  pin: "M8 14.5s4.5-4.2 4.5-8a4.5 4.5 0 00-9 0c0 3.8 4.5 8 4.5 8zM8 8a1.5 1.5 0 100-3 1.5 1.5 0 000 3z",
  external: "M9.5 2.5h4v4M13.5 2.5L7.5 8.5M12 9.5v4h-9.5V4h4",
  book: "M2.5 3c2-.6 3.8-.4 5.5.8v10c-1.7-1.2-3.5-1.4-5.5-.8zM13.5 3c-2-.6-3.8-.4-5.5.8v10c1.7-1.2 3.5-1.4 5.5-.8z",
  more: "M3.5 8h.01M8 8h.01M12.5 8h.01",
} as const;
export type IconName = keyof typeof PATHS;

export function Icon({ name, className }: { name: IconName; className?: string }) {
  const round = name === "more";
  return (
    <svg viewBox="0 0 16 16" className={cx("h-4 w-4 shrink-0", className)} fill="none" aria-hidden>
      <path
        d={PATHS[name]}
        stroke="currentColor"
        strokeWidth={round ? 2.5 : 1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

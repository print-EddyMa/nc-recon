import type { ReactNode } from "react";
import { cn } from "../../lib/utils";

export interface RankedItem {
  id: string;
  primary: ReactNode;
  secondary?: ReactNode;
  /** css color for the leading severity dot */
  dot?: string;
  /** …or a utility class (e.g. "bg-dmg1"); takes precedence over `dot` */
  dotClassName?: string;
  trailing?: ReactNode;
  title?: string;
  onSelect?: () => void;
}

/**
 * A ranked, scannable list, severity dot, two lines of text, an optional
 * trailing figure, one click target that usually flies the map to the item.
 * Shared by the Live Monitor ("active now") and the NC dashboard (flood
 * forecast / alerts / ground-truth). `<ol>` so order reads as rank.
 */
export default function RankedList({
  items,
  empty,
  as = "ol",
}: {
  items: RankedItem[];
  empty?: ReactNode;
  as?: "ol" | "ul";
}) {
  const List = as;
  if (!items.length) {
    return empty ? <p className="text-2xs text-ink-faint">{empty}</p> : null;
  }
  return (
    <List className="space-y-0.5">
      {items.map((it) => {
        const inner = (
          <>
            {(it.dot || it.dotClassName) && (
              <span
                className={cn("mt-1 h-2 w-2 shrink-0 rounded-full", it.dotClassName)}
                style={it.dotClassName ? undefined : { background: it.dot }}
              />
            )}
            <span className="min-w-0 flex-1">
              <span className="block truncate text-xs text-ink">{it.primary}</span>
              {it.secondary != null && (
                <span className="tnum block truncate text-2xs text-ink-faint">{it.secondary}</span>
              )}
            </span>
            {it.trailing != null && (
              <span className="tnum shrink-0 self-center text-2xs text-ink-faint">{it.trailing}</span>
            )}
          </>
        );
        return (
          <li key={it.id}>
            {it.onSelect ? (
              <button
                onClick={it.onSelect}
                title={it.title}
                className="pressable flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left hover:bg-surface-2"
              >
                {inner}
              </button>
            ) : (
              <div className="flex items-start gap-2 px-2 py-1.5" title={it.title}>
                {inner}
              </div>
            )}
          </li>
        );
      })}
    </List>
  );
}

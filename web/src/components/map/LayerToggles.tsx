import { cn } from "../../lib/utils";

export interface LayerRow {
  id: string;
  label: string;
  /** trailing eyebrow chip, e.g. a phase tag "E2" */
  chip?: string;
  /** the count · source line under the label */
  meta: string;
  /** legend swatch colour before the label */
  dotColor?: string;
  checked: boolean;
  disabled?: boolean;
  /** hover title / a11y hint when disabled */
  reason?: string;
  onToggle: () => void;
}

/**
 * The map dashboards' left-hand layer switchboard: a checkbox, a colour
 * swatch, the layer name, and a monospace "N · source" status line. Disabled
 * rows dim and carry their reason as a tooltip. Shared by the Live Monitor and
 * the NC risk dashboard.
 */
export default function LayerToggles({ rows }: { rows: LayerRow[] }) {
  return (
    <ul className="space-y-2 text-xs">
      {rows.map((r) => (
        <li key={r.id}>
          <label
            className={cn("flex items-start gap-2", r.disabled ? "opacity-45" : "cursor-pointer")}
            title={r.reason ?? undefined}
          >
            <input
              type="checkbox"
              className="mt-0.5 accent-accent"
              checked={r.checked && !r.disabled}
              disabled={r.disabled}
              onChange={r.onToggle}
            />
            <span className="min-w-0">
              <span className="flex items-center gap-1.5 text-ink">
                {r.dotColor && (
                  <span
                    className="h-2 w-2 shrink-0 rounded-full"
                    style={{ background: r.dotColor }}
                  />
                )}
                {r.label}
              </span>
              <span className="block text-2xs text-ink-faint">{r.meta}</span>
            </span>
          </label>
        </li>
      ))}
    </ul>
  );
}

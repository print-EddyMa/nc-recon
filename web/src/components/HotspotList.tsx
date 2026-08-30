import type { Hotspot } from "../lib/data";

interface Props {
  items: Hotspot[];
  activeKey: string | null;
  onPick: (h: Hotspot) => void;
}

export default function HotspotList({ items, activeKey, onPick }: Props) {
  if (!items.length) {
    return <p className="px-1 py-2 text-xs text-ink-faint">No clustered damage in this area.</p>;
  }
  const max = items[0].score || 1;

  return (
    <ol className="stagger space-y-0.5">
      {items.map((h, i) => {
        const active = h.key === activeKey;
        return (
          <li key={h.key}>
            <button
              onClick={() => onPick(h)}
              aria-pressed={active}
              className={`pressable group flex w-full items-center gap-3 rounded-md px-2.5 py-2 text-left ${
                active ? "bg-surface-2" : "hover:bg-surface-2"
              }`}
            >
              <span className="tnum w-5 shrink-0 text-center text-sm text-ink-faint">{i + 1}</span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm text-ink">{h.label}</span>
                <span className="tnum block text-2xs text-ink-dim">
                  {h.count} buildings · {h.severe} severe
                </span>
                {/* score bar is a neutral meter — red is reserved for the damage ramp */}
                <span className="mt-1.5 block h-[3px] w-full overflow-hidden rounded-full bg-line">
                  <span
                    className="block h-full bg-meter transition-[width] duration-500 ease-out"
                    style={{ width: `${(h.score / max) * 100}%` }}
                  />
                </span>
              </span>
              <svg
                width="10"
                height="10"
                viewBox="0 0 12 12"
                fill="none"
                aria-hidden
                className="shrink-0 text-ink-faint transition-transform duration-200 ease-out group-hover:translate-x-0.5"
              >
                <path d="M4 2l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

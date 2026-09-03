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

  return (
    <ol className="stagger -mx-1">
      {items.map((h, i) => {
        const active = h.key === activeKey;
        const sevPct = h.count ? Math.round((h.severe / h.count) * 100) : 0;
        return (
          <li key={h.key}>
            <button
              onClick={() => onPick(h)}
              aria-pressed={active}
              className={`pressable flex w-full items-center gap-3 rounded-md px-2.5 py-2 text-left ${
                active ? "bg-surface-2" : "hover:bg-surface-2"
              }`}
            >
              <span className="tnum w-4 shrink-0 text-center text-sm font-medium text-ink-faint">
                {i + 1}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm text-ink">{h.label}</span>
                <span className="tnum block text-2xs text-ink-dim">
                  {h.count} buildings · {sevPct}% severe
                </span>
              </span>
              <span className="tnum shrink-0 rounded-sm bg-surface-2 px-1.5 py-0.5 text-2xs font-semibold text-dmg2">
                {h.severe} severe
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

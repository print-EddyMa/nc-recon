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
    <ol className="space-y-1">
      {items.map((h, i) => {
        const active = h.key === activeKey;
        return (
          <li key={h.key}>
            <button
              onClick={() => onPick(h)}
              className={`group flex w-full items-center gap-3 rounded-sm border px-2.5 py-2 text-left transition-colors ${
                active
                  ? "border-accent bg-surface-2"
                  : "border-transparent hover:border-line hover:bg-surface-2"
              }`}
            >
              <span className="tnum w-5 text-center text-sm text-ink-faint">{i + 1}</span>
              <span className="flex-1">
                <span className="block text-sm text-ink">{h.label}</span>
                <span className="tnum block text-2xs text-ink-dim">
                  {h.count} buildings · {h.severe} severe
                </span>
                <span className="mt-1 block h-1 w-full overflow-hidden rounded-full bg-line">
                  <span
                    className="block h-full bg-dmg2"
                    style={{ width: `${(h.score / max) * 100}%` }}
                  />
                </span>
              </span>
              <span
                aria-hidden
                className="text-ink-faint transition-transform group-hover:translate-x-0.5"
              >
                ›
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

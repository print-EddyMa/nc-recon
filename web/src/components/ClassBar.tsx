import { DAMAGE } from "../lib/damage";
import type { DamageClass } from "../lib/types";

interface Props {
  counts: Record<DamageClass, number>;
  filter: Set<number>;
  onToggle: (c: number) => void;
  compact?: boolean;
}

export default function ClassBar({ counts, filter, onToggle, compact }: Props) {
  const total = (Object.values(counts) as number[]).reduce((a, b) => a + b, 0) || 1;

  return (
    <div>
      <div className="flex h-2.5 w-full overflow-hidden rounded-sm border border-line">
        {DAMAGE.map((d) => {
          const pct = (counts[d.index] / total) * 100;
          const on = filter.has(d.index);
          return (
            <div
              key={d.index}
              style={{ width: `${pct}%`, background: on ? d.hex : "transparent" }}
              className={`transition-opacity duration-300 ease-out ${on ? "" : "opacity-25"}`}
              title={`${d.label}: ${counts[d.index]}`}
            />
          );
        })}
      </div>
      {!compact && (
        <div className="mt-2.5 space-y-1">
          {DAMAGE.map((d) => {
            const on = filter.has(d.index);
            const pct = ((counts[d.index] / total) * 100).toFixed(0);
            return (
              <button
                key={d.index}
                onClick={() => onToggle(d.index)}
                aria-pressed={on}
                className={`flex w-full items-center gap-2 whitespace-nowrap text-left text-xs transition-opacity duration-200 ease-out active:opacity-60 ${
                  on ? "opacity-100" : "opacity-40"
                } hover:opacity-100`}
              >
                <span
                  className="h-2.5 w-2.5 shrink-0 rounded-[2px]"
                  style={{ background: d.hex }}
                />
                <span className="text-ink-dim">{d.label}</span>
                <span className="tnum ml-auto text-ink">{counts[d.index]}</span>
                <span className="tnum w-9 text-right text-ink-faint">{pct}%</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

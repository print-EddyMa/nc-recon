import { useId } from "react";

interface Props {
  value: number; // 0..1  (0 = imagery, 1 = 3-D assessment)
  onChange: (v: number) => void;
  imagery: "pre" | "post";
  onImageryChange: (k: "pre" | "post") => void;
  preDate?: string;
  postDate?: string;
}

/**
 * The signature control. One track drags the view from raw satellite imagery on
 * the left to the extruded 3-D damage model on the right; a segmented toggle
 * picks which capture the imagery half shows.
 */
export default function BeforeAfterSlider({
  value,
  onChange,
  imagery,
  onImageryChange,
  preDate,
  postDate,
}: Props) {
  const id = useId();
  const pct = Math.round(value * 100);

  return (
    <div className="panel px-4 py-3">
      <div className="mb-2 flex items-center justify-center gap-1.5">
        {(["pre", "post"] as const).map((k) => (
          <button
            key={k}
            onClick={() => onImageryChange(k)}
            aria-pressed={imagery === k}
            className={`tnum rounded-md px-2.5 py-1 text-2xs uppercase tracking-wider transition-colors duration-200 ease-out active:opacity-70 ${
              imagery === k ? "bg-accent text-[#05171a]" : "border border-line text-ink-dim hover:text-ink"
            }`}
          >
            {k === "pre" ? `Before${preDate ? " · " + preDate : ""}` : `After${postDate ? " · " + postDate : ""}`}
          </button>
        ))}
      </div>

      <input
        id={id}
        type="range"
        min={0}
        max={100}
        value={pct}
        onChange={(e) => onChange(Number(e.target.value) / 100)}
        aria-label="Blend from satellite imagery to 3-D damage assessment"
        className="ba-range w-full"
        style={{ ["--pct" as string]: `${pct}%` }}
      />

      <div className="mt-1.5 flex items-baseline justify-between text-2xs text-ink-faint">
        <span>Satellite</span>
        <span className="tnum text-ink-dim">{pct}%</span>
        <span>3-D damage model</span>
      </div>
    </div>
  );
}

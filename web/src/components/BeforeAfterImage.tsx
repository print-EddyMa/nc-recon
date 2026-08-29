import { useRef, useState } from "react";
import { heroTileUrl } from "../lib/data";
import type { AreaConfig } from "../lib/types";

interface Props {
  area: AreaConfig;
  preDate?: string;
  postDate?: string;
}

/** A wipe comparison of the pre- and post-storm Maxar tile over one block of
 * town. Drag the handle (or use the arrow keys) to sweep between them. */
export default function BeforeAfterImage({ area, preDate, postDate }: Props) {
  const [pos, setPos] = useState(52); // % from left showing "after"
  const boxRef = useRef<HTMLDivElement | null>(null);
  const dragging = useRef(false);

  const setFromClientX = (clientX: number) => {
    const el = boxRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    setPos(Math.max(2, Math.min(98, ((clientX - r.left) / r.width) * 100)));
  };

  return (
    <figure className="m-0">
      <div
        ref={boxRef}
        className="relative aspect-[4/3] w-full select-none overflow-hidden rounded-sm border border-line"
        onPointerDown={(e) => {
          dragging.current = true;
          (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
          setFromClientX(e.clientX);
        }}
        onPointerMove={(e) => dragging.current && setFromClientX(e.clientX)}
        onPointerUp={() => (dragging.current = false)}
      >
        {/* after (full) */}
        <img
          src={heroTileUrl(area.id, "post", area.hero)}
          alt={`${area.name} after Hurricane Helene`}
          className="absolute inset-0 h-full w-full object-cover"
          draggable={false}
        />
        {/* before (clipped to the left of the handle) */}
        <img
          src={heroTileUrl(area.id, "pre", area.hero)}
          alt={`${area.name} before Hurricane Helene`}
          className="absolute inset-0 h-full w-full object-cover"
          style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }}
          draggable={false}
        />

        <span className="pointer-events-none absolute left-3 top-3 rounded-[3px] bg-canvas/75 px-1.5 py-0.5 text-2xs uppercase tracking-wider text-ink-dim">
          Before{preDate ? ` · ${preDate}` : ""}
        </span>
        <span className="pointer-events-none absolute right-3 top-3 rounded-[3px] bg-canvas/75 px-1.5 py-0.5 text-2xs uppercase tracking-wider text-ink-dim">
          After{postDate ? ` · ${postDate}` : ""}
        </span>

        <div
          className="absolute inset-y-0 w-px bg-accent"
          style={{ left: `${pos}%` }}
          aria-hidden
        >
          <span className="absolute top-1/2 grid h-7 w-7 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border-2 border-accent bg-canvas text-accent">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
              <path d="M6 4L2 8l4 4M10 4l4 4-4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
        </div>

        <input
          type="range"
          min={2}
          max={98}
          value={pos}
          onChange={(e) => setPos(Number(e.target.value))}
          aria-label={`Wipe between ${area.name} before and after imagery`}
          className="absolute inset-0 h-full w-full cursor-ew-resize opacity-0"
        />
      </div>
      <figcaption className="mt-2 text-2xs text-ink-faint">
        {area.name}, NC — Maxar Open Data. Drag to compare.
      </figcaption>
    </figure>
  );
}

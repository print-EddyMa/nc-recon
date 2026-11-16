/* Before / after swipe: the before-event image on a second, pointer-transparent
 * map, synced to the main map's camera and clipped to the left of a divider
 * the analyst drags. Swipe is the comparison NASA Worldview defaults to, and
 * the fastest in controlled studies; it keeps the same ground under the eye
 * instead of asking the reader to match two pictures. */
import { useEffect, useRef, useState } from "react";
import { Map as MLMap } from "maplibre-gl";
import { imageryTileUrl, isOpsUrl, opsRequestHeaders } from "../../lib/ops";

export default function SwipeCompare({
  main,
  areaId,
  beforeLabel,
  afterLabel,
}: {
  /** the main map (after image + structures underneath) */
  main: MLMap;
  areaId: string;
  beforeLabel: string;
  afterLabel: string;
}) {
  const box = useRef<HTMLDivElement>(null);
  const holder = useRef<HTMLDivElement>(null);
  const [x, setX] = useState(50);
  const dragging = useRef(false);

  useEffect(() => {
    if (!holder.current) return;
    const m = new MLMap({
      container: holder.current,
      interactive: false,
      attributionControl: false,
      center: main.getCenter(),
      zoom: main.getZoom(),
      bearing: main.getBearing(),
      pitch: main.getPitch(),
      // responder-only tiles: the token goes in a header, never in the URL
      transformRequest: (url) => (isOpsUrl(url) ? { url, headers: opsRequestHeaders() } : { url }),
      style: {
        version: 8,
        sources: {
          pre: {
            type: "raster",
            tiles: [imageryTileUrl(areaId, "pre")],
            tileSize: 256,
            minzoom: 12,
            maxzoom: 19,
          },
        },
        layers: [
          { id: "bg", type: "background", paint: { "background-color": "#1c2225" } },
          { id: "pre", type: "raster", source: "pre", paint: { "raster-fade-duration": 0 } },
        ],
      },
    });
    const sync = () =>
      m.jumpTo({ center: main.getCenter(), zoom: main.getZoom(), bearing: main.getBearing(), pitch: main.getPitch() });
    main.on("move", sync);
    const ro = new ResizeObserver(() => m.resize());
    ro.observe(holder.current);
    return () => {
      main.off("move", sync);
      ro.disconnect();
      m.remove();
    };
  }, [main, areaId]);

  useEffect(() => {
    const move = (e: PointerEvent) => {
      if (!dragging.current || !box.current) return;
      const r = box.current.getBoundingClientRect();
      setX(Math.min(98, Math.max(2, ((e.clientX - r.left) / r.width) * 100)));
    };
    const up = () => (dragging.current = false);
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
  }, []);

  return (
    <div ref={box} className="pointer-events-none absolute inset-0 z-[5]">
      {/* maplibre's own CSS makes its container position: relative, so the
          map sits in a full-size child of the clipped box */}
      <div className="absolute inset-0" style={{ clipPath: `inset(0 ${100 - x}% 0 0)` }}>
        <div ref={holder} className="h-full w-full" />
      </div>
      <div className="absolute inset-y-0" style={{ left: `${x}%` }}>
        <div className="absolute inset-y-0 -ml-px w-0.5 bg-white/90 shadow-[0_0_0_1px_rgba(0,0,0,0.35)]" />
        <button
          type="button"
          role="slider"
          aria-label="Before and after divider"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(x)}
          onPointerDown={(e) => {
            dragging.current = true;
            (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowLeft") setX((v) => Math.max(2, v - 5));
            if (e.key === "ArrowRight") setX((v) => Math.min(98, v + 5));
          }}
          className="pointer-events-auto absolute top-1/2 -ml-4 grid h-8 w-8 -translate-y-1/2 cursor-ew-resize place-items-center rounded-full border border-black/30 bg-white text-[#141a1c] shadow-2"
        >
          <svg viewBox="0 0 16 16" className="h-4 w-4" aria-hidden>
            <path d="M6 4L2 8l4 4M10 4l4 4-4 4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
      <span className="absolute left-3 top-[60px] rounded-sm bg-black/70 px-1.5 py-0.5 text-[11px] font-semibold text-white">
        Before · {beforeLabel}
      </span>
      <span className="absolute right-3 top-[60px] rounded-sm bg-black/70 px-1.5 py-0.5 text-[11px] font-semibold text-white">
        After · {afterLabel}
      </span>
    </div>
  );
}

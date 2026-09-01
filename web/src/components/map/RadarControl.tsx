/**
 * Playback strip for the live NEXRAD radar loop: play/pause, a scrub slider
 * over the last hour of five-minute frames, and the frame's wall-clock time.
 * Bottom-centre of the map, only mounted while the radar layer is on.
 */
export default function RadarControl({
  playing,
  index,
  frames,
  onToggle,
  onScrub,
}: {
  playing: boolean;
  index: number;
  frames: { label: string; minutesAgo: number }[];
  onToggle: () => void;
  onScrub: (i: number) => void;
}) {
  const f = frames[index];
  if (!f) return null;
  const ago = f.minutesAgo === 0 ? "now" : `${f.minutesAgo} min ago`;

  return (
    <div className="absolute bottom-20 left-1/2 z-20 w-[min(420px,calc(100%-1.5rem))] -translate-x-1/2 md:bottom-4">
      <div className="panel flex items-center gap-3 px-3 py-2">
        <button
          onClick={onToggle}
          className="pressable grid h-7 w-7 shrink-0 place-items-center rounded-md bg-accent text-accent-ink"
          aria-label={playing ? "Pause radar" : "Play radar"}
        >
          {playing ? (
            <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" aria-hidden>
              <rect x="2" y="1.5" width="3" height="9" rx="0.6" />
              <rect x="7" y="1.5" width="3" height="9" rx="0.6" />
            </svg>
          ) : (
            <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" aria-hidden>
              <path d="M3 1.7v8.6a.6.6 0 0 0 .92.5l6.6-4.3a.6.6 0 0 0 0-1L3.92 1.2A.6.6 0 0 0 3 1.7Z" />
            </svg>
          )}
        </button>

        <input
          type="range"
          min={0}
          max={frames.length - 1}
          value={index}
          onChange={(e) => onScrub(Number(e.target.value))}
          aria-label="Radar frame"
          className="ba-range h-1 flex-1 cursor-pointer accent-accent"
        />

        <div className="tnum shrink-0 text-right text-2xs leading-tight text-ink-dim">
          <div className="text-ink">{f.label}</div>
          <div className="text-ink-faint">{ago}</div>
        </div>
      </div>
    </div>
  );
}

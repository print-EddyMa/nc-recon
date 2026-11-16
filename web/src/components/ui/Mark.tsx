/** The NC Recon mark, "the odd one out" (docs/brand): nine tiles, one per
 * building, and one knocked out of line in signal orange, the one that needs a
 * look. The eight tiles follow the text colour, so the mark tracks the light and
 * dark themes; the odd tile uses the brand colour. */
const TILES: [number, number][] = [
  [7, 7], [36, 7], [65, 7],
  [7, 36], [36, 36], [65, 36],
  [7, 65], [36, 65],
];

export function Mark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 100 100" className={className} aria-hidden>
      {TILES.map(([x, y]) => (
        <rect key={`${x}-${y}`} x={x} y={y} width="24" height="24" fill="currentColor" />
      ))}
      <rect x="69.2" y="68.4" width="24" height="24" transform="rotate(19 81.2 80.4)" style={{ fill: "rgb(var(--brand))" }} />
    </svg>
  );
}

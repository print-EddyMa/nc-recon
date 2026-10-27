/** The groma: a Roman surveyor's staff, cross-arm and plumb lines. Strokes
 * follow the text colour; the plumb bobs and finial are the bronze brand. */
export function GromaMark({ className }: { className?: string }) {
  const bronze = { fill: "rgb(var(--brand))" };
  return (
    <svg viewBox="0 0 64 64" className={className} aria-hidden>
      <g fill="none" stroke="currentColor" strokeLinecap="round">
        <line x1="32" y1="9" x2="32" y2="55" strokeWidth="3.6" />
        <line x1="9" y1="15" x2="55" y2="15" strokeWidth="3.6" />
        <line x1="6" y1="56" x2="58" y2="56" strokeWidth="3.6" />
        <line x1="12" y1="15" x2="12" y2="39" strokeWidth="1.8" />
        <line x1="52" y1="15" x2="52" y2="39" strokeWidth="1.8" />
      </g>
      <path d="M12 38.5l-3.6 3.4 3.6 6 3.6-6zM52 38.5l-3.6 3.4 3.6 6 3.6-6z" style={bronze} />
      <circle cx="32" cy="9" r="2.8" style={bronze} />
    </svg>
  );
}

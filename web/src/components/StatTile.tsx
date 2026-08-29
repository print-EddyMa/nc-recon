interface Props {
  label: string;
  value: string;
  sub?: string;
  accent?: string;
  align?: "left" | "center";
}

export default function StatTile({ label, value, sub, accent, align = "left" }: Props) {
  return (
    <div className={`panel px-4 py-3 ${align === "center" ? "text-center" : ""}`}>
      <div className="cap mb-1.5">{label}</div>
      <div
        className="tnum text-2xl font-semibold leading-none"
        style={accent ? { color: accent } : undefined}
      >
        {value}
      </div>
      {sub && <div className="mt-1 text-xs text-ink-dim">{sub}</div>}
    </div>
  );
}

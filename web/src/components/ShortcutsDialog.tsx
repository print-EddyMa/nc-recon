import { useEffect, useState } from "react";
import { Dialog } from "./ui/Dialog";

const KEYS: [string, string][] = [
  ["⌘K / Ctrl K", "Command menu — jump to a screen or any of 55 disasters"],
  ["?", "This shortcut list"],
  ["G then L", "Go to the live monitor"],
  ["G then M", "Go to the damage map (when a disaster is open)"],
  ["G then R", "Go to the review queue"],
  ["G then S", "Go to the summary"],
  ["Esc", "Close a menu or dialog"],
];

/** `?` opens a shortcut reference. `g` then a letter jumps between screens. */
export default function ShortcutsDialog({ onNav }: { onNav: (s: "live" | "map" | "review" | "stats") => void }) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let gPending = 0;
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      if (e.key === "?") {
        e.preventDefault();
        setOpen((o) => !o);
        return;
      }
      if (e.key.toLowerCase() === "g") {
        gPending = Date.now();
        return;
      }
      if (Date.now() - gPending < 900) {
        const map: Record<string, "live" | "map" | "review" | "stats"> = {
          l: "live",
          m: "map",
          r: "review",
          s: "stats",
        };
        const dest = map[e.key.toLowerCase()];
        if (dest) {
          e.preventDefault();
          onNav(dest);
        }
        gPending = 0;
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onNav]);

  return (
    <Dialog open={open} onOpenChange={setOpen} title="Keyboard shortcuts">
      <ul className="space-y-2">
        {KEYS.map(([k, d]) => (
          <li key={k} className="flex items-baseline gap-3 text-xs">
            <kbd className="tnum shrink-0 rounded-sm border border-line bg-surface-2 px-1.5 py-0.5 text-[10px] text-ink-dim">
              {k}
            </kbd>
            <span className="text-ink-dim">{d}</span>
          </li>
        ))}
      </ul>
    </Dialog>
  );
}

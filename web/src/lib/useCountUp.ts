import { useEffect, useRef, useState } from "react";
import { prefersReducedMotion } from "./motion";

/** Count up to `value`, easing out over `ms`. Animates 0 → value on first mount,
 * then previous → next whenever `value` changes. Under reduced-motion (or ms<=0)
 * it just returns the value. Used only for the headline stat figures on Home /
 * Summary / Review - see DESIGN.md § Motion. */
export function useCountUp(value: number, ms = 600): number {
  const reduced = prefersReducedMotion() || ms <= 0;
  const [n, setN] = useState(reduced ? value : 0);
  const from = useRef(reduced ? value : 0);

  useEffect(() => {
    if (reduced) return;
    const a = from.current;
    if (a === value) return;
    const start = performance.now();
    let raf = 0;
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / ms);
      const e = 1 - Math.pow(1 - p, 3); // cubic ease-out
      setN(a + (value - a) * e);
      if (p < 1) raf = requestAnimationFrame(tick);
      else from.current = value;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, ms, reduced]);

  return reduced ? value : n;
}

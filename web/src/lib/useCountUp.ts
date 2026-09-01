import { useEffect, useRef, useState } from "react";
import { prefersReducedMotion } from "./motion";

/** Count up to `value` once, easing out over `ms`: it animates the first
 * transition from 0 to a real target on mount, then every later change to
 * `value` just snaps. That "animate once, then track" behaviour is what the
 * Review queue needs - rapid Approve clicks must land the headline count
 * immediately, not restart a 600 ms roll each time. Reduced-motion (or ms<=0)
 * returns the value with no animation. Remounting (e.g. switching area, which
 * carries a React `key`) gives a fresh count-up. See DESIGN.md § Motion. */
export function useCountUp(value: number, ms = 600): number {
  const reduced = prefersReducedMotion() || ms <= 0;
  const [n, setN] = useState(0);
  const [done, setDone] = useState(false);
  const from = useRef(0);

  useEffect(() => {
    if (reduced || done) return;
    const a = from.current;
    if (a === value) return; // still waiting for the first real target
    const start = performance.now();
    let raf = 0;
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / ms);
      const e = 1 - Math.pow(1 - p, 3); // cubic ease-out
      setN(a + (value - a) * e);
      if (p < 1) {
        raf = requestAnimationFrame(tick);
      } else {
        from.current = value;
        setDone(true);
      }
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, ms, reduced, done]);

  return reduced || done ? value : n;
}

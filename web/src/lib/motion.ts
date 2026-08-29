/** Whether the viewer asked for reduced motion. Read at render; it's a cheap
 * media-query check and callers re-read on re-render. */
export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

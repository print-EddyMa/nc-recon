/**
 * Phase H — a tiny deterministic timeline. NOT GSAP: the task brief assumed
 * GSAP was already in the stack; it is not, and the project deliberately runs
 * with no motion library (see DESIGN.md § Motion). More to the point, the hard
 * requirement here is *frame-identical re-recordable playback*, which needs an
 * owned clock:
 *
 *   - mode "realtime" — advance by wall-clock delta. Use this for recording.
 *   - mode "fixed"    — advance by exactly `step` ms per frame regardless of
 *                       elapsed time. Use this for the 10x validation run so a
 *                       dropped frame can't shift which positions get sampled.
 *
 * A track is a pure function of the playhead in ms. Nothing here reads the DOM
 * or the network; `Stage` subscribes and renders.
 */

export type Ease = (t: number) => number;

export const easing = {
  linear: (t: number) => t,
  inOut: (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
  out: (t: number) => 1 - Math.pow(1 - t, 3),
  outQuint: (t: number) => 1 - Math.pow(1 - t, 5),
  in: (t: number) => t * t * t,
  /** aggressive "drop in" — slow to leave, then snaps home (Beats 3, 6) */
  inExpo: (t: number) => (t === 0 ? 0 : Math.pow(2, 10 * t - 10)),
  /** fast off the line, eases to rest (Beats 1) */
  outExpo: (t: number) => (t === 1 ? 1 : 1 - Math.pow(2, -10 * t)),
} satisfies Record<string, Ease>;

export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
export const clamp01 = (t: number) => (t < 0 ? 0 : t > 1 ? 1 : t);

export interface Track {
  /** ms */
  start: number;
  /** ms */
  end: number;
  ease?: Ease;
  /** called every frame while the playhead is anywhere in [0, total];
   *  `p` is the eased progress of THIS track (0 before start, 1 after end). */
  update: (p: number, ctx: FrameCtx) => void;
}

export interface FrameCtx {
  /** absolute playhead, ms */
  ms: number;
  /** whole-sequence progress 0..1 */
  whole: number;
  dt: number;
}

export interface TimelineOpts {
  total: number;
  mode?: "realtime" | "fixed";
  step?: number;
  onFrame?: (ctx: FrameCtx) => void;
  onEnd?: () => void;
}

export class Timeline {
  readonly total: number;
  private tracks: Track[] = [];
  private ms = 0;
  private raf = 0;
  private last = 0;
  private playing = false;
  private mode: "realtime" | "fixed";
  private step: number;
  private onFrame?: (ctx: FrameCtx) => void;
  private onEnd?: () => void;

  constructor(opts: TimelineOpts) {
    this.total = opts.total;
    this.mode = opts.mode ?? "realtime";
    this.step = opts.step ?? 1000 / 60;
    this.onFrame = opts.onFrame;
    this.onEnd = opts.onEnd;
  }

  add(track: Track): this {
    this.tracks.push(track);
    return this;
  }

  get currentMs() {
    return this.ms;
  }
  get isPlaying() {
    return this.playing;
  }

  /** Apply every track at the current playhead. Safe to call while paused. */
  private apply(dt: number) {
    const whole = clamp01(this.ms / this.total);
    const ctx: FrameCtx = { ms: this.ms, whole, dt };
    for (const tr of this.tracks) {
      const raw =
        tr.end === tr.start ? (this.ms >= tr.end ? 1 : 0) : (this.ms - tr.start) / (tr.end - tr.start);
      const p = (tr.ease ?? easing.linear)(clamp01(raw));
      tr.update(p, ctx);
    }
    this.onFrame?.(ctx);
  }

  /** Jump the playhead and repaint once. */
  seek(ms: number) {
    this.ms = Math.max(0, Math.min(this.total, ms));
    this.apply(0);
  }

  restart() {
    this.pause();
    this.seek(0);
  }

  play() {
    if (this.playing) return;
    this.playing = true;
    this.last = performance.now();
    const loop = (now: number) => {
      if (!this.playing) return;
      const dt = this.mode === "fixed" ? this.step : Math.min(64, now - this.last);
      this.last = now;
      this.ms += dt;
      if (this.ms >= this.total) {
        this.ms = this.total;
        this.apply(dt);
        this.playing = false;
        this.onEnd?.();
        return;
      }
      this.apply(dt);
      this.raf = requestAnimationFrame(loop);
    };
    this.raf = requestAnimationFrame(loop);
  }

  pause() {
    this.playing = false;
    if (this.raf) cancelAnimationFrame(this.raf);
    this.raf = 0;
  }

  toggle() {
    if (this.playing) this.pause();
    else this.play();
  }

  dispose() {
    this.pause();
    this.tracks = [];
  }
}

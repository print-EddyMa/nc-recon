import { useCallback, useEffect, useRef, useState } from "react";
import Stage, { type StageHandle } from "./Stage";
import { BEATS, TOTAL, beatAt } from "./beats";
import type { FrameCtx } from "../demo/timeline";

// Query flags (all optional):
//   ?hold      wait for Space instead of starting by itself (recording)
//   ?fixed     fixed 60 fps step, so a slow capture frame slows the playhead
//   ?prewarm   dense tile warm-up before the first frame (recording)
//   ?clean     no buttons or hints on the stage (recording)
//   ?debug     timecode HUD (also the D key)
const params = new URLSearchParams(location.search);
const HOLD = params.has("hold");
const FIXED = params.has("fixed");
const DENSE = params.has("prewarm");
const CLEAN = params.has("clean");
const DEBUG0 = params.has("debug");
// Where "Open Groma" goes. The intro is built with the pitch demo's pinned
// map stack, so the app is never on this dev server: in development it is the
// app's own dev server; in a build it is the site root unless VITE_APP_URL
// says otherwise.
const APP_URL =
  (import.meta.env.VITE_APP_URL as string | undefined) ||
  (import.meta.env.DEV ? "http://localhost:5173/" : "/");
const REDUCED =
  typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

type Phase = "loading" | "ready" | "running" | "paused" | "ended" | "error";

const tc = (ms: number) => {
  const s = ms / 1000;
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${(s % 60).toFixed(2).padStart(5, "0")}`;
};

export default function Intro() {
  const stage = useRef<StageHandle | null>(null);
  const [phase, setPhase] = useState<Phase>("loading");
  const [prog, setProg] = useState({ p: 0, label: "" });
  const [error, setError] = useState("");
  const [debug, setDebug] = useState(DEBUG0);
  const [ms, setMs] = useState(0);

  const onFrame = useCallback((ctx: FrameCtx) => setMs(ctx.ms), []);

  const play = useCallback(() => {
    setPhase("running");
    stage.current?.play();
  }, []);

  const onReady = useCallback(() => {
    if (REDUCED && !HOLD) {
      // no motion asked for: land on the title card and offer the sequence
      stage.current?.seek(TOTAL);
      setPhase("ended");
    } else if (HOLD) setPhase("ready");
    else play();
  }, [play]);

  const restart = useCallback(() => {
    stage.current?.restart();
    play();
  }, [play]);

  const skip = useCallback(() => {
    stage.current?.pause();
    stage.current?.seek(TOTAL);
    setPhase("ended");
  }, []);

  const toggle = useCallback(() => {
    if (phase === "loading" || phase === "error") return;
    if (phase === "ended") return restart();
    if (phase === "running") {
      stage.current?.pause();
      setPhase("paused");
    } else play();
  }, [phase, play, restart]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.repeat || e.metaKey || e.ctrlKey || e.altKey) return;
      const k = e.key.toLowerCase();
      if (k === " " || k === "k") {
        // let Space activate a focused button or link instead
        const t = e.target as HTMLElement | null;
        if (k === " " && t && (t.tagName === "BUTTON" || t.tagName === "A")) return;
        e.preventDefault();
        toggle();
      } else if (k === "r") restart();
      else if (k === "s" || k === "arrowright" || k === "escape") skip();
      else if (k === "f") {
        if (document.fullscreenElement) void document.exitFullscreen();
        else void document.documentElement.requestFullscreen?.().catch(() => {});
      } else if (k === "d") setDebug((v) => !v);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggle, restart, skip]);

  // handle for capture scripts: window.__intro.seek(ms) then screenshot
  useEffect(() => {
    (window as unknown as { __intro: unknown }).__intro = {
      play,
      pause: () => stage.current?.pause(),
      restart,
      seek: (t: number) => stage.current?.seek(t),
      get ms() {
        return stage.current?.timeline?.currentMs ?? 0;
      },
      get beat() {
        return beatAt(stage.current?.timeline?.currentMs ?? 0).id;
      },
      total: TOTAL,
      ready: () => phase !== "loading" && phase !== "error",
    };
  }, [play, restart, phase]);

  const beat = beatAt(ms);
  const chrome = !CLEAN;

  return (
    <div className={`intro-root${phase === "running" ? " is-running" : ""}`}>
      <Stage
        ref={stage}
        mode={FIXED ? "fixed" : "realtime"}
        dense={DENSE}
        onProgress={(p, label) => setProg({ p, label })}
        onReady={onReady}
        onError={(m) => {
          setError(m);
          setPhase("error");
        }}
        onFrame={onFrame}
        onEnd={() => setPhase("ended")}
      />

      {phase === "loading" && (
        <div className="intro-loader" role="status">
          <div className="intro-loader-bar">
            <div style={{ transform: `scaleX(${prog.p})` }} />
          </div>
          <div className="intro-loader-label">
            Loading the sequence · {prog.label} · {Math.round(prog.p * 100)}%
          </div>
        </div>
      )}

      {phase === "error" && (
        <div className="intro-loader" role="alert">
          <div className="intro-loader-label">
            The intro could not load: {error}. Its assets are baked with{" "}
            <code>npm run demo:assets</code> and <code>npm run intro:assets</code> in web/.
          </div>
        </div>
      )}

      {phase === "ready" && (
        <button className="intro-start" onClick={play}>
          <span>Space</span> play
        </button>
      )}

      {chrome && phase === "paused" && (
        <button className="intro-start" onClick={play}>
          <span>Space</span> resume
        </button>
      )}

      {chrome && (phase === "running" || phase === "paused") && ms < BEATS[BEATS.length - 1].t0 && (
        <button className="intro-skip" onClick={skip}>
          Skip intro
        </button>
      )}

      {chrome && phase === "ended" && (
        <div className="intro-actions">
          <a className="intro-btn intro-btn-primary" href={APP_URL}>
            Open Groma
          </a>
          <button className="intro-btn" onClick={restart}>
            {REDUCED && ms >= TOTAL ? "Play intro" : "Replay"}
          </button>
        </div>
      )}

      {debug && (
        <div className="intro-debug">
          <b>{tc(ms)}</b> / {tc(TOTAL)} · {BEATS.indexOf(beat) + 1}. {beat.name} · {phase}
          {FIXED ? " · fixed step" : ""}
        </div>
      )}
    </div>
  );
}

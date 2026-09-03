import { useCallback, useEffect, useRef, useState } from "react";
import Stage, { type StageHandle } from "./Stage";
import { BEATS, TOTAL, beatAt } from "./beats";
import type { FrameCtx } from "./timeline";

const params = new URLSearchParams(location.search);
const AUTOPLAY = params.has("autoplay");
const DEBUG0 = params.has("debug");
const FIXED = params.has("fixed"); // deterministic step, for validate_demo.mjs

const fmt = (ms: number) => {
  const s = ms / 1000;
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${(s % 60).toFixed(2).padStart(5, "0")}`;
};

export default function Demo() {
  const stage = useRef<StageHandle | null>(null);
  const [phase, setPhase] = useState<"loading" | "ready" | "running">("loading");
  const [prog, setProg] = useState({ p: 0, label: "" });
  const [warmed, setWarmed] = useState(0);
  const [debug, setDebug] = useState(DEBUG0);
  const [hud, setHud] = useState<{ ms: number; playing: boolean }>({ ms: 0, playing: false });
  const startedRef = useRef(false);

  const onFrame = useCallback((ctx: FrameCtx) => {
    setHud({ ms: ctx.ms, playing: stage.current?.timeline?.isPlaying ?? false });
  }, []);

  const onReady = useCallback(
    ({ tilesWarmed }: { tilesWarmed: number }) => {
      setWarmed(tilesWarmed);
      setPhase("ready");
      if (AUTOPLAY && !startedRef.current) {
        startedRef.current = true;
        setPhase("running");
        stage.current?.play();
      }
    },
    [],
  );

  const restart = useCallback(() => {
    stage.current?.restart();
    setPhase("ready");
    setHud({ ms: 0, playing: false });
  }, []);

  const toggle = useCallback(() => {
    if (phase === "loading") return;
    if (phase === "ready") setPhase("running");
    stage.current?.toggle();
  }, [phase]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.repeat) return;
      const k = e.key.toLowerCase();
      if (k === " " || k === "k") {
        e.preventDefault();
        toggle();
      } else if (k === "r") {
        e.preventDefault();
        restart();
      } else if (k === "f") {
        e.preventDefault();
        if (document.fullscreenElement) document.exitFullscreen();
        else document.documentElement.requestFullscreen?.();
      } else if (k === "d") {
        setDebug((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggle, restart]);

  // imperative handle for the headless validation harness
  useEffect(() => {
    (window as unknown as { __demo: unknown }).__demo = {
      play: () => stage.current?.play(),
      pause: () => stage.current?.pause(),
      restart,
      seek: (ms: number) => stage.current?.timeline?.seek(ms),
      get ms() {
        return stage.current?.timeline?.currentMs ?? 0;
      },
      get playing() {
        return stage.current?.timeline?.isPlaying ?? false;
      },
      get beat() {
        return beatAt(stage.current?.timeline?.currentMs ?? 0).id;
      },
      total: TOTAL,
      ready: () => phase !== "loading",
    };
  }, [restart, phase]);

  const beat = beatAt(hud.ms);

  return (
    <div className={`demo-root${phase === "ready" && !hud.playing ? " idle" : ""}`}>
      <Stage
        ref={stage}
        mode={FIXED ? "fixed" : "realtime"}
        fixedStep={1000 / 60}
        onProgress={(p, label) => setProg({ p, label })}
        onReady={onReady}
        onFrame={onFrame}
      />

      {phase === "loading" && (
        <div className="demo-loader">
          <div className="demo-loader-bar">
            <div className="demo-loader-fill" style={{ width: `${Math.round(prog.p * 100)}%` }} />
          </div>
          <div className="demo-loader-label">
            preparing sequence · {prog.label} · {Math.round(prog.p * 100)}%
          </div>
        </div>
      )}

      {phase === "ready" && !hud.playing && hud.ms === 0 && (
        <div className="demo-start" onClick={toggle}>
          <div className="demo-start-key">SPACE</div>
          <div className="demo-start-sub">
            play · <b>R</b> restart · <b>F</b> fullscreen
          </div>
        </div>
      )}

      {debug && (
        <div className="demo-debug">
          <span className="demo-debug-tc">{fmt(hud.ms)}</span> / {fmt(TOTAL)}
          <span className="demo-debug-beat">
            {BEATS.indexOf(beat) + 1}. {beat.name}
          </span>
          <span className="demo-debug-meta">
            {hud.playing ? "▶" : "⏸"} · {warmed} tiles warmed{FIXED ? " · fixed-step" : ""}
          </span>
          <div className="demo-debug-track">
            {BEATS.map((b) => (
              <span
                key={b.id}
                style={{
                  left: `${(b.t0 / TOTAL) * 100}%`,
                  width: `${((b.t1 - b.t0) / TOTAL) * 100}%`,
                }}
                className={b.id === beat.id ? "on" : ""}
              />
            ))}
            <i style={{ left: `${(hud.ms / TOTAL) * 100}%` }} />
          </div>
        </div>
      )}
    </div>
  );
}

import { useCallback, useSyncExternalStore } from "react";

/**
 * Per-viewer settings kept in localStorage (never leaves the browser). Right now
 * just the optional NASA FIRMS map key so the active-fire layer can be enabled
 * without a rebuild.
 */
export interface Settings {
  firmsKey?: string;
}

const KEY = "terratriage:settings";
let cache: Settings | null = null;
const listeners = new Set<() => void>();

function read(): Settings {
  if (cache) return cache;
  try {
    cache = JSON.parse(localStorage.getItem(KEY) || "{}") as Settings;
  } catch {
    cache = {};
  }
  return cache;
}

function write(next: Settings) {
  cache = next;
  try {
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    /* private window */
  }
  listeners.forEach((l) => l());
}

const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => listeners.delete(l);
};

export function useSettings() {
  const settings = useSyncExternalStore(subscribe, read, () => ({}) as Settings);
  const set = useCallback(<K extends keyof Settings>(k: K, v: Settings[K]) => {
    const next = { ...read() };
    if (v == null || v === "") delete next[k];
    else next[k] = v;
    write(next);
  }, []);
  return { settings, set };
}

/** Non-hook access (for lib code). */
export const getSetting = <K extends keyof Settings>(k: K): Settings[K] => read()[k];

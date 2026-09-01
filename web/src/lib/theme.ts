import { useCallback, useSyncExternalStore } from "react";

/**
 * Light / dark / system theme, stored per viewer in localStorage. The initial
 * value is applied by a tiny inline script in index.html (before first paint) so
 * there is no flash; this module keeps React in sync and lets the toggle change
 * it at runtime.
 */
export type Theme = "light" | "dark" | "system";
const KEY = "terratriage:theme";

const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

function read(): Theme {
  try {
    const v = localStorage.getItem(KEY);
    if (v === "light" || v === "dark") return v;
  } catch {
    /* private window */
  }
  return "system";
}

/** the theme actually in effect right now (system resolved to light/dark) */
export function resolved(t: Theme = read()): "light" | "dark" {
  if (t !== "system") return t;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function apply(t: Theme) {
  const root = document.documentElement;
  if (t === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", t);
}

export function setTheme(t: Theme) {
  try {
    if (t === "system") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, t);
  } catch {
    /* ignore */
  }
  apply(t);
  emit();
}

const subscribe = (l: () => void) => {
  listeners.add(l);
  const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
  const onSys = () => emit();
  mq?.addEventListener?.("change", onSys);
  return () => {
    listeners.delete(l);
    mq?.removeEventListener?.("change", onSys);
  };
};

export function useTheme() {
  const theme = useSyncExternalStore(subscribe, read, () => "system" as Theme);
  const eff = resolved(theme);
  const cycle = useCallback(() => {
    // toggle between explicit light and dark (skip "system" on manual cycle)
    setTheme(resolved() === "dark" ? "light" : "dark");
  }, []);
  return { theme, effective: eff, setTheme, cycle };
}

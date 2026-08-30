import { useCallback, useSyncExternalStore } from "react";
import type { DamageClass } from "./types";

/**
 * Phase D3 — the human-in-the-loop review queue's memory. A team member's
 * approve / reject / override on a "needs review" building is kept per-viewer in
 * localStorage (it never leaves the browser). Consumers read it back to redraw
 * the map and re-tally the summary with human calls applied.
 *
 * Backed by a tiny module-level store so every `useReviewDecisions` call — the
 * queue, the map, the summary, the nav badge — stays in sync within a session.
 */
export type ReviewAction = "approve" | "reject" | "override";

export interface ReviewDecision {
  action: ReviewAction;
  /** present only when action === "override" */
  damage_class?: DamageClass;
  at: number;
}

type Store = Record<string, ReviewDecision>;

const KEY = (areaId: string) => `terratriage:review:${areaId}`;
const EMPTY: Store = {};

const caches = new Map<string, Store>();
const listeners = new Set<() => void>();

function load(areaId: string): Store {
  if (caches.has(areaId)) return caches.get(areaId)!;
  let parsed: Store = EMPTY;
  try {
    const raw = localStorage.getItem(KEY(areaId));
    if (raw) parsed = JSON.parse(raw) as Store;
  } catch {
    /* private window / disabled storage */
  }
  caches.set(areaId, parsed);
  return parsed;
}

function persist(areaId: string, store: Store) {
  caches.set(areaId, store);
  try {
    localStorage.setItem(KEY(areaId), JSON.stringify(store));
  } catch {
    /* session-only */
  }
  listeners.forEach((l) => l());
}

const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => listeners.delete(l);
};

/** Live view of one area's review decisions + setters that persist + notify. */
export function useReviewDecisions(areaId: string) {
  const decisions = useSyncExternalStore(
    subscribe,
    () => (areaId ? load(areaId) : EMPTY),
    () => EMPTY,
  );

  const setDecision = useCallback(
    (featureId: string, decision: ReviewDecision | null) => {
      if (!areaId) return;
      const next = { ...load(areaId) };
      if (decision) next[featureId] = decision;
      else delete next[featureId];
      persist(areaId, next);
    },
    [areaId],
  );

  const clearAll = useCallback(() => {
    if (areaId) persist(areaId, {});
  }, [areaId]);

  return { decisions, setDecision, clearAll };
}

/** Map of featureId -> effective damage class, for decisions that change it
 * (only "override" does). Approve/reject leave the model class in place. */
export function overrideClasses(store: Store): Record<string, DamageClass> {
  const out: Record<string, DamageClass> = {};
  for (const [id, d] of Object.entries(store)) {
    if (d.action === "override" && d.damage_class != null) out[id] = d.damage_class;
  }
  return out;
}

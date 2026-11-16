/* System status that every screen shares: are the data sources up, who is
 * signed in, and how far the model has been validated. These used to sit
 * at the bottom of the area list; they belong in the frame, one click away. */
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { API_URL } from "../../lib/catalog";
import {
  ago,
  fmtAge,
  labelerName,
  loadHealth,
  loadReport,
  responderToken,
  setLabelerName,
  setResponderToken,
  type HealthBoard,
  type HealthRow,
} from "../../lib/ops";
import { Button, Dot, Icon, Popover, type Status } from "../ui/kit";
import { useOffline } from "../../lib/offline";

const ROW_STATUS: Record<HealthRow["status"], Status> = {
  ok: "ok",
  stale: "warn",
  down: "bad",
  unconfigured: "unknown",
};
const STATUS_WORD: Record<HealthRow["status"], string> = {
  ok: "OK",
  stale: "Stale",
  down: "Down",
  unconfigured: "Not set up",
};
const HIDDEN = new Set(["usgs_waterservices_legacy"]);

function useHealth() {
  const [h, setH] = useState<HealthBoard | null>(null);
  const [err, setErr] = useState(false);
  const load = useCallback((recheck = false) => {
    if (!API_URL) return;
    loadHealth(recheck)
      .then((d) => {
        setH(d);
        setErr(false);
      })
      .catch(() => setErr(true));
  }, []);
  useEffect(() => {
    load();
    const t = window.setInterval(() => load(), 5 * 60_000);
    return () => window.clearInterval(t);
  }, [load]);
  // a re-check runs in the background on the server: look again until it lands
  const refreshing = h?.refreshing ?? false;
  useEffect(() => {
    if (!refreshing) return;
    const t = window.setInterval(() => load(), 3000);
    return () => window.clearInterval(t);
  }, [refreshing, load]);
  return { h, err, load, refreshing };
}

/** Top-bar button: one dot that summarises every source, a list on click. */
export function SourcesButton() {
  const { h, err, load, refreshing } = useHealth();
  const rows = h?.sources.filter((s) => !HIDDEN.has(s.source)) ?? [];
  const down = rows.filter((s) => s.status === "down").length;
  const stale = rows.filter((s) => s.status === "stale").length;
  // offline the feeds cannot be checked: unknown, never a green "OK"
  const offline = !!useOffline()?.offline;
  const overall: Status =
    !API_URL || err || offline ? "unknown" : down ? "bad" : stale ? "warn" : h ? "ok" : "unknown";
  const word = !API_URL
    ? "No service"
    : offline
      ? "Sources not checked"
      : err
      ? "Status unavailable"
      : down
        ? `${down} source${down > 1 ? "s" : ""} down`
        : stale
          ? `${stale} stale`
          : h
            ? "Sources OK"
            : "Checking…";
  return (
    <Popover
      label="Data sources"
      trigger={({ open, toggle, id }) => (
        <button
          onClick={toggle}
          aria-expanded={open}
          aria-controls={id}
          className="pressable inline-flex h-8 items-center gap-2 rounded border border-line bg-surface px-2 text-[13px] text-ink-dim hover:text-ink sm:px-2.5"
        >
          <Dot status={overall} pulse={overall === "bad"} />
          <span className="hidden md:inline">{word}</span>
        </button>
      )}
    >
      <div className="flex items-baseline justify-between gap-2">
        <div className="text-sm font-semibold text-ink">Data sources</div>
        {h && (
          <span className="text-xs text-ink-faint">
            {refreshing ? "checking…" : `checked ${ago(h.checked_utc)}`}
          </span>
        )}
      </div>
      {down > 0 && (
        <p className="mt-1 text-[13px] text-st-bad" role="status">
          New assessments may fail or lose detail while a source is down.
        </p>
      )}
      {err && !h && <p className="mt-2 text-sm text-ink-dim">The assessment service did not answer.</p>}
      <ul className="mt-2 max-h-72 space-y-1 overflow-y-auto pr-1">
        {rows.map((s) => (
          <li key={s.source} className="flex items-center gap-2 text-[13px]" title={s.detail}>
            <Dot status={ROW_STATUS[s.status]} />
            <span className="flex-1 truncate text-ink">{s.source.replace(/_/g, " ")}</span>
            <span className={`tnum font-mono text-xs ${s.status === "down" ? "text-st-bad" : "text-ink-faint"}`}>
              {STATUS_WORD[s.status]}
              {s.status === "ok" && s.data_age_s != null ? ` · ${fmtAge(s.data_age_s)}` : ""}
            </span>
          </li>
        ))}
      </ul>
      {h && (
        <Button size="sm" className="mt-3" disabled={refreshing} busy={refreshing} onClick={() => load(true)}>
          Check again
        </Button>
      )}
    </Popover>
  );
}

/** Top-bar button: the responder token and the analyst's initials. */
export function AccessButton() {
  const [tok, setTok] = useState(responderToken());
  const [who, setWho] = useState(labelerName());
  const signed = !!responderToken();
  return (
    <Popover
      label="Responder access"
      trigger={({ open, toggle, id }) => (
        <button
          onClick={toggle}
          aria-expanded={open}
          aria-controls={id}
          title={signed ? "Responder access is set in this browser" : "Set responder access"}
          className="pressable inline-flex h-8 items-center gap-1.5 rounded border border-line bg-surface px-2 text-[13px] text-ink-dim hover:text-ink sm:px-2.5"
        >
          <Icon name="key" className={signed ? "text-accent" : ""} />
          <span className="hidden lg:inline">{signed ? (labelerName() || "Responder") : "Sign in"}</span>
        </button>
      )}
    >
      {(close) => (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setResponderToken(tok);
            setLabelerName(who);
            toast("Access saved in this browser. Reopen an area to load structure-level data.");
            close();
          }}
        >
          <div className="text-sm font-semibold text-ink">Responder access</div>
          <p className="mt-1 text-[13px] leading-relaxed text-ink-dim">
            Structure-level results, addresses, labels, exports and briefs need the service token.
            It stays in this browser.
          </p>
          <label className="mt-3 block text-xs font-medium text-ink-dim" htmlFor="acc-token">
            Service token
          </label>
          <input id="acc-token" type="password" value={tok} onChange={(e) => setTok(e.target.value)} className="field mt-1" autoComplete="off" />
          <label className="mt-2 block text-xs font-medium text-ink-dim" htmlFor="acc-who">
            Your name or initials (saved with each label)
          </label>
          <input id="acc-who" value={who} onChange={(e) => setWho(e.target.value)} className="field mt-1" />
          <div className="mt-3 flex gap-2">
            <Button type="submit" variant="primary" size="sm">
              Save
            </Button>
            {signed && (
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => {
                  setResponderToken("");
                  setTok("");
                  close();
                }}
              >
                Sign out
              </Button>
            )}
          </div>
        </form>
      )}
    </Popover>
  );
}

/** Accuracy status: the honest state of validation, for the overview. */
export function AccuracyNote() {
  const [rep, setRep] = useState<Record<string, unknown> | null>(null);
  useEffect(() => {
    if (!API_URL) return;
    loadReport()
      .then(setRep)
      .catch(() => setRep({ status: "UNAVAILABLE" }));
  }, []);
  if (!rep) return null;
  const roles = (rep.roles ?? {}) as Record<
    string,
    { all: { n: number; macro_f1: number | null; destroyed_recall: number | null } }
  >;
  if (rep.status !== "OK")
    return (
      <div className="flex gap-2.5 rounded border border-st-warn/40 bg-st-warn/10 p-3 text-[13px] leading-relaxed">
        <Icon name="alert" className="mt-0.5 text-st-warn" />
        <div>
          <b className="text-ink">Accuracy not yet validated.</b>{" "}
          <span className="text-ink-dim">
            No held-out labels exist yet, so no accuracy figure is shown. Treat every call as a lead
            to verify.
          </span>
        </div>
      </div>
    );
  return (
    <div className="rounded border border-line p-3 text-[13px]">
      <div className="font-semibold text-ink">Measured accuracy</div>
      {Object.entries(roles).map(([role, r]) => (
        <div key={role} className="mt-1">
          <span className="text-ink-dim">
            {role} areas · {r.all.n} labelled{role === "TUNE" && " (fitted here: optimistic)"}
          </span>
          <div className="tnum font-mono text-ink">
            macro-F1 {r.all.macro_f1?.toFixed(2) ?? "n/a"} · Destroyed recall{" "}
            {r.all.destroyed_recall?.toFixed(2) ?? "n/a"}
          </div>
        </div>
      ))}
    </div>
  );
}

/** Shown only when the server runs from an offline pack: what still works,
 * what does not, and where labels made here end up. */
export function OfflineButton() {
  const off = useOffline();
  if (!off?.offline) return null;
  return (
    <Popover
      label="Offline"
      trigger={({ open, toggle, id }) => (
        <button
          onClick={toggle}
          aria-expanded={open}
          aria-controls={id}
          className="pressable inline-flex h-8 items-center gap-1.5 rounded border border-st-warn/50 bg-st-warn/10 px-2 text-[13px] font-medium text-ink sm:px-2.5"
        >
          <Dot status="warn" />
          Offline
        </button>
      )}
    >
      <div className="text-sm font-semibold text-ink">Working offline</div>
      <p className="mt-1 text-xs leading-relaxed text-ink-dim">
        Packed areas open with their own imagery and results.{" "}
        {off.basemap.available ? "The base map is the packed USGS topo." : "No base map was packed, so only the area imagery shows."}
      </p>
      <div className="mt-3 text-xs font-semibold text-ink">Not available</div>
      <ul className="mt-1 list-disc space-y-1 pl-4 text-xs leading-relaxed text-ink-dim">
        {off.unavailable_offline.map((x) => (
          <li key={x}>{x}</li>
        ))}
      </ul>
      {off.labels && <p className="mt-3 border-t border-line pt-2 text-xs leading-relaxed text-ink-dim">{off.labels}</p>}
      {off.packs.length > 0 && (
        <div className="mt-3 border-t border-line pt-2 text-xs text-ink-faint">
          {off.packs.length} pack{off.packs.length > 1 ? "s" : ""}:{" "}
          {off.packs.map((p) => `${p.area}${p.pack_created_utc ? ` (${p.pack_created_utc.slice(0, 10)})` : ""}`).join(", ")}
        </div>
      )}
    </Popover>
  );
}

import { useEffect, useMemo } from "react";
import { Command } from "cmdk";
import { Map as MapIcon, Radio, ListChecks, BarChart3, Home, Search } from "lucide-react";
import HazardIcon from "./HazardIcon";
import { HAZARD_LABEL } from "../lib/events";
import type { CatalogEvent } from "../lib/catalog";
import type { IngestState } from "../lib/useAssess";
import type { EventConfig } from "../lib/types";

export type CommandScreen = "landing" | "map" | "live" | "review" | "stats";

interface Props {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  events: EventConfig[];
  catalog: CatalogEvent[];
  currentEventId: string;
  online: boolean | null;
  jobs: Record<string, IngestState>;
  onNav: (s: CommandScreen) => void;
  onPickEvent: (id: string) => void;
  onIngest: (ev: { id: string; name: string; center: [number, number] | null }) => void;
}

const SCREENS: { id: CommandScreen; label: string; icon: typeof MapIcon }[] = [
  { id: "map", label: "Damage map", icon: MapIcon },
  { id: "live", label: "Live monitor", icon: Radio },
  { id: "review", label: "Review queue", icon: ListChecks },
  { id: "stats", label: "Summary", icon: BarChart3 },
  { id: "landing", label: "Overview", icon: Home },
];

/**
 * ⌘K command palette — screen navigation + one place to open or ingest any of
 * the ~55 Maxar Open Data disasters. Built on `cmdk` (the primitive behind most
 * shadcn / 21st.dev command menus), styled to the app's tokens.
 */
export default function CommandMenu({
  open,
  onOpenChange,
  events,
  catalog,
  currentEventId,
  online,
  jobs,
  onNav,
  onPickEvent,
  onIngest,
}: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        onOpenChange(!open);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  const ingestedIds = useMemo(() => new Set(events.map((e) => e.id)), [events]);
  const catalogRest = useMemo(
    () => catalog.filter((e) => !ingestedIds.has(e.id)),
    [catalog, ingestedIds],
  );

  const run = (fn: () => void) => {
    fn();
    onOpenChange(false);
  };

  return (
    <>
      <Command.Dialog
        open={open}
        onOpenChange={onOpenChange}
        label="Command menu"
        className="fixed left-1/2 top-[18vh] z-[100] w-[min(560px,calc(100vw-2rem))] -translate-x-1/2"
        overlayClassName="fixed inset-0 z-[99] bg-canvas/70 backdrop-blur-[2px]"
      >
        <div className="panel overflow-hidden p-0">
          <div className="flex items-center gap-2.5 border-b border-line px-3.5">
            <Search size={15} className="shrink-0 text-ink-faint" />
            <Command.Input
              autoFocus
              placeholder="Jump to a screen, search 55 disasters…"
              className="w-full bg-transparent py-3 text-sm text-ink outline-none placeholder:text-ink-faint"
            />
          </div>

          <Command.List className="max-h-[52vh] overflow-y-auto p-1.5">
            <Command.Empty className="px-3 py-6 text-center text-xs text-ink-faint">
              No matches.
            </Command.Empty>

            <Command.Group
              heading="Go to"
              className="[&_[cmdk-group-heading]]:cap [&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1.5"
            >
              {SCREENS.map((s) => (
                <Item key={s.id} onSelect={() => run(() => onNav(s.id))}>
                  <s.icon size={14} className="shrink-0 text-ink-faint" />
                  <span className="flex-1">{s.label}</span>
                </Item>
              ))}
            </Command.Group>

            {events.length > 0 && (
              <Command.Group
                heading="Assessed events"
                className="[&_[cmdk-group-heading]]:cap [&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1.5"
              >
                {events.map((e) => (
                  <Item
                    key={e.id}
                    value={`open ${e.name} ${HAZARD_LABEL[e.hazard]} ${e.region ?? ""}`}
                    onSelect={() => run(() => onPickEvent(e.id))}
                  >
                    <HazardIcon hazard={e.hazard} size={14} className="shrink-0 text-ink-faint" />
                    <span className="flex-1 truncate">
                      {e.name}
                      {e.id === currentEventId && (
                        <span className="ml-2 text-2xs text-accent">current</span>
                      )}
                    </span>
                    <span className="text-2xs text-ink-faint">open</span>
                  </Item>
                ))}
              </Command.Group>
            )}

            <Command.Group
              heading={`Maxar Open Data catalogue · ${online ? "ingest" : "commands"}`}
              className="[&_[cmdk-group-heading]]:cap [&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1.5"
            >
              {catalogRest.map((e) => {
                const job = jobs[e.id];
                return (
                  <Item
                    key={e.id}
                    value={`ingest ${e.name} ${e.hazard} ${e.id}`}
                    disabled={job?.phase === "running" || !e.center}
                    onSelect={() =>
                      run(() => onIngest({ id: e.id, name: e.name, center: e.center }))
                    }
                  >
                    <HazardIcon hazard={e.hazard} size={14} className="shrink-0 text-ink-faint" />
                    <span className="flex-1 truncate">{e.name}</span>
                    <span className="tnum text-2xs text-ink-faint">
                      {job?.phase === "running"
                        ? job.step
                        : e.capture_dates?.length
                          ? e.capture_dates[e.capture_dates.length - 1]
                          : ""}
                    </span>
                    <span className="text-2xs text-ink-faint">
                      {job?.phase === "running" ? "…" : online ? "ingest" : "how"}
                    </span>
                  </Item>
                );
              })}
            </Command.Group>
          </Command.List>
        </div>
      </Command.Dialog>
    </>
  );
}

function Item({
  children,
  onSelect,
  value,
  disabled,
}: {
  children: React.ReactNode;
  onSelect: () => void;
  value?: string;
  disabled?: boolean;
}) {
  return (
    <Command.Item
      value={value}
      disabled={disabled}
      onSelect={onSelect}
      className="flex cursor-pointer items-center gap-2.5 rounded-md px-2.5 py-2 text-sm text-ink-dim aria-selected:bg-surface-2 aria-selected:text-ink data-[disabled=true]:opacity-40"
    >
      {children}
    </Command.Item>
  );
}

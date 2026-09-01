import { useEffect, useMemo } from "react";
import { Command } from "cmdk";
import { Map as MapIcon, ListChecks, BarChart3, Home, Search, MapPin, Crosshair, LayoutGrid, Clock } from "lucide-react";
import HazardIcon from "./HazardIcon";
import { intersectsNC, ncPointFor, type CatalogEvent } from "../lib/catalog";
import type { IngestState, AssessTarget } from "../lib/useAssess";
import type { EventConfig } from "../lib/types";

export type CommandScreen = "home" | "nc" | "history" | "assess" | "map" | "review" | "stats" | "about";

interface Props {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  areas: { event: EventConfig; area: EventConfig["areas"][number] }[];
  catalog: CatalogEvent[];
  currentAreaId: string;
  online: boolean | null;
  jobs: Record<string, IngestState>;
  onNav: (s: CommandScreen) => void;
  onPickArea: (areaId: string) => void;
  onIngest: (t: AssessTarget) => void;
}

const SCREENS: { id: CommandScreen; label: string; icon: typeof MapIcon }[] = [
  { id: "home", label: "Home dashboard", icon: LayoutGrid },
  { id: "nc", label: "Live NC map", icon: MapPin },
  { id: "history", label: "Disaster history timeline", icon: Clock },
  { id: "assess", label: "Assess an area", icon: Crosshair },
  { id: "map", label: "Damage map", icon: MapIcon },
  { id: "review", label: "Review queue", icon: ListChecks },
  { id: "stats", label: "Summary", icon: BarChart3 },
  { id: "about", label: "About", icon: Home },
];

/**
 * ⌘K command palette, screen navigation, assessed NC areas, and the NC subset
 * of the Maxar Open Data catalogue for a one-key assessment. Built on `cmdk`.
 */
export default function CommandMenu({
  open,
  onOpenChange,
  areas,
  catalog,
  currentAreaId,
  online,
  jobs,
  onNav,
  onPickArea,
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

  const ncCatalog = useMemo(
    () => catalog.filter(intersectsNC).filter((e) => e.center || e.bbox),
    [catalog],
  );

  const run = (fn: () => void) => {
    fn();
    onOpenChange(false);
  };

  return (
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
            placeholder="Jump to a screen, open or assess an NC area…"
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

          {areas.length > 0 && (
            <Command.Group
              heading="Assessed NC areas"
              className="[&_[cmdk-group-heading]]:cap [&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1.5"
            >
              {areas.map(({ event: e, area: a }) => (
                <Item
                  key={a.id}
                  value={`open ${a.name} ${e.name} ${a.subtitle ?? ""}`}
                  onSelect={() => run(() => onPickArea(a.id))}
                >
                  <HazardIcon hazard={e.hazard} size={14} className="shrink-0 text-ink-faint" />
                  <span className="flex-1 truncate">
                    {a.name}
                    <span className="ml-1.5 text-2xs text-ink-faint">{e.name}</span>
                    {a.id === currentAreaId && (
                      <span className="ml-2 text-2xs text-accent">current</span>
                    )}
                  </span>
                  <span className="text-2xs text-ink-faint">open</span>
                </Item>
              ))}
            </Command.Group>
          )}

          <Command.Group
            heading={`Maxar events covering NC · ${online ? "assess" : "commands"}`}
            className="[&_[cmdk-group-heading]]:cap [&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1.5"
          >
            {ncCatalog.map((e) => {
              const job = jobs[e.id];
              // an in-NC point so the service doesn't reject a multi-state event
              // whose centroid sits in VA/SC; the map Assess screen is precise
              const point = ncPointFor(e);
              return (
                <Item
                  key={e.id}
                  value={`assess ${e.name} ${e.hazard} ${e.id}`}
                  disabled={job?.phase === "running" || !point}
                  onSelect={() =>
                    run(() => onIngest({ id: e.id, name: `${e.name} (NC)`, center: e.center, point }))
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
                    {job?.phase === "running" ? "…" : online ? "assess" : "how"}
                  </span>
                </Item>
              );
            })}
          </Command.Group>
        </Command.List>
      </div>
    </Command.Dialog>
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

import * as RD from "@radix-ui/react-dialog";
import type { ReactNode } from "react";
import { cn } from "../../lib/utils";

/** shadcn-style dialog on Radix, focus trap + scroll lock + a11y for free. */
export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  className,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <RD.Root open={open} onOpenChange={onOpenChange}>
      <RD.Portal>
        <RD.Overlay className="fixed inset-0 z-[110] bg-canvas/70 backdrop-blur-[2px] data-[state=open]:animate-[skel_0ms]" />
        <RD.Content
          className={cn(
            "panel fixed left-1/2 top-1/2 z-[111] w-[min(520px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 p-5",
            className,
          )}
        >
          <div className="mb-3 flex items-start justify-between gap-4">
            <div>
              <RD.Title className="section-title">{title}</RD.Title>
              {description && (
                <RD.Description className="mt-1 text-xs text-ink-faint">{description}</RD.Description>
              )}
            </div>
            <RD.Close
              className="pressable -m-1 grid h-6 w-6 place-items-center rounded-md text-ink-faint hover:bg-surface-2 hover:text-ink"
              aria-label="Close"
            >
              <svg width="11" height="11" viewBox="0 0 12 12" fill="none" aria-hidden>
                <path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              </svg>
            </RD.Close>
          </div>
          {children}
        </RD.Content>
      </RD.Portal>
    </RD.Root>
  );
}

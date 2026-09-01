import * as RT from "@radix-ui/react-tooltip";
import type { ReactNode } from "react";
import { cn } from "../../lib/utils";

/** shadcn-style tooltip on Radix, for icon-only controls and truncated labels. */
export function Tooltip({
  content,
  children,
  side = "bottom",
  delay = 250,
}: {
  content: ReactNode;
  children: ReactNode;
  side?: "top" | "bottom" | "left" | "right";
  delay?: number;
}) {
  if (!content) return <>{children}</>;
  return (
    <RT.Provider delayDuration={delay} skipDelayDuration={0}>
      <RT.Root>
        <RT.Trigger asChild>{children}</RT.Trigger>
        <RT.Portal>
          <RT.Content
            side={side}
            sideOffset={6}
            className={cn(
              "z-[120] max-w-[16rem] rounded-md border border-line bg-surface px-2 py-1 text-xs text-ink shadow-1",
              "data-[state=delayed-open]:animate-[skel_0ms] select-none",
            )}
          >
            {content}
            <RT.Arrow className="fill-line" />
          </RT.Content>
        </RT.Portal>
      </RT.Root>
    </RT.Provider>
  );
}

import type { ReactNode } from "react";

/**
 * The bottom-centre "you clicked this" panel used on both map dashboards.
 * Title + monospace sub-line + dismiss, then whatever the caller wants below a
 * hairline rule (a detail paragraph, a cross-reference to Maxar imagery, a
 * link out to the source).
 */
export default function FeatureCallout({
  title,
  subtitle,
  onDismiss,
  children,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  onDismiss: () => void;
  children?: ReactNode;
}) {
  return (
    <div className="absolute bottom-16 left-1/2 z-20 w-[min(440px,calc(100%-1.5rem))] -translate-x-1/2 sm:bottom-14">
      <div className="panel enter-pop px-3.5 py-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="truncate text-sm text-ink">{title}</div>
            {subtitle != null && (
              <div className="tnum text-2xs text-ink-faint">{subtitle}</div>
            )}
          </div>
          <button
            onClick={onDismiss}
            className="pressable -m-1 grid h-6 w-6 shrink-0 place-items-center rounded-md text-ink-faint hover:text-ink"
            aria-label="Dismiss"
          >
            <svg width="10" height="10" viewBox="0 0 12 12" fill="none" aria-hidden>
              <path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

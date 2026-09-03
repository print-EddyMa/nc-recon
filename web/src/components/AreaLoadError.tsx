/**
 * Terminal state for the area screens (damage map, review, summary) when the
 * assessment for the selected area can't be fetched — the service is down, slow
 * past the timeout, or returned an error. Without this the screens sit on a
 * skeleton forever.
 */
export default function AreaLoadError({
  areaName,
  detail,
  onRetry,
}: {
  areaName: string;
  detail?: string | null;
  onRetry: () => void;
}) {
  return (
    <div className="mx-auto grid h-full max-w-md place-items-center px-6 text-center">
      <div>
        <div className="section-title mb-2">Couldn&rsquo;t load this area</div>
        <p className="text-sm text-ink-dim">
          The assessment for <span className="text-ink">{areaName}</span> didn&rsquo;t load.
          The pipeline service may be offline or still starting. The rest of the app
          still works.
        </p>
        {detail && (
          <pre className="mt-3 overflow-x-auto rounded bg-surface-2 px-2.5 py-2 text-left text-2xs text-ink-faint">
            {detail}
          </pre>
        )}
        <button
          onClick={onRetry}
          className="pressable mt-4 rounded-md border border-line px-3 py-1.5 text-xs text-ink-dim hover:border-accent hover:text-ink"
        >
          Retry
        </button>
      </div>
    </div>
  );
}

import { useState } from "react";

/**
 * Inline "paste an optional API key" control, kept in localStorage by the
 * caller. Used for the NASA FIRMS map key (global Live Monitor) and the NC
 * State Climate Office CLOUDS hash (NC dashboard), same shape, one component.
 *
 * When no key is set it shows a compact add-form; once set, a quiet remove
 * link. Both sit on a hairline top border so they read as a sub-section of a
 * `.panel`.
 */
export default function KeyForm({
  hasKey,
  placeholder,
  addLabel = "add",
  removeLabel = "remove key",
  onAdd,
  onRemove,
}: {
  hasKey: boolean;
  placeholder: string;
  addLabel?: string;
  removeLabel?: string;
  onAdd: (value: string) => void;
  onRemove: () => void;
}) {
  const [draft, setDraft] = useState("");

  if (hasKey) {
    return (
      <button
        onClick={onRemove}
        className="pressable mt-2 border-t border-line pt-2 text-2xs text-ink-faint hover:text-ink"
      >
        {removeLabel}
      </button>
    );
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        const v = draft.trim();
        if (v) {
          onAdd(v);
          setDraft("");
        }
      }}
      className="mt-2.5 flex gap-1.5 border-t border-line pt-2.5"
    >
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        placeholder={placeholder}
        className="min-w-0 flex-1 rounded-md border border-line bg-canvas px-2 py-1 text-2xs text-ink outline-none placeholder:text-ink-faint focus-visible:border-accent"
      />
      <button
        type="submit"
        disabled={!draft.trim()}
        className="pressable rounded-md border border-line px-2 py-1 text-2xs text-ink-dim hover:text-ink disabled:opacity-40"
      >
        {addLabel}
      </button>
    </form>
  );
}

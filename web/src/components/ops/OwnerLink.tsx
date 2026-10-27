// Operator side of the owner evidence record: issue a private, expiring link
// for one building to an owner or renter whom a partner has verified (legal
// aid intake, a county call centre). Groma does not verify identity itself.
import { useState } from "react";
import { toast } from "sonner";
import { authHeaders } from "../../lib/ops";
import { issueOwnerLink, recordUrl, revokeOwnerLink, type OwnerLink as Link } from "../../lib/owner";
import { Button } from "../ui/kit";

export default function OwnerLink({ areaId, ncrId }: { areaId: string; ncrId: string }) {
  const [days, setDays] = useState(30);
  const [busy, setBusy] = useState(false);
  const [link, setLink] = useState<Link | null>(null);
  const url = link ? recordUrl(link.path) : "";

  const make = async () => {
    setBusy(true);
    try {
      setLink(await issueOwnerLink(areaId, ncrId, days, authHeaders()));
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const copy = () =>
    navigator.clipboard
      .writeText(url)
      .then(() => toast.success("Link copied"))
      .catch(() => toast.error("Copying is blocked here: select the link and copy it"));
  const withdraw = async () => {
    if (!link) return;
    try {
      await revokeOwnerLink(link.id, authHeaders());
      toast.success("Link withdrawn");
      setLink(null);
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <div className="grid gap-2 text-xs">
      <p className="text-ink-dim">
        Only for the owner or renter, after a partner has checked who they are. The link shows this building's call,
        imagery and evidence, and stops working when it expires.
      </p>
      {!link ? (
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-ink-dim">
            Works for
            <select
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              className="h-7 rounded border border-line-strong bg-surface px-1 text-ink"
            >
              {[7, 30, 60, 90].map((d) => (
                <option key={d} value={d}>
                  {d} days
                </option>
              ))}
            </select>
          </label>
          <Button size="sm" onClick={make} disabled={busy}>
            {busy ? "Creating…" : "Create owner link"}
          </Button>
        </div>
      ) : (
        <div className="grid gap-1.5">
          <input
            readOnly
            value={url}
            aria-label="Owner record link"
            onFocus={(e) => e.currentTarget.select()}
            className="h-7 w-full rounded border border-line-strong bg-surface-2 px-1.5 font-mono text-[11px] text-ink"
          />
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="primary" onClick={copy}>
              Copy link
            </Button>
            <Button size="sm" variant="ghost" onClick={withdraw}>
              Withdraw
            </Button>
            <span className="text-ink-faint">until {link.expires_utc.slice(0, 10)} · id {link.id}</span>
          </div>
        </div>
      )}
    </div>
  );
}

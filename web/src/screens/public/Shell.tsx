// The frame for Groma's public pages (check a street, the index, an owner's
// record), matching the website: a light top bar, one sans family, a quiet
// footer with links. No operator chrome, nothing that needs a token.
import type { ReactNode } from "react";
import { GromaMark } from "../../components/ui/GromaMark";
import { DISCLAIMER } from "../../lib/ops";

const LINKS = [
  { href: "#/check", label: "Check a street" },
  { href: "#/index", label: "Damage index" },
];

export function PublicShell({
  hero,
  children,
  current,
}: {
  hero?: ReactNode;
  children: ReactNode;
  current?: "check" | "index" | "record";
}) {
  return (
    <div className="h-full overflow-y-auto bg-surface print:h-auto print:overflow-visible">
      <header className="sticky top-0 z-10 border-b border-line bg-surface/90 backdrop-blur print:hidden">
        <div className="public-wrap flex h-16 items-center gap-4 sm:gap-8">
          <a href="#/check" className="flex items-center gap-2 text-ink" aria-label="Groma, check a street">
            <GromaMark className="h-[26px] w-[26px]" />
            <span className="text-[19px] font-semibold tracking-[-0.01em]">Groma</span>
          </a>
          <nav aria-label="Public pages" className="ml-auto flex items-center gap-4 text-[14px] sm:gap-7 sm:text-[15px]">
            {LINKS.map((l) => (
              <a
                key={l.href}
                href={l.href}
                aria-current={current && l.href.endsWith(current) ? "page" : undefined}
                className="whitespace-nowrap text-ink-dim hover:text-ink aria-[current=page]:font-medium aria-[current=page]:text-ink"
              >
                {l.label}
              </a>
            ))}
          </nav>
        </div>
      </header>
      {hero && (
        <section className="border-b border-line">
          <div className="public-wrap pb-12 pt-12 sm:pb-16 sm:pt-20">{hero}</div>
        </section>
      )}
      <main id="main" className="public-wrap py-10 sm:py-14">
        {children}
      </main>
      <footer className="border-t border-line bg-canvas print:hidden">
        <div className="public-wrap grid gap-4 py-8 text-sm text-ink-faint sm:grid-cols-[1fr_auto] sm:items-end">
          <p className="max-w-[60ch]">{DISCLAIMER}</p>
          <div className="flex flex-wrap gap-x-6 gap-y-2">
            {LINKS.map((l) => (
              <a key={l.href} href={l.href} className="whitespace-nowrap text-ink-dim hover:text-ink">
                {l.label}
              </a>
            ))}
            <a href="#/" className="whitespace-nowrap text-ink-dim hover:text-ink">
              For responders
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}

/** The page title on a public page: large, medium weight, tight. */
export function HeroTitle({ children }: { children: ReactNode }) {
  return (
    <h1 className="max-w-[16ch] text-[clamp(2.6rem,6vw,4.75rem)] font-medium leading-[1.02] tracking-[-0.035em] text-ink">
      {children}
    </h1>
  );
}

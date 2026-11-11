import Link from "next/link";
import { CTA_PRIMARY, CTA_SECONDARY, WRAP } from "@/components/home/styles";
import { TYPE_CHIP } from "@/lib/entity";
import { BADGE_CLASS } from "@/lib/review";

const CHIP = "inline-flex items-center rounded-md border px-2 py-0.5 text-[13px]";

/** The promise, who it is for, and the two ways in (M5 §5.7 item 1). */
export function Hero() {
  return (
    <section aria-labelledby="home-hero" className="border-b border-border bg-linear-to-b from-panel to-background">
      <div className={`${WRAP} grid items-center gap-10 py-14 sm:py-20 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)] lg:gap-14`}>
        <div>
          <p className="m-0 text-xs font-semibold uppercase tracking-[1.4px] text-accent">Sagaloom</p>
          <h1 id="home-hero" className="m-0 mt-3 font-heading text-[38px] font-medium leading-[1.08] sm:text-5xl lg:text-[56px]">
            A continuity editor for your fictional world: you decide, it checks.
          </h1>
          <p className="m-0 mt-5 text-lg text-prose">For authors, fan-fiction writers and solo game masters.</p>
          <p className="m-0 mt-3 max-w-xl text-[15px] leading-relaxed text-prose-muted">
            Tell it a new fact in plain words. Sagaloom checks it against everything already true in your world, shows
            you each clash with the entry it comes from, and writes nothing until you say so.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link href="/sign-up" className={CTA_PRIMARY}>
              Sign up free
            </Link>
            <Link href="/sign-in" className={CTA_SECONDARY}>
              Sign in
            </Link>
          </div>
          <p className="m-0 mt-4 text-[13px] text-muted-foreground">
            Every new account starts with Velmar, a small sample world to try it on.
          </p>
        </div>
        <HeroSample />
      </div>
    </section>
  );
}

/** A glance at what a check looks like; the full, real card is in the preview below. */
function HeroSample() {
  return (
    <figure className="m-0 overflow-hidden rounded-[14px] border border-conflict-line bg-panel-2 shadow-2xl shadow-black/30">
      <div className="flex flex-wrap items-center gap-2 border-b border-conflict-line bg-conflict-bg px-4 py-2.5">
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${BADGE_CLASS.conflict}`}>Conflict</span>
        <span className="font-heading text-[15px] font-semibold">Commit to canon?</span>
      </div>
      <div className="flex flex-col gap-3 px-4 py-4 text-sm">
        <div className="self-end rounded-[14px_14px_4px_14px] border border-user-line bg-panel-3 px-3.5 py-2.5">
          Velmar has three moons.
        </div>
        <dl className="m-0 grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2">
          <dt className="text-[11px] uppercase tracking-[0.9px] text-muted-foreground">In canon</dt>
          <dd className="m-0 flex flex-wrap items-center gap-1.5">
            One moon <span aria-hidden="true" className="text-muted-foreground">·</span>
            <span className={`${CHIP} ${TYPE_CHIP.place}`}>Ister, the red moon</span>
            <span className="text-xs text-muted-foreground">ent_0012</span>
          </dd>
          <dt className="text-[11px] uppercase tracking-[0.9px] text-muted-foreground">Proposed</dt>
          <dd className="m-0 font-semibold text-conflict-text-2">Three moons</dd>
        </dl>
        <div className="flex flex-wrap gap-2 border-t border-border pt-3 text-[13px]">
          {["Approve", "Edit", "Reject", "Save as myth"].map((a) => (
            <span key={a} className="rounded-lg border border-border-strong px-3 py-1.5 text-prose-muted">
              {a}
            </span>
          ))}
        </div>
      </div>
      <figcaption className="border-t border-border px-4 py-2 text-xs text-muted-foreground">
        You choose what becomes canon.
      </figcaption>
    </figure>
  );
}

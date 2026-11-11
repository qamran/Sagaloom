import Link from "next/link";
import { Compare } from "@/components/home/Compare";
import { Features } from "@/components/home/Features";
import { CTA_PRIMARY, CTA_SECONDARY, GITHUB_URL, WRAP } from "@/components/home/styles";
import { Hero } from "@/components/home/Hero";
import { Loop } from "@/components/home/Loop";
import { Preview } from "@/components/home/Preview";
import type { PublicPreview } from "@/lib/types";

/**
 * The public home page for signed-out visitors (M5 §5.7): hero, the loop, a recorded read-only
 * preview, features, the comparison and a footer. Its only links go to sign-in, sign-up and GitHub;
 * nothing here calls the API from the browser.
 */
export function HomePage({ preview }: { preview: PublicPreview | null }) {
  return (
    <>
      <main className="flex-1">
        <Hero />
        <Loop />
        <Preview preview={preview} />
        <Features />
        <Compare />
      </main>
      <footer className="border-t border-border bg-panel">
        <div className={`${WRAP} flex flex-col gap-8 py-12`}>
          <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="m-0 font-heading text-[26px] font-medium leading-tight">Check your own world.</h2>
              <p className="m-0 mt-1.5 text-muted-foreground">
                Every new account starts with a copy of Velmar to try it on.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <Link href="/sign-up" className={CTA_PRIMARY}>
                Sign up free
              </Link>
              <Link href="/sign-in" className={CTA_SECONDARY}>
                Sign in
              </Link>
            </div>
          </div>
          <div className="flex flex-col gap-2 border-t border-border pt-6 text-[13px] text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
            <p className="m-0">Your canon stays on the server you run it on.</p>
            <a href={GITHUB_URL} className="self-start sm:self-auto" rel="noopener noreferrer">
              Sagaloom on GitHub
            </a>
          </div>
        </div>
      </footer>
    </>
  );
}

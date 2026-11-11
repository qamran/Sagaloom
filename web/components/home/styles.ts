// Shared by the home page sections (M5 §5.7): the page width and the two call-to-action looks,
// matching the Header's Sign in / Sign up free links.

export const WRAP = "mx-auto w-full max-w-6xl px-4 sm:px-6";
export const GITHUB_URL = "https://github.com/qamran/Sagaloom";

const CTA =
  "inline-flex min-h-11 items-center justify-center rounded-lg px-5 text-sm no-underline hover:no-underline";
export const CTA_PRIMARY = `${CTA} bg-accent font-semibold text-accent-foreground hover:text-accent-foreground hover:brightness-110`;
export const CTA_SECONDARY = `${CTA} border border-border-strong text-foreground hover:bg-panel-3 hover:text-foreground`;

/** A section's small label above its heading. */
export const EYEBROW = "m-0 text-xs font-semibold uppercase tracking-[1.4px] text-accent";
export const H2 = "m-0 mt-2 font-heading text-[30px] font-medium leading-tight sm:text-4xl";
export const LEDE = "m-0 mt-3 max-w-2xl text-[15px] leading-relaxed text-prose-muted";

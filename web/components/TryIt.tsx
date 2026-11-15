import Link from "next/link";
import { chatHref } from "@/lib/toolTests";

/** A message to try in Chat: the text, a link that puts it in the Chat box, and what to expect.
 * `label` names the case when a panel shows more than one ("Should be blocked"). */
export function TryIt({ prompt, expect, label = "Try it" }: { prompt: string; expect: string; label?: string }) {
  return (
    <div className="flex flex-col gap-2 rounded-lg bg-well px-3 py-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-[0.8px] text-muted-foreground">{label}</span>
        <Link
          href={chatHref(prompt)}
          className="rounded-md border border-border-strong px-2.5 py-1 text-xs text-foreground no-underline hover:bg-panel-3 hover:text-foreground hover:no-underline"
        >
          Open in Chat <span aria-hidden="true">→</span>
        </Link>
      </div>
      <p className="m-0 text-[13px] leading-snug text-foreground">{prompt}</p>
      <p className="m-0 text-xs text-muted-foreground">
        <span className="text-foreground">You should see:</span> {expect}
      </p>
    </div>
  );
}

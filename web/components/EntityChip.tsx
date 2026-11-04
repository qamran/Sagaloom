import Link from "next/link";
import { TYPE_CHIP } from "@/lib/entity";
import type { EntryType } from "@/lib/types";

const BASE =
  "inline-flex items-center rounded-md border px-2 py-0.5 text-[13px] no-underline hover:brightness-125";

/** An entry named in the UI. Colour marks the type; the type is also in the accessible name. */
export function EntityChip({ type, name, href }: { type: EntryType; name: string; href?: string }) {
  const cls = `${BASE} ${TYPE_CHIP[type]}`;
  const inner = (
    <>
      <span className="sr-only">{type}</span> <span>{name}</span>
    </>
  );
  if (href) {
    return (
      <Link href={href} className={cls}>
        {inner}
      </Link>
    );
  }
  return <span className={cls}>{inner}</span>;
}

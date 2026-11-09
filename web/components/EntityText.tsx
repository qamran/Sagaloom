import { EntityChip } from "@/components/EntityChip";
import { linkEntities, type Named } from "@/lib/mentions";

/** Text with the entries it names shown as chips. Secret entries stay plain text while hidden. */
export function EntityText({ text, entries, showSecrets }: { text: string; entries?: Named[]; showSecrets: boolean }) {
  if (!entries || entries.length === 0) return <>{text}</>;
  return (
    <>
      {linkEntities(text, entries, showSecrets).map((p, i) =>
        typeof p === "string" ? (
          <span key={i}>{p}</span>
        ) : (
          <EntityChip key={i} type={p.entry.type} name={p.text} href={`/canon/${p.entry.id}`} />
        ),
      )}
    </>
  );
}

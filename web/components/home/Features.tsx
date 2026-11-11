import { EYEBROW, H2, WRAP } from "@/components/home/styles";

const FEATURES: { title: string; text: string; tone: string }[] = [
  {
    title: "Contradiction check on every change",
    text: "Each proposed write is checked fact against fact before you see it, and every flag cites the entry IDs and quotes both sides.",
    tone: "bg-conflict",
  },
  {
    title: "Human approval before anything is written",
    text: "The agent drafts; you approve, edit or reject. Nothing reaches canon without your decision.",
    tone: "bg-accent",
  },
  {
    title: "Myths, rumours and secrets",
    text: "Record what people in your world believe without making it true, and keep secrets masked on screen until you show them.",
    tone: "bg-myth",
  },
  {
    title: "Import your notes and fan wikis",
    text: "Paste your notes or a fan wiki page. Sagaloom stores your own words verbatim and keeps where each entry came from.",
    tone: "bg-rule",
  },
  {
    title: "See what every step costs",
    text: "Each turn shows its tokens and cost per model, and the header shows this month's spend against your budget.",
    tone: "bg-event",
  },
];

/** What it does, in five cards (M5 §5.7 item 4). */
export function Features() {
  return (
    <section aria-labelledby="home-features" className="border-t border-border py-16 sm:py-20">
      <div className={WRAP}>
        <p className={EYEBROW}>Features</p>
        <h2 id="home-features" className={H2}>
          Built to keep your world consistent
        </h2>
        <ul className="m-0 mt-10 grid list-none gap-4 p-0 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <li key={f.title} className="flex flex-col gap-2.5 rounded-xl border border-border bg-panel-2 px-5 py-5">
              <span aria-hidden="true" className={`h-1 w-8 rounded-full ${f.tone}`} />
              <h3 className="m-0 font-heading text-[19px] font-semibold leading-snug">{f.title}</h3>
              <p className="m-0 text-[13px] leading-relaxed text-prose-muted">{f.text}</p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

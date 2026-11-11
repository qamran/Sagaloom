import { EYEBROW, H2, LEDE, WRAP } from "@/components/home/styles";

const STEPS: { title: string; text: string }[] = [
  { title: "You state a fact", text: "Write it in chat the way you would say it: “Velmar has three moons.”" },
  {
    title: "Sagaloom checks it against canon",
    text: "The change is compared fact by fact with what is already true, and every clash cites the entry it comes from.",
  },
  {
    title: "You approve, edit, reject or save it as a myth",
    text: "Nothing is written until you decide. A myth keeps the idea as something people in your world believe.",
  },
  { title: "It becomes canon", text: "The entry is saved with its facts, and the next change is checked against it too." },
];

/** The four steps of every change (M5 §5.7 item 2). */
export function Loop() {
  return (
    <section aria-labelledby="home-loop" className="py-16 sm:py-20">
      <div className={WRAP}>
        <p className={EYEBROW}>The loop</p>
        <h2 id="home-loop" className={H2}>
          How it works
        </h2>
        <p className={LEDE}>The same four steps for every change, whether it is one fact or a whole imported page.</p>
        <ol aria-label="The loop" className="m-0 mt-10 grid list-none gap-4 p-0 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((s, i) => (
            <li key={s.title} className="flex flex-col gap-3 rounded-xl border border-border bg-panel-2 px-5 py-5">
              <span
                aria-hidden="true"
                className="flex size-8 items-center justify-center rounded-full border border-accent/60 font-heading text-[15px] font-semibold text-accent"
              >
                {i + 1}
              </span>
              <h3 className="m-0 font-heading text-[19px] font-semibold leading-snug">{s.title}</h3>
              <p className="m-0 text-[13px] leading-relaxed text-prose-muted">{s.text}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

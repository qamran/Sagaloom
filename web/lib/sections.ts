import { HEADING_OPENER, isImportedHeading } from "@/lib/imported";

const OPENER = new RegExp(HEADING_OPENER);

export interface Section {
  heading: string;
  text: string;
  imported: boolean;
}

/** Split an entry body into cards at each `## ` line. Text before the first one is the Description. */
export function sectionsOf(body: string): Section[] {
  const sections: Section[] = [{ heading: "Description", text: "", imported: false }];
  const lines: string[][] = [[]];
  for (const line of body.split("\n")) {
    if (OPENER.test(line)) {
      const heading = line.replace(OPENER, "").trim();
      sections.push({ heading, text: "", imported: isImportedHeading(heading) });
      lines.push([]);
    } else {
      lines[lines.length - 1].push(line);
    }
  }
  const out = sections.map((s, i) => ({ ...s, text: lines[i].join("\n").trim() }));
  // A body that opens with a heading has no description: drop the empty leading card.
  return out.length > 1 && out[0].text === "" ? out.slice(1) : out;
}

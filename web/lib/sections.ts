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
    if (line.startsWith("## ")) {
      const heading = line.slice(3).trim();
      sections.push({ heading, text: "", imported: heading.startsWith("Imported from ") });
      lines.push([]);
    } else {
      lines[lines.length - 1].push(line);
    }
  }
  return sections.map((s, i) => ({ ...s, text: lines[i].join("\n").trim() }));
}

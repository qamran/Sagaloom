"use client";

import { useId, useState } from "react";

export const IMPORT_CAP = 100_000;
export const OVER_CAP = "Over the 100,000-character limit for one import. Split it into smaller imports.";
export const WRONG_TYPE = "Only .md and .txt files can be imported.";
const EMPTY_FILE = "That file has no text to import.";

const CARD = "flex min-w-0 flex-[1_1_300px] flex-col gap-3 rounded-xl border border-border bg-panel-2 px-5 py-[18px]";
const BTN =
  "min-h-11 self-start rounded-lg bg-accent px-4 text-[13px] font-semibold text-accent-foreground hover:brightness-110 disabled:opacity-50";

export type ImportBody = { text: string; filename?: string };

type Props = {
  kind: "paste" | "upload" | "wiki";
  disabled?: boolean;
  onExtract?: (body: ImportBody) => void;
};

const count = (n: number) => n.toLocaleString("en-US");

function readText(file: File): Promise<string> {
  if (typeof file.text === "function") return file.text();
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result ?? ""));
    r.onerror = () => reject(r.error);
    r.readAsText(file);
  });
}

function Paste({ disabled, onExtract }: Pick<Props, "disabled" | "onExtract">) {
  const id = useId();
  const [text, setText] = useState("");
  const over = text.length > IMPORT_CAP;
  const blank = text.trim() === "";
  return (
    <section aria-label="Paste text" className={CARD}>
      <h2 className="m-0 font-heading text-xl font-medium">Paste text</h2>
      <p className="m-0 text-[13px] text-muted-foreground">Notes, a draft chapter, a session log. Your wording stays yours.</p>
      <label htmlFor={id} className="sr-only">
        Text to import
      </label>
      <textarea
        id={id}
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={8}
        className="min-h-40 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
      />
      <div className={`text-xs ${over ? "text-conflict" : "text-muted-foreground"}`}>
        {count(text.length)} / {count(IMPORT_CAP)} characters
      </div>
      {over && (
        <p role="alert" className="m-0 text-sm text-conflict">
          {OVER_CAP}
        </p>
      )}
      <button type="button" disabled={disabled || blank || over} onClick={() => onExtract?.({ text })} className={BTN}>
        Extract entries
      </button>
    </section>
  );
}

function Upload({ disabled, onExtract }: Pick<Props, "disabled" | "onExtract">) {
  const id = useId();
  const [staged, setStaged] = useState<{ text: string; filename: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function pick(file: File | undefined) {
    setStaged(null);
    setError(null);
    if (!file) return;
    if (!/\.(md|txt)$/i.test(file.name)) {
      setError(WRONG_TYPE);
      return;
    }
    let text: string;
    try {
      text = await readText(file);
    } catch {
      setError("Could not read that file.");
      return;
    }
    if (text.trim() === "") setError(EMPTY_FILE);
    else if (text.length > IMPORT_CAP) setError(OVER_CAP);
    else setStaged({ text, filename: file.name });
  }

  return (
    <section aria-label="Upload a file" className={CARD}>
      <h2 className="m-0 font-heading text-xl font-medium">Upload a file</h2>
      <p className="m-0 text-[13px] text-muted-foreground">A .md or .txt file, up to {count(IMPORT_CAP)} characters.</p>
      <label htmlFor={id} className="text-[13px]">
        Choose a file
      </label>
      <input
        id={id}
        type="file"
        accept=".md,.txt"
        onChange={(e) => {
          const input = e.currentTarget;
          const file = input.files?.[0];
          // Clear the value so the same file can be chosen again (the browser fires no change event otherwise).
          input.value = "";
          void pick(file);
        }}
        className="min-h-11 text-sm"
      />
      {staged && (
        <div className="text-xs text-muted-foreground">
          {staged.filename} · {count(staged.text.length)} characters
        </div>
      )}
      {error && (
        <p role="alert" className="m-0 text-sm text-conflict">
          {error}
        </p>
      )}
      <button type="button" disabled={disabled || !staged} onClick={() => staged && onExtract?.(staged)} className={BTN}>
        Extract entries
      </button>
    </section>
  );
}

/** One way to bring text in: paste it, upload a file, or (later) point at a fan wiki. */
export function ImportSourceCard({ kind, disabled, onExtract }: Props) {
  if (kind === "paste") return <Paste disabled={disabled} onExtract={onExtract} />;
  if (kind === "upload") return <Upload disabled={disabled} onExtract={onExtract} />;
  return (
    <section aria-label="Fan wiki" className={CARD}>
      <h2 className="m-0 font-heading text-xl font-medium">Fan wiki</h2>
      <p className="m-0 text-[13px] text-muted-foreground">Pull a page from a fan wiki, with its licence kept.</p>
      <span className="self-start rounded-full border border-border-strong px-2.5 py-0.5 text-xs text-muted-foreground">
        Coming soon
      </span>
    </section>
  );
}

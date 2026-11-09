"use client";

import { useLayoutEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { TYPE_DOT } from "@/lib/entity";
import { suggestEntries, type Named } from "@/lib/mentions";

// An @ at the start or after whitespace, with the query typed so far, ending at the caret.
const TRIGGER = /(^|\s)@([^\s@]*)$/;

/** The chat input. Enter sends, Shift+Enter adds a line, @ suggests entries (the message stays plain text). */
export function Composer({
  onSend,
  disabled,
  hint,
  placeholder,
  prefill,
  entries,
  showSecrets = false,
}: {
  onSend: (text: string) => void;
  disabled?: boolean;
  /** Shown under the input; replaces the default reassurance line. */
  hint?: string | null;
  placeholder?: string;
  /** Text to put in the box once (a Studio "Try it" link); the author still has to send it. */
  prefill?: string | null;
  /** The world's entries, for @ suggestions. */
  entries?: Named[];
  /** Whether secret entries may be suggested (the thread's world toggle). */
  showSecrets?: boolean;
}) {
  const [text, setText] = useState("");
  const [applied, setApplied] = useState<string | null>(null);
  const [caret, setCaret] = useState(0);
  // -1: nothing highlighted yet, so the first ArrowDown lands on the first option.
  const [active, setActive] = useState(-1);
  const [dismissed, setDismissed] = useState(false);
  const box = useRef<HTMLTextAreaElement>(null);
  const nextCaret = useRef<number | null>(null);
  if (prefill && prefill !== applied) {
    setApplied(prefill);
    setText(prefill);
    setCaret(prefill.length);
  }

  const trigger = TRIGGER.exec(text.slice(0, caret));
  const options = !dismissed && trigger && entries ? suggestEntries(trigger[2], entries, showSecrets) : [];
  const open = options.length > 0;
  const current = Math.min(active, options.length - 1);
  const chosen = Math.max(current, 0);

  useLayoutEffect(() => {
    if (nextCaret.current !== null && box.current) {
      box.current.setSelectionRange(nextCaret.current, nextCaret.current);
      nextCaret.current = null;
    }
  });

  function pick(entry: Named) {
    if (!trigger) return;
    const start = caret - trigger[2].length - 1;
    const inserted = `${entry.title} `;
    setText(text.slice(0, start) + inserted + text.slice(caret));
    nextCaret.current = start + inserted.length;
    setCaret(start + inserted.length);
    setActive(-1);
  }

  function submit(e?: FormEvent) {
    e?.preventDefault();
    const value = text.trim();
    if (!value || disabled) return;
    onSend(value);
    setText("");
    setCaret(0);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (open && !e.nativeEvent.isComposing) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        const step = e.key === "ArrowDown" ? 1 : -1;
        setActive(current < 0 && step < 0 ? options.length - 1 : (current + step + options.length) % options.length);
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        pick(options[chosen]);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        setDismissed(true);
        return;
      }
    }
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <form onSubmit={submit} className="mx-auto flex w-full max-w-[860px] flex-col gap-2">
      <div className="flex items-end gap-2.5">
        <label htmlFor="composer" className="sr-only">
          Message Sagaloom
        </label>
        <div className="relative flex-1">
          <textarea
            id="composer"
            ref={box}
            rows={2}
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setCaret(e.target.selectionStart);
              setActive(-1);
              setDismissed(false);
            }}
            onSelect={(e) => setCaret(e.currentTarget.selectionStart)}
            onKeyDown={onKeyDown}
            disabled={disabled}
            maxLength={4000}
            role="combobox"
            aria-autocomplete="list"
            aria-haspopup="listbox"
            aria-controls={open ? "composer-mentions" : undefined}
            aria-expanded={open}
            aria-activedescendant={open && current >= 0 ? `composer-mention-${options[current].id}` : undefined}
            aria-describedby="composer-hint"
            placeholder={placeholder ?? "Ask about your world, add a fact, or brainstorm."}
            className="min-h-12 w-full resize-none rounded-xl border border-border bg-panel-2 px-3.5 py-3 text-sm text-foreground placeholder:text-muted-foreground disabled:opacity-60"
          />
          {open && (
            <ul
              id="composer-mentions"
              role="listbox"
              aria-label="Entry suggestions"
              className="absolute bottom-full left-0 z-10 mb-1 max-h-56 w-full overflow-y-auto rounded-lg border border-border-strong bg-panel-2 py-1 text-sm shadow-lg"
            >
              {options.map((o, i) => (
                <li
                  key={o.id}
                  id={`composer-mention-${o.id}`}
                  role="option"
                  aria-selected={i === current}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    pick(o);
                  }}
                  className={`flex cursor-pointer items-center gap-2 px-3 py-2 ${i === current ? "bg-panel-3" : ""}`}
                >
                  <span aria-hidden="true" className={`size-2 rounded-full ${TYPE_DOT[o.type]}`} />
                  <span>{o.title}</span>
                  <span className="text-xs text-muted-foreground">{o.type}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <button
          type="submit"
          aria-label="Send"
          disabled={disabled || !text.trim()}
          className="flex size-12 shrink-0 items-center justify-center rounded-[10px] bg-accent disabled:opacity-50"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            className="stroke-background"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M5 12h14M13 6l6 6-6 6" />
          </svg>
        </button>
      </div>
      <div id="composer-hint" className={`text-xs ${hint ? "text-conflict" : "text-muted-foreground"}`}>
        {hint ?? "Nothing enters canon until you approve it."}
      </div>
    </form>
  );
}

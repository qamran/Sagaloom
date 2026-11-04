"use client";

import { useState, type FormEvent, type KeyboardEvent } from "react";

/** The chat input. Enter sends, Shift+Enter adds a line. */
export function Composer({
  onSend,
  disabled,
  hint,
  placeholder,
}: {
  onSend: (text: string) => void;
  disabled?: boolean;
  /** Shown under the input; replaces the default reassurance line. */
  hint?: string | null;
  placeholder?: string;
}) {
  const [text, setText] = useState("");

  function submit(e?: FormEvent) {
    e?.preventDefault();
    const value = text.trim();
    if (!value || disabled) return;
    onSend(value);
    setText("");
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
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
        <textarea
          id="composer"
          rows={2}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={disabled}
          maxLength={4000}
          aria-describedby="composer-hint"
          placeholder={placeholder ?? "Ask about your world, add a fact, or brainstorm."}
          className="min-h-12 flex-1 resize-none rounded-xl border border-border bg-panel-2 px-3.5 py-3 text-sm text-foreground placeholder:text-muted-foreground disabled:opacity-60"
        />
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
            stroke="#121514"
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

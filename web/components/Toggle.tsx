/** An on/off switch that looks like one: a track with a sliding knob, the state in words, and a
 * pointer cursor (a "not allowed" cursor while disabled). Only for settings that can change: a
 * fixed state is shown as plain text, not as a switch. */
export function Toggle({
  label,
  on,
  onChange,
  disabled = false,
}: {
  /** The accessible name (e.g. the tool's name). */
  label: string;
  on: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!on)}
      className={`inline-flex shrink-0 items-center gap-2 rounded-full py-1 pl-1 pr-2 text-xs font-medium focus-visible:outline-2 focus-visible:outline-offset-2 ${
        disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer hover:bg-panel-3"
      }`}
    >
      <span
        aria-hidden="true"
        className={`relative inline-block h-5 w-9 rounded-full transition-colors ${on ? "bg-place" : "bg-border-strong"}`}
      >
        <span
          data-knob
          className={`absolute left-0 top-0.5 size-4 rounded-full bg-white shadow transition-transform ${
            on ? "translate-x-[18px]" : "translate-x-0.5"
          }`}
        />
      </span>
      <span className={on ? "text-foreground" : "text-muted-foreground"}>{on ? "On" : "Off"}</span>
    </button>
  );
}

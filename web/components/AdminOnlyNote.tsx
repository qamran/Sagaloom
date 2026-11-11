/** Shown under a developer-settings panel whose controls are disabled for a non-admin (spec 5.5). */
export const ADMIN_ONLY = "Only the admin can change developer settings.";

export function AdminOnlyNote() {
  return <p className="m-0 text-xs text-muted-foreground">{ADMIN_ONLY}</p>;
}

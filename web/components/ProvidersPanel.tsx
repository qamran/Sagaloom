"use client";

import { useState } from "react";
import { AdminOnlyNote } from "@/components/AdminOnlyNote";
import { putFallback, putModel } from "@/lib/api";
import type { AllowedModel, ModelRating, ModelRole, ModelsPayload, ProviderStatus } from "@/lib/types";

const ROLES: { role: ModelRole; label: string; aria: string }[] = [
  { role: "agent", label: "Chat agent", aria: "Model for the chat agent" },
  { role: "judge", label: "Contradiction judge", aria: "Model for the contradiction judge" },
  { role: "extractor", label: "Fact extractor", aria: "Model for the fact extractor" },
];

/** Every role that can have a fallback (R11.G11). The router follows the input guard's. */
const FALLBACK_ROLES: { role: ModelRole; label: string }[] = [
  { role: "agent", label: "Chat agent" },
  { role: "judge", label: "Contradiction judge" },
  { role: "extractor", label: "Fact extractor" },
  { role: "guard", label: "Input guard and router" },
];
const NO_FALLBACK = "";

const GEMINI_OPTION_ID = "gemini-3.5-flash-lite";
const GEMINI_OPTION_LABEL = "gemini-3.5-flash-lite (Gemini, demo only)";

const fmt = (n: number | null | undefined) => (n == null ? "n/a" : n.toFixed(2));

/** Five stars from a benchmark score: 50 and up is five, then one star less per 10 points, never
 * fewer than one. The top model on the index scored about 65. */
export function ratingStars(score: number): string {
  const n = Math.max(1, Math.min(5, Math.floor(score / 10)));
  return "★".repeat(n) + "☆".repeat(5 - n);
}

const ratingText = (r: ModelRating | null | undefined) => (r ? `${ratingStars(r.score)} ${r.score.toFixed(1)}` : "no rating");

/** One dropdown option: the id, the price per 1M tokens in and out, and the rating. */
const optionText = (m: AllowedModel) => `${m.id} · $${fmt(m.price_in)} / $${fmt(m.price_out)} · ${ratingText(m.rating)}`;

const RETRIEVED = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

const HEAD = "bg-raised px-2.5 py-[7px] text-[11px] uppercase tracking-[0.8px] text-muted-foreground";
const CELL = "border-t border-border px-2.5 py-[7px]";

function KeyBadge({ set, on, off }: { set: boolean; on: string; off: string }) {
  return (
    <span
      className={`rounded-full px-2 py-px text-[11px] ${
        set ? "bg-place text-background" : "bg-border-strong text-foreground"
      }`}
    >
      {set ? on : off}
    </span>
  );
}

/** Models and providers (R20.7, R11.G10): a dropdown per role limited to the allowlist. The key
 * status is shown, never a key value. */
export function ProvidersPanel({
  providers,
  models,
  readOnly = false,
}: {
  providers: ProviderStatus[];
  models: ModelsPayload;
  readOnly?: boolean;
}) {
  const [mapping, setMapping] = useState(models.mapping);
  const [fallbacks, setFallbacks] = useState(models.fallbacks);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState<string | null>(null);
  const price = (id: string) => models.allowed.find((m) => m.id === id);
  const openrouter = providers.find((p) => p.name === "OpenRouter");
  const gemini = providers.find((p) => p.name === "Gemini");
  const embeddings = openrouter?.models.find((m) => m.role === "embeddings");

  async function change(role: ModelRole, model: string) {
    setError(null);
    setSaving(role);
    try {
      const next = await putModel(role, model);
      setMapping(next.mapping);
    } catch {
      setError("That model was not saved. Pick one from the list and try again.");
    } finally {
      setSaving(null);
    }
  }

  async function changeFallback(role: ModelRole, model: string) {
    setError(null);
    setSaving(`fallback-${role}`);
    try {
      const next = await putFallback(role, model === NO_FALLBACK ? null : model);
      setFallbacks(next.fallbacks);
    } catch {
      setError("That fallback was not saved. Pick one from the list and try again.");
    } finally {
      setSaving(null);
    }
  }

  return (
    <section
      id="models"
      aria-label="Models and providers"
      className="flex scroll-mt-4 flex-col gap-3 rounded-xl border border-border bg-panel-2 px-5 py-[18px]"
    >
      <h2 className="m-0 font-heading text-[22px] font-medium">Models and providers</h2>
      {openrouter && (
        <div className="flex flex-wrap items-center gap-2.5">
          <span className="font-semibold">{openrouter.name}</span>
          <KeyBadge set={openrouter.key_set} on="Key set" off="Key missing" />
          <span className="text-xs text-muted-foreground">
            {openrouter.role} · choices limited to your allowlist ({models.allowed.length} models)
          </span>
        </div>
      )}
      <div className="grid grid-cols-[minmax(0,0.8fr)_minmax(0,1.6fr)_minmax(0,0.7fr)_minmax(0,0.7fr)] overflow-hidden rounded-lg border border-border text-[13px]">
        <div className={HEAD}>Role</div>
        <div className={HEAD}>Model</div>
        <div className={HEAD}>$ / 1M in · out</div>
        <div className={HEAD}>Rating</div>
        {ROLES.map(({ role, label, aria }) => {
          const p = price(mapping[role]);
          return (
            <div key={role} className="contents">
              <div className={CELL}>{label}</div>
              <div className="border-t border-border px-2.5 py-1">
                <select
                  aria-label={aria}
                  value={mapping[role]}
                  disabled={readOnly || saving === role}
                  onChange={(e) => void change(role, e.target.value)}
                  className="min-h-9 w-full rounded-md border border-border-strong bg-background px-1.5 py-1 font-mono text-xs text-foreground"
                >
                  {models.allowed.map((m) => (
                    <option key={m.id} value={m.id}>
                      {optionText(m)}
                    </option>
                  ))}
                  {gemini && (
                    <option value={GEMINI_OPTION_ID} disabled>
                      {GEMINI_OPTION_LABEL}
                    </option>
                  )}
                </select>
              </div>
              <div className={CELL}>{p ? `${fmt(p.price_in)} · ${fmt(p.price_out)}` : "n/a"}</div>
              <div className={CELL}>
                <span>{ratingText(p?.rating)}</span>
                {p?.rating?.variant && (
                  <span className="block text-[11px] text-muted-foreground">{p.rating.variant} effort</span>
                )}
              </div>
            </div>
          );
        })}
        {embeddings && (
          <>
            <div className={CELL}>Embeddings</div>
            <div className={`${CELL} font-mono text-xs`}>{embeddings.id}</div>
            <div className={CELL}>{fmt(embeddings.price_in)}</div>
            <div className={CELL} />
          </>
        )}
      </div>
      {fallbacks && (
        <>
          <h3 className="m-0 mt-1 text-[15px] font-semibold">Fallback models</h3>
          <p className="m-0 text-xs text-muted-foreground">
            If a role&rsquo;s model is withdrawn from OpenRouter, refused for this key, or its provider is failing, the
            same request goes once to its fallback. The chat shows a note under that turn, and Under the hood keeps
            both calls. Out of credit, a bad key, rate limits and timeouts never switch models: the fallback would fail
            the same way.
          </p>
          <div className="grid grid-cols-[minmax(0,0.8fr)_minmax(0,1.6fr)_minmax(0,0.7fr)_minmax(0,0.7fr)] overflow-hidden rounded-lg border border-border text-[13px]">
            <div className={HEAD}>Role</div>
            <div className={HEAD}>Fallback</div>
            <div className={HEAD}>$ / 1M in · out</div>
            <div className={HEAD}>Rating</div>
            {FALLBACK_ROLES.map(({ role, label }) => {
              const chosen = fallbacks[role] ?? NO_FALLBACK;
              const p = chosen ? price(chosen) : undefined;
              const same = chosen !== NO_FALLBACK && chosen === mapping[role];
              return (
                <div key={role} className="contents">
                  <div className={CELL}>{label}</div>
                  <div className="border-t border-border px-2.5 py-1">
                    <select
                      aria-label={`Fallback model for the ${label.toLowerCase()}`}
                      value={chosen}
                      disabled={readOnly || saving === `fallback-${role}`}
                      onChange={(e) => void changeFallback(role, e.target.value)}
                      className="min-h-9 w-full rounded-md border border-border-strong bg-background px-1.5 py-1 font-mono text-xs text-foreground"
                    >
                      <option value={NO_FALLBACK}>None: fail and say why</option>
                      {models.allowed.map((m) => (
                        <option key={m.id} value={m.id}>
                          {optionText(m)}
                        </option>
                      ))}
                    </select>
                    {same && (
                      <span className="mt-1 block text-[11px] text-conflict">
                        Same as the role&rsquo;s model, so it never helps. Pick another.
                      </span>
                    )}
                  </div>
                  <div className={CELL}>{p ? `${fmt(p.price_in)} · ${fmt(p.price_out)}` : "–"}</div>
                  <div className={CELL}>{p ? ratingText(p.rating) : "–"}</div>
                </div>
              );
            })}
          </div>
        </>
      )}
      {readOnly && <AdminOnlyNote />}
      {error && (
        <p role="alert" className="m-0 text-xs text-conflict">
          {error}
        </p>
      )}
      <p className="m-0 text-xs text-muted-foreground">
        A switch is saved on the server and applies from the next turn. It is recorded on every prompt record.
      </p>
      {models.ratings_source?.url && (
        <p className="m-0 text-xs text-muted-foreground">
          Ratings:{" "}
          <a href={models.ratings_source.url} target="_blank" rel="noreferrer">
            {models.ratings_source.source}
          </a>
          {models.ratings_source.retrieved &&
            `, retrieved ${RETRIEVED.format(new Date(models.ratings_source.retrieved))}`}
          . Higher is better; the top model on the index scored about 65. The medium reasoning-effort score is used
          where there is one. &ldquo;no rating&rdquo; means the model is not on the current index. A general score,
          not a test of continuity checking.
        </p>
      )}
      {gemini && (
        <div className="mt-1 flex flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-2.5">
            <span className="font-semibold">Google Gemini (direct)</span>
            <span className="rounded-full bg-event px-2 py-px text-[11px] text-background">Demo only</span>
            <span className="text-xs text-muted-foreground">
              {gemini.key_set ? "key set" : "not configured"} · {gemini.role}
            </span>
          </div>
          {gemini.notice && <p className="m-0 text-xs text-muted-foreground">{gemini.notice}</p>}
        </div>
      )}
    </section>
  );
}

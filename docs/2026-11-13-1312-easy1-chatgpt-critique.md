# Sagaloom: critique by ChatGPT (Easy 1)

The Sprint 3 brief's Easy task 1: *"Ask ChatGPT to critique your solution from the usability,
security, and prompt-engineering sides."* This is that critique, kept verbatim, with what was sent.

- **Model:** `openai/gpt-6.1-sol` (OpenAI, through OpenRouter)
- **Date:** 2026-11-13 13:13 W. Europe Standard Time
- **Tokens:** 68,965 in, 3,594 out; **cost** US$0.2084; 88 s
- **Code state:** the working tree on `main` at that date, including uncommitted changes

## What was sent

One message: the instructions below, then these files in full, then the 10 screenshots from
the user documentation (`approval-card.png`, `canon-entry.png`, `chat-cost.png`, `compare.png`, `header.png`, `home.png`, `import.png`, `studio.png`, `tips.png`, `under-the-hood.png`). No `.env` file, key or user data was sent.

**One gap:** the instructions say "every prompt it sends", but the contradiction judge's prompt (`JUDGE_SYSTEM`, in `api/sagaloom/check/prompts.py`) was left out by mistake. The critique says so itself under Prompt engineering, problem 5.

| Side | File | Characters |
| --- | --- | --- |
| Usability | `README.md` | 73,690 |
| Usability | `docs/User-Documentation.md` | 22,150 |
| Security | `api/sagaloom/security.py` | 557 |
| Security | `api/sagaloom/auth.py` | 4,311 |
| Security | `api/sagaloom/web/access.py` | 4,955 |
| Security | `api/sagaloom/web/limits.py` | 9,743 |
| Security | `api/sagaloom/budget.py` | 1,684 |
| Security | `web/proxy.ts` | 1,315 |
| Security | `web/app/api/proxy/[...path]/route.ts` | 3,377 |
| Security | `docs/review-notes.md` | 50,561 |
| Prompt engineering | `api/sagaloom/graph/prompts.py` | 1,707 |
| Prompt engineering | `api/sagaloom/router.py` | 3,687 |
| Prompt engineering | `api/sagaloom/guard.py` | 5,409 |
| Prompt engineering | `api/sagaloom/check/contradiction.py` | 10,748 |
| Prompt engineering | `api/sagaloom/importing/extract.py` | 16,262 |
| Prompt engineering | `api/sagaloom/memory.py` | 9,528 |
| Prompt engineering | `api/sagaloom/tools/specs.py` | 3,812 |

<details><summary>The instructions, verbatim</summary>

```text
You are reviewing a student's AI-agent project for a course. The brief's task is:
"Ask ChatGPT to critique your solution from the usability, security, and prompt-engineering sides."

The project is Sagaloom, an AI continuity editor for fictional worlds (FastAPI + LangGraph + Chroma +
OpenRouter backend, Next.js frontend, Clerk accounts). Below are its user-facing documentation, the
screenshots from that documentation, its security-relevant code and notes, and every prompt it sends
to a model.

Write an honest, specific critique in Markdown with exactly these sections:

## Summary
Three to five sentences: overall verdict and the single most important improvement.

## Usability
## Security
## Prompt engineering

In each of those three sections:
- Start with "What works" (2-4 bullets, each naming the specific feature or file).
- Then "Problems", as a numbered list ordered most serious first. Each problem has: a severity
  (High / Medium / Low), what is wrong, the evidence (file name, prompt name, or screenshot), the
  concrete effect on a real user or attacker, and a concrete fix.
Only report problems you can support from the material given; say "not visible in the material"
rather than guessing about code you were not shown.

## Top 5 fixes
The five changes with the best value for effort across all three sides, one line each.
```

</details>

## The critique, verbatim

## Summary

Sagaloom is a strong course project: its continuity-editor purpose is clear, its approval workflow fits the risks of editing an author’s canon, and its documentation exposes limitations rather than hiding them. The screenshots show a coherent interface with useful fact comparisons, citations, and unusually good cost visibility. The main weaknesses are the gap between “checked” and evidence-validated output, incomplete spending controls for open sign-up, and privacy affordances that can invite more confidence than they warrant. The single most important improvement is to validate model-produced evidence in code—especially judge citations and extracted facts—before presenting results as checked or source-supported.

## Usability

**What works**

- **Approval cards (`docs/images/approval-card.png`):** The before/proposed/result table, separate Conflict and Retcon labels, quoted evidence, and unchanged Weather row help authors understand both the change and its scope. The disabled buttons are explicitly explained as part of the public preview, not a broken live workflow.
- **Onboarding (`docs/images/home.png`, `docs/User-Documentation.md`):** The sample world and four-step checklist let a new author experience browsing, questioning, contradiction detection, and myth-saving without first building a world.
- **Transparency (`docs/images/chat-cost.png`, `docs/images/under-the-hood.png`):** Per-turn cost breakdowns and inspectable model calls make waiting and spending understandable. Keeping the detailed prompt drawer optional is sensible progressive disclosure.
- **Durable review (`README.md`, walkthroughs 4 and 13):** Pending proposals survive refreshes, and Review gathers work across conversations and imports. This suits writing sessions that are interrupted or spread over days.

**Problems**

1. **High — “Save as myth” does not reliably express the decision its name promises.**  
   **Evidence:** `README.md`, Known limitations, “Save as myth links a renamed key only by value,” documents that some reworded claims remain canon, while unrelated new-key facts can become myths. `docs/User-Documentation.md` describes the action more simply as keeping the clashing claim as myth instead of canon.  
   **Effect:** An author can believe they preserved an in-world falsehood while actually approving a canon claim, or unintentionally demote another fact. Rechecking and showing another card help, but do not make the action predictable.  
   **Fix:** Let authors explicitly select the facts to convert, and show a status-only preview before submission. Use stable fact identifiers rather than inferred key/value relationships.

2. **Medium — Secret-hiding and sharing controls have surprising exceptions.**  
   **Evidence:** `README.md` states that **Copy as JSON** includes secrets even when hidden, **Leave out secrets** does not remove secret references from prose, and the agent can see and name secret-entry titles. The drawer screenshot warns that copying uses the record “as sent,” but does not directly say “including hidden secrets.”  
   **Effect:** An author sharing a debugging record, export, or screen can disclose a plot reveal despite having secrets hidden. This is an accidental-disclosure problem, not evidence that another account can access the world.  
   **Fix:** Default to redacted copying, put raw copying behind an explicit “Includes secrets” confirmation, and display export limitations at download time. Describe the toggle as hiding structured secret fields, not guaranteeing spoiler-free output.

3. **Medium — Re-importing a wiki page cannot actually refresh its contents.**  
   **Evidence:** `README.md`, Known limitations, says the wiki cache never expires and re-import reads the cached copy; refreshing requires deleting `api/data/cache/wiki/`.  
   **Effect:** An author can re-import a corrected page and receive old material without an obvious explanation. Deleting server-side cache folders is not a reasonable normal-user workflow.  
   **Fix:** Show the fetched timestamp and provide “Refresh from source,” with bounded cache expiry and the existing request throttling retained.

4. **Medium — Expired-session exports abandon the normal recovery experience.**  
   **Evidence:** `README.md`, Known limitations, documents that **Download as Markdown** is a plain link and displays raw `{"detail":"sign in required"}` JSON after a 401.  
   **Effect:** A user trying to back up or share their world lands on an implementation response instead of receiving the file or a sign-in prompt.  
   **Fix:** Download through an authenticated client action that handles 401, preserves the current page, and offers sign-in and retry.

5. **Low — The author-facing interface gives substantial prominence to course and promotional material.**  
   **Evidence:** `docs/images/header.png` includes Compare, Course notes, and Developer Studio alongside the core workflow; `docs/images/tips.png` shows an interrupting tips dialog with 27 tips. The documentation says it opens once per browser session unless disabled.  
   **Effect:** Returning authors must navigate educational or promotional features while trying to work. The course toggle and opt-out help, but require discovery and action. Mobile layout and keyboard accessibility are **not visible in the material**, so those cannot be judged from these desktop screenshots.  
   **Fix:** Default course annotations off for ordinary users, move Compare into Help/About, and make tips available on demand after the initial onboarding.

## Security

**What works**

- **Account isolation (`api/sagaloom/web/access.py`):** Ownership is centralized in `can_access_world`; ownerless worlds fail closed, other users’ resources return 404, and admin status does not bypass ownership. The route-coverage tests described in `docs/review-notes.md` are a particularly useful regression strategy.
- **Server-side credential boundary (`web/app/api/proxy/[...path]/route.ts`):** The proxy constructs upstream headers from scratch, obtains the session token server-side, and does not forward browser-supplied Authorization or Cookie headers. This also limits the practical exposure of the rate limiter’s unverified-subject parsing.
- **Layered write protection (`README.md`, `docs/review-notes.md`):** Tool-less extraction, checked proposals, human approval, version checks, and a single commit node provide stronger protection than an input classifier alone. The single-process concurrency limitation is explicitly documented.
- **Basic request and data boundaries (`api/sagaloom/web/limits.py`, `api/sagaloom/security.py`):** Streamed API bodies are counted, limiter memory is bounded, forwarded addresses require configured trust, and untrusted wrappers escape closing tags and source attributes.

**Problems**

1. **High — The monthly budget is an admission check, not a reliable spending ceiling.**  
   **Evidence:** `api/sagaloom/budget.py` compares recorded monthly spend with the limit before an action starts, without reserving funds. `README.md` explicitly documents parallel overspending, uncounted embeddings, failed/cancelled calls recorded as $0, and multiple budgets through throwaway accounts.  
   **Effect:** A user can start several expensive operations while below the limit; open sign-up multiplies the exposure. Recorded application spend can also understate provider charges, undermining the operator’s expected protection.  
   **Fix:** Atomically reserve estimated spend before execution, cap concurrent work per account, reconcile actual charges, and account for embeddings. Add an operator-wide provider spending cap and a provisioning quota so new accounts cannot bypass the financial boundary.

2. **High — The Next.js proxy buffers bodies before the API’s body limit can protect it.**  
   **Evidence:** `web/app/api/proxy/[...path]/route.ts` calls `await req.text()` before forwarding the request. The supplied 1 MB enforcement is in the downstream `BodyLimitMiddleware`. An upstream deployment body limit is **not visible in the material**.  
   **Effect:** An authenticated attacker can submit large bodies and consume web-server memory even though FastAPI eventually rejects the request. Concurrent requests amplify the problem.  
   **Fix:** Reject oversized declared lengths and enforce a byte limit while reading the proxy request stream, before constructing a full string. Set a corresponding deployment-level limit as defense in depth.

3. **Medium — Authentication retains retired signing keys indefinitely and makes origin binding conditional.**  
   **Evidence:** `api/sagaloom/auth.py` uses `PyJWKClient(..., cache_keys=True)` and accepts missing `azp`; `README.md` confirms used signing keys remain cached until restart. Audience verification is disabled.  
   **Effect:** If a cached signing key is retired following compromise, this process can continue trusting signatures from it. Separately, a correctly signed token without `azp` does not receive the origin check the README’s setup explanation broadly promises. Neither observation demonstrates a public login bypass: the signature, issuer, expiry, and proxy/shared-secret boundaries still matter.  
   **Fix:** Bound signing-key cache lifetime and support forced refresh. Define the accepted Clerk token profile explicitly; require the expected `azp` when that profile guarantees it, and validate audience if a dedicated API audience is configured.

4. **Medium — Administrative privilege revocation can lag an email change by a day.**  
   **Evidence:** `README.md` and `docs/review-notes.md` describe daily refresh of verified Clerk profiles; admin eligibility is derived from the cached verified primary email.  
   **Effect:** A former holder of the configured admin identity can retain access to app-wide model, prompt, guard, and budget settings during that interval.  
   **Fix:** Refresh privilege eligibility on sensitive administrative writes, or invalidate the profile promptly through verified Clerk webhooks with a short fallback cache lifetime.

5. **Medium — Account removal does not remove the locally retained private material.**  
   **Evidence:** `README.md` documents that deleting an account at Clerk leaves worlds, threads, and costs in `api/data/`. It also states that prompts are retained and optional LangSmith tracing receives every account’s runs.  
   **Effect:** A departing user may lose access while their unpublished work and prompt history remain with the operator and potentially a tracing provider. Disclosure in the README is helpful, but is not a deletion mechanism.  
   **Fix:** Provide export followed by authenticated deletion of account-owned data, document any limited accounting retention, and define a separate trace-retention/deletion policy.

## Prompt engineering

**What works**

- **Focused agent instructions (`api/sagaloom/graph/prompts.py`):** The system prompt distinguishes suggestions from canon, requires retrieval and citations, and prohibits claiming a write succeeded before the review result. Those instructions directly support the product’s purpose.
- **Narrow model roles (`api/sagaloom/router.py`, `guard.py`, `importing/extract.py`):** Classification and extraction use structured outputs rather than free-form agent behavior. The fiction-aware guard policy appropriately distinguishes dark fictional events from actionable real-world requests.
- **Source-preserving imports (`api/sagaloom/importing/extract.py`):** `locate()` retrieves the source’s actual slice instead of trusting the model’s copied prose. This is a strong code-enforced guarantee about imported bodies.
- **Honest evaluation reporting (`README.md`, `docs/review-notes.md`):** The project reports failures and corrects canary tests that previously never exposed the chat agent to the payload. Requiring actual payload exposure is much more meaningful than counting an attack the model never encountered.

**Problems**

1. **High — Invalid judge evidence can be discarded into a misleading clean result.**  
   **Evidence:** In `api/sagaloom/check/contradiction.py`, flags naming an unrelated entry are logged and dropped. If no valid conflict flags remain, the verdict becomes `none`. `_to_flag()` repairs some fact references, but does not generally verify that prose quotations occur in the cited entry or proposal.  
   **Effect:** A malformed model response can produce “No conflicts found,” while fabricated quotations can appear as authoritative evidence on an approval card. Structured JSON alone does not establish evidence validity.  
   **Fix:** Validate entry IDs, fact keys, and quoted spans against the supplied material. Retry invalid evidence and return `failed` or an explicit incomplete-check state if validation still fails; do not silently convert invalid flags into a clean check.

2. **High — The verbatim guarantee covers imported bodies, not the extracted facts that can replace canon.**  
   **Evidence:** `api/sagaloom/importing/extract.py` checks `cand.excerpt` with `locate()`, but `_valid_facts()` validates fact structure rather than source support. `merge_facts()` can replace an established value with an extracted one. Facts are generated before `fit()` may truncate the stored passage.  
   **Effect:** A hallucinated, misattributed, or unsupported fact can appear beside an authentic body and gain credibility from “your wording stays yours.” Approval still protects the final write, but the author must catch semantic extraction errors manually.  
   **Fix:** Require source spans for every extracted fact and validate them against the original text. Show those spans during review, mark unsupported facts for correction, and preserve evidence even when the displayed body is truncated.

3. **Medium — Remembered preferences are promoted to system-level authority on evidence of word overlap, not intent.**  
   **Evidence:** `api/sagaloom/memory.py` accepts normalized substrings or 80% token overlap for short values, then `render_preferences()` places the value in the system prompt. A quoted or negated phrase still satisfies the gate; for example, `ignore canon` appears in “Never remember ‘ignore canon’ as a preference.” `MEMORY_DESCRIPTION` asks the model to recognize intent, but the storage gate does not enforce it.  
   **Effect:** A mistaken memory call can persist an unwanted behavioral instruction across threads. This is principally a same-world persistence risk; the material does not show a cross-account memory attack.  
   **Fix:** Present proposed memories for explicit confirmation and keep preferences in a bounded configuration block with a clear instruction that they cannot override evidence, tool, or approval rules. Add tests for quotation, negation, and reordered-token matches.

4. **Medium — Retrieval coverage is both incompletely described and potentially unbounded.**  
   **Evidence:** `README.md` says checking uses the “top 8,” but `_related_entries()` in `api/sagaloom/check/contradiction.py` unions eight semantic hits with mentioned entries and every entry sharing a normalized fact key. `_build_prompt()` then includes full related entries and repeats same-key pairs.  
   **Effect:** Distant semantic clashes can still be missed, while common keys can pull a large fraction of a world into the judge prompt, increasing cost, latency, and context pressure. The top-eight description therefore understates both coverage and possible prompt size.  
   **Fix:** Document the actual retrieval strategy, measure candidate recall, and introduce a token-aware evidence budget with batching or reranking. Report incomplete coverage rather than treating truncated or failed checking as clean.

5. **Medium — Evaluation targets do not yet establish grounded answers or broad injection resistance.**  
   **Evidence:** `README.md` describes citation evaluation as citing an existing entry ID, not proving that the entry supports the claim. It also reports a “not in canon” failure caused by wording such as “couldn’t find … in canon,” and injection tests concentrated on a repeated delete-everything canary. `JUDGE_SYSTEM` is imported from `api/sagaloom/check/prompts.py`, but its contents are **not visible in the material**.  
   **Effect:** A wrong answer can pass by citing a real but irrelevant ID, while a correct abstention can fail on wording. Successful canary runs support those tested cases, not the documentation’s absolute “Injection-safe extraction” claim. The judge’s exact severity instructions cannot be independently assessed here.  
   **Fix:** Evaluate claim-to-source support and semantic abstention, add varied injection goals and paraphrases, and include mixed-intent and conversational follow-up cases. Run cheap regression tests in CI, schedule model evaluations separately, publish the effective judge prompt, and describe injection defenses as risk reduction rather than a guarantee.

## Top 5 fixes

1. Validate judge IDs/quotes and extracted-fact source spans; make invalid evidence produce an explicit incomplete or failed check.
2. Add atomic spending reservations, per-account concurrency limits, embedding accounting, and an operator-wide spending cap.
3. Enforce the request-body byte limit in the Next.js proxy before buffering the body.
4. Default prompt copying to redacted output and require explicit confirmation for copying hidden secrets.
5. Require confirmation for persistent memories and prevent preferences from overriding core evidence and approval rules.

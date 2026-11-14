# Monthly Recap Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` for this single scoped change. The user approved the approach in conversation and requested implementation, technical documentation and one local commit.

**Goal:** Replace only the Home spotlight card with a concise, automatically generated recap of the selected account and month.

**Architecture:** Reuse `createAPI.agent(message, {month, locale, conversation: []})` and the existing read-only tools/numeric verification. The model chooses supported observations and writes the recap; the client presents recorded monthly figures while loading or after failure. Keep a bounded in-memory cache and reject obsolete responses.

**Tech Stack:** Existing Python/SQLite API, vanilla JavaScript and CSS, EN/FI/SV translations, Python unittest/Node harness and optional Playwright/Chrome.

**Spec:** The approved design below records the user's conversation request.

## Approved design

- The user chose an AI-written monthly recap, with tool-computed facts rather than model arithmetic, followed by number verification. Only this Home card changes; update technical documentation and commit locally without pushing.
- Chosen approach: reuse the existing agent for a brief summary and relevant follow-up. Alternatives considered in discussion were the existing fixed spotlight templates and asking a model to calculate directly from raw transactions. Existing tools provide exact amounts and source references while the model can select the salient facts.
- Show a month-specific heading and a short recap, an honest AI/recorded-facts source label, and access to Coach. Remove the Alex/September fixed restaurant headline from this card. Other stories, chat rendering and financial engines retain their behavior.
- Source raw amounts from the existing server. Do not invent missing values, present transaction counts as outings, or equate savings transfers with portfolio returns. Home generation cannot save goals/scenarios or create conversation messages.
- Implementation choices: first show available income/spending/saving-transfer facts, then replace them with an accepted agent answer. Cache at most twelve results during this page session, keyed by account, month, language and the loaded overview snapshot. Data reloads can invalidate changed snapshots. A failed attempt remains on factual copy until the snapshot or page session changes. No transcripts/cache are persisted.
- Copy acceptance requires a successful overview step and at most 600 characters across one to three paragraphs; the prompt requests two short sentences and two observations. Live verification exposed cent/euro calculator confusion, so the prompt explicitly uses preformatted euro values and computed comparison differences, leaving optional failed calculations out.
- Local preferences and notes stay local. Preserve existing protected-category/buffer follow-ups and optional personal-plan actions; the automatic recap prompt contains no profile notes or preference text. Its observations are descriptive, without prescriptive category-cutting advice.

## Global constraints

- Run commands from the repository root; all repository text is English.
- Limit changes to `s bank/`; no dependency, endpoint, request-field or environment-variable changes.
- Preserve the user's deletion of `s bank/.env.example` and untracked root implementation brief. Never stage `.env` or source databases.
- Reuse the current feature branch and the already authorized temporary Playwright installation.
- Run the full S-Coach suite before the single commit; do not push or open a PR.

## Review focus

- A delayed answer after account/month/language changes must never overwrite the active card.
- Auto generation must not block Home/Coach, create chat history, or execute a proposed action.
- Missing/failed data, unavailable models and malformed/overlong summaries must show honest factual/unavailable copy, never old persona data or an AI label.
- Repeated renders/navigation must reuse results; changed financial snapshots must request fresh analysis.
- Untrusted model text and local notes must not become executable HTML or unintended prompt context.

### Task 1: Scoped monthly recap

**Files:** Create `web/monthly-recap.js`, `tests/test_monthly_recap.py`; modify `web/app.js`, `web/index.html`, `web/i18n.js`, targeted existing client/browser tests, and `README.md`, `docs/API.md`, `docs/DEVELOPMENT_LOG.md`.

**Interfaces:** Consume the existing `createAPI.agent` response and monthly overview fields `salary_cents`, `other_income_cents`, `consumption_cents`, `committed_saving_transfers_cents`. Produce `monthlyRecapPrompt(month, locale)` and `createMonthlyRecapCache().get(key, request)` entries with `pending`, `result` and `promise`; accepted results contain bounded plain text and one suggested question.

- [x] Write failing client tests for automatic scoped generation without chat/history/writes, safe rendering, cache reuse/invalidation, late-answer isolation, fallback/missing facts, and Coach handoff.
- [x] Run `PYTHONPATH='s bank:s bank/tests' python3 -m unittest test_monthly_recap -q`; expect failures for absent recap behavior.
- [x] Implement the small cache/prompt module and sole ownership of the Home card's text. Keep its async state independent from chat and account loading.
- [x] Re-run the targeted tests and existing interaction tests; expect all to pass with intent-preserving fixture adjustments only.
- [x] Extend rendered acceptance for Home text, loading/fallback, source label, related question and no overflow at phone/desktop widths. Reuse temporary synthetic data and scripted responses, then perform a small live DeepSeek smoke check separately.
- [x] Update technical documentation; run the full suite with `SCOACH_CHAT_PLAYWRIGHT_PATH=/tmp/scoach-wp6-browser/node_modules/playwright`, syntax and staged whitespace/credential checks. Expect zero failures; the older separately opted-in browser flow may remain skipped.
- [x] Obtain one fresh read-only review of this change, resolve substantive findings with regressions, and commit the scoped files once. Report the commit and stop.

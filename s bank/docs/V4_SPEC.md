# V4 build spec (for parallel agents)

Source of truth for WHY: `docs/V4_REVIEW_AND_PLAN.md` (Chinese) and the six reports in `docs/critique/` (English, with file/line evidence). Read the parts relevant to your lane. This file defines WHAT each lane builds and the CONTRACTS between lanes.

Product direction: S-Coach is an S-mobiili feature that turns each salary into a plan: must-pays held back, a surprise buffer, one honest "per day until payday" number. Categories/baskets explain *why*. Optional planning modules (mortgage, tax) can be switched on by the customer. The Home redesign (lane H) waits for the owner's positioning decision and is NOT in this batch.

## Global rules (every lane)

- Work only in your git worktree on your branch. Commit often with clear messages. NEVER use `git stash` (shared across worktrees), never checkout other branches, never touch `s bank/var/` or `.env*`.
- Python stdlib only; vanilla ES modules; no new dependencies.
- Run the full suite before your final commit: `cd "<worktree>/s bank" && python3 -m unittest discover -s tests -q`. It must pass. If you change a behaviour that an existing test pins, update the test only when the old behaviour is the bug described in the review; say so in the commit message.
- Add tests for what you build. Money is integer cents. All customer-facing text exists in EN, FI and SV (natural, not word-for-word; FI money format `1 138,27 €`, SV `1 138,27 €`, EN `€1,138.27`; percentages FI/SV `9,6 %`).
- No developer wording visible to customers (no "deterministic", "demo reserve", "MCC", "quartile", "scenario", "provenance", "reference day").
- Keep your diff inside your lane's files. If you must touch a shared file (api.py, app.js, i18n.js, styles.css, index.html, agent.py), keep the edit small and contiguous, and list it in your final report.
- Final report: what you built, files touched, contracts implemented, test count, anything left undone.

## Lane N — numbers you can trust (backend) — branch v4-numbers

1. ONE safe-to-spend. New `forecast.spending_plan(conn, cid, as_of=None, profile=None)` (wrap/replace `safe_until_payday`) returning:
   `{as_of, balance_cents, next_payday, days_to_payday, held_back:[{kind:'bill'|'loan'|'tax'|'goal'|'buffer'|'reserve', label, amount_cents, date|null}], everyday_cents (expected groceries/commuting etc. until payday, from history), buffer_cents, reserve_floor_cents, free_cents (= balance − held_back − everyday, floored at 0), per_day_cents, extra_cents (money beyond a sensible cap that should be shown as "could be saved", not spendable), basis:{...}, evidence:{...}}`.
   - Spendable until payday = min(free_cents, cap) where cap is a sensible ceiling from the customer's own typical spending until payday (e.g. 1.5× median non-bill spending for that many days); the rest is `extra_cents`. Taylor/Sam must no longer get €11k–15k/week.
   - `/api/safe-to-spend` always returns this shape (keep accepting `days`/`horizon`/`reserve_floor_cents` for compatibility, but there is only one answer). Remove the 7-day path from the agent tool `safe_to_spend`; `safe_to_save` must be consistent: can_save ≤ free − spendable, never double-counted.
2. Payday detection (`forecast._next_payday` and friends): handle mid-month + end-of-month patterns and weekends; next payday must be a date salary has plausibly arrived on (never a median of two clusters). Test with Alex: salary days 15,15,15,29,30,31 pattern.
3. Goals capacity (`goals.py:56`) must agree with the spending plan (no "€0.00 capacity" next to "€4,223 available").
4. Saving rate (`cashflow.py`): saving = income − consumption (what was left), and separately "moved to savings/investments". Name both clearly. No constant 9.6% artefact presented as insight.
5. Year review (`year_review.py`, `year_story.py`): headline and body numbers come from the same field; no comparison with an incomplete year unless labelled; "left over" and "saved" must not overlap/contradict.
6. Spender/baskets (`spender.py`): Little leaks = discretionary purchases under €40 (configurable constant); larger discretionary purchases form "Bigger choices". The archetype must be derived consistently and explained in one plain sentence; no contradiction with basket figures.
7. Agent retry (`agent.py`): the number-verification feedback must be a system/tool note telling the model to rewrite silently ("do not apologise or mention a correction"); strip leading apologies ("My apologies", "You're right", "Sorry") from final answers as a safety net.
8. Formatting bugs: VAT "1E+1%" (`vat.py:131`), tax summary thousands separators and FI/SV text, percent formatting helpers.
Owns: forecast.py, goals.py, cashflow.py, year_review.py, year_story.py, spender.py, vat.py, tax.py (format only), agent.py (retry only), agent_tools.py (safe_to_spend/safe_to_save only), api.py (safe-to-spend route only), related tests.

## Lane C — question catalogue + answer cards (backend) — branch v4-catalogue

New module `scoach/catalogue.py` and routes. The catalogue replaces the regex offline coach as the offline answer path.
- ~27 questions in 7 groups (money overview, spending, safe & save, goals, bills & coming up, my profile/life events, extras: compare/taxes/VAT/year). Must include the brief's four: "Where did my money go?", "What kind of spender am I?", "What can I safely spend this week?" (→ until payday), "How could I save more?". Each question: id, EN/FI/SV text, group, tool call(s) via `agent_tools.dispatch`, optional pickers.
- Contracts:
  - `GET /api/catalogue?customer_id&locale` → `{groups:[{id, title, questions:[{id, text}]}], starters:[question ids for empty-state chips (6)]}`
  - `POST /api/catalogue/answer?customer_id&month` body `{question_id, params?, locale}` → `{card}`
  - `POST /api/catalogue/match?customer_id` body `{message, locale}` → `{suggestions:[{id,text}] (max 3), supportive: str|null, intent_hint: str|null}`. Matching is ranking only (token overlap/synonyms incl. FI/SV stems); it NEVER answers. Emotional/life-event messages (stress, lost job, baby, divorce, illness) set `supportive` to one warm line and suggest relevant questions (e.g. safe-to-spend, buffer, "tell the coach about a life change").
  - Card shape: `{question_id, title, headline:{label, value_text, value_cents|null}, lines:[str] (≤4, plain language), chart:{kind:'bars'|'trend'|'ring'|'progress', data}|null, caveat:str|null, evidence:[{label, query}], followups:[{id,text}] (2–3), pickers:[{name, kind:'category'|'month'|'percent'|'amount'|'date', value, options?}], params_used:{}}`. All text localized server-side with correct number formats.
  - Amount/date extraction helper `extract_amount_date(message, locale)` (e.g. "save €2,000 for a trip by June") used by match to prefill a goal question's params.
- `/api/agent` fallback: when the model is unavailable or fails verification twice, return `{source:'catalogue', fallback_reason, supportive, suggestions, card:null}` (or a card if match is unambiguous AND the question has no required params) instead of the old regex coach answer. Keep `/api/coach` working for existing tests but stop using it from the agent fallback.
- AI path: add `cards` to agent responses when the model's tool calls correspond to catalogue questions (map tool name+args → card via the same builders), so AI and offline answers look the same; the model text becomes the 1–3 sentence lead.
- Acceptance tests: the brief's four questions + all 6 starters answer correctly via catalogue in EN/FI/SV; 20 tricky free-text messages from `docs/critique/coach.md` get sensible suggestions and never a wrong answer.
Owns: catalogue.py (new), tests/test_catalogue.py (new), api.py (new routes + agent fallback branch), agent.py (fallback branch + cards), agent_tools.py (only if a builder needs a new read tool — add, don't change existing).
Use `forecast.spending_plan` if present; if not yet merged, call `safe_until_payday` behind a small adapter function `_plan(conn,cid,as_of)` so the merge is a one-line change.

## Lane U — Coach UI with cards (frontend) — branch v4-coachui

- New `web/answer-card.js`: `renderCard(card, {locale, esc})` → HTML; charts via existing `charts.js`; evidence opens existing transactions dialog; pickers re-request `/api/catalogue/answer` with params; followups are chips.
- Coach empty state and topic menu (`web/topic-menu.js`) load from `GET /api/catalogue` (fallback to a built-in list if it fails). Tapping a question → `POST /api/catalogue/answer` → render card as a coach turn (no AI call needed, instant).
- Typed text → `/api/agent`. If `source==='agent'`: render lead text + `cards`. If `source==='catalogue'`: show an honest notice ("Quick answers mode — the AI coach isn't available right now"), the supportive line if any, the suggestion chips, and the existing "Try again with the AI coach" button.
- Remove the 8-question onboarding from the first Coach visit (keep the code reachable from Me → "Tell the coach about you"). Coach opens straight into the chat with starter chips.
- Finnish/Swedish: all chips and notices localized.
Owns: answer-card.js (new), topic-menu.js, coach parts of app.js (`askCoach` render path) and coach-chat.js, onboarding trigger in v3.js (only the auto-open call), CSS in a new `web/cards-v4.css` linked from index.html. Mock the API in tests (tests/test_web_contract.py harness) — lane C's endpoints may not exist in your worktree yet; code against the contract above.

## Lane P — optional planning modules: mortgage + tax (backend + UI) — branch v4-plans

Opt-in "Plans" the customer can switch on (stored as money-profile entries, e.g. key `plan_mortgage`, `plan_tax`; extend `money_profile.validate_entry`).
- Mortgage plan (`scoach/mortgage.py`): inputs remaining principal, interest (reference rate e.g. 12-month Euribor + margin, user-entered), type annuity|equal_principal, monthly payment, remaining years; detect a likely loan payment from transactions to prefill (Taylor has history in `financing.py`). Outputs: payoff date, total remaining interest, monthly plan (payment held back on each payday — expose `planning_inputs` so lane N's spending plan holds it back as kind 'loan'), what-if extra €X/month (months and interest saved), rate +1 pp / −1 pp payment change, and a gentle note when the buffer is thin before suggesting extra payments. Clearly "estimate, check with your bank". Endpoints: `GET /api/plans` (which plans exist/on), `POST /api/plans/mortgage` (confirmed save), `GET /api/plans/mortgage/projection?extra_cents&rate_delta_bp`.
- Tax plan: switch on "Help me plan taxes" → uses `tax.py`: monthly set-aside for expected back tax, refund expectation, suggestion to update the tax card when withholding looks off (link text to Vero's OmaVero, no real link needed), dates from the tax calendar. Endpoint `GET /api/plans/tax`.
- Agent tools: `mortgage_plan`, `tax_plan` (read-only) + prompt lines; AI can propose turning a plan on via a review card (`propose_action` kind `enable_plan`).
- UI: in the Goals tab, a "Plans" section above goals: two cards "Mortgage plan" and "Tax plan" with short benefit text and "Turn on" → a draft form (reuse the v3 draft dialog `openDraft`) → saved plan card showing the monthly plan + what-if slider/buttons. New `web/plans.js`, CSS in `web/plans-v4.css`.
Owns: mortgage.py, plans (new module or in mortgage.py), money_profile.py (validation for new keys only), api.py (new routes), agent_tools.py (new tools only), agent.py (prompt lines only), web/plans.js, web/plans-v4.css, small hook in app.js/v3.js to render the Plans section, tests.

## Lane F — fix broken and confusing things (frontend) — branch v4-fixes

From usability.md / visual.md / judge.md, excluding Coach rendering (lane U) and Home redesign (later):
- Me tab "Add something" menu: all 13 buttons dead (handler bound to #profile-content, menu in #v3-dialog; `v3.js:179/192`). Fix and test.
- Routing: each tab gets a URL hash (#home, #spending, #coach, #goals, #me); back/forward and reload work. Chat clears only with a visible notice.
- Remove developer copy everywhere visible (list in visual.md: "Deterministic offline coach", "demo reserve", "MCC is used first", "upper quartile…", "Rate mapping coverage", "Average unavailable", "Observed restaurant spending" under total chart, investments card copy-paste, duplicated VAT row).
- Spending tab: remove duplicated headings under accordion titles, one period control, readable chart month labels everywhere (trend chart too), empty "Choose a slice" box only when nothing selected.
- Dialogs: title in the sheet header, no box-in-box, Save never cut off (sticky footer); goal edit date input in locale format.
- Desktop: year banner/tax chip full width (styles.css:632-635), month-range control layout.
- Consistent buttons (≤3 styles), replace "↗" on in-app links with "›", nav icons as inline SVG set.
- Unified plain vocabulary (usability.md list): one term per concept across EN/FI/SV.
Owns: v3.js (non-coach parts), app.js (routing + non-coach), index.html, styles.css, i18n.js (EN copy fixes), money-profile.js, draft-card.js, charts.js (labels only), tests.

## Lane L — Finnish & Swedish (frontend copy) — branch v4-lang

- Translate every English string still visible in FI/SV (Things I noticed questions — these come from `money_profile.profile_suggestions` server-side, so localize there too; archetype labels; category names on year cards; follow-up chips; assumption lines).
- Fix awkward phrasing (judge.md: "Tilaa tärkeille asioille", "demon vararaha", spliced "Mihin … meni: syyskuu 2026?", "osparade skatteplaner") and number formats in FI/SV (`9,6 %`, `225,70 €`, "13,5 % ja 25,5 %").
- Produce `docs/LANGUAGE_REVIEW.md`: a table of key terms (baskets, archetypes, plan names, buttons) EN/FI/SV for a native speaker to approve.
Owns: i18n.js (FI/SV values only — do not change keys or EN), server-side localized strings in money_profile.py/spender.py/year_review.py (string tables only), tests. Coordinate with lane F by never editing EN values.

## Lane H — Home as the Payday Plan (frontend) — branch v4-home

Owner decision (2026-11-15): adopt the "Payday Plan + surprise buffer" positioning. See docs/critique/product.md section 4 and visual.md's Home sketch.
- Home, top to bottom at 390x844, with NO demo labels/slogans above it (move persona/month/language into a compact header or the profile button sheet; keep a small "Synthetic demo data" note in the footer):
  1. Plan hero card: "€162 a day until payday" (big), "Payday in N days · Thu 15 Oct", a thin bar showing balance split into Held back (bills, loan, tax set-aside) / Buffer / Free to spend / Could be saved, and a "Why this number?" expander listing held_back lines with dates (data: `GET /api/safe-to-spend` → lane N's `spending_plan` shape; code a small adapter so it also works with the current `safe_until_payday` shape).
  2. One coach insight with up to 2 action chips (e.g. "Put €80 in your surprise buffer" → confirm card that saves a goal/plan entry, no real money moves; "See where it goes" → Spending).
  3. This month: in / out / left over, each once, with change vs last month (reuse recapTiles data).
  4. Surprise buffer card: target from `irregular_buffer`, progress, one-tap "Set aside monthly".
  5. Goals/plans summary (one line each, link to Goals).
  6. Seasonal extras (year review, tax date) as one small row at the bottom, not banners.
- Remove from Home: slogan hero, duplicate "Make it yours"/"Show me around" buttons, the four-times repeated income/spent/saved, the full baskets card (baskets live in Spending).
- New files web/home-v4.js and web/home-v4.css; only touch the #home-view markup in index.html and the Home render call in app.js. Do not touch other tabs (lane F) or Coach (lane U). All text EN/FI/SV.
- Tests in the node harness for the plan card (both API shapes), plus Playwright screenshots at 390x844 and 1280x800.

## Global rule added by the owner (2026-11-15)

Do NOT lose the existing personalization strengths: money profile (entries with sources, view/edit/delete/forget), "Things I noticed" Keep/Not this, steady mode after job loss or big loss, saving targets / emergency-fund months / debts / protected categories changing the numbers, "the coach recorded this" notices, confirm-before-save, local preference consent, goals and wishes. Every lane keeps these working and visible.

## Lane G — personalization guard (tests) — branch v4-guard

Write `tests/test_personalization_v4.py` (API level, temp DB like other tests) + `tests/browser/personalization_walk.py` (Playwright script, not run by unittest) that pin every personalization behaviour above end to end: profile entry → safe-to-spend/plan changes; steady mode → reserve and tone; protected category never suggested for cuts; Things I noticed keep/dismiss; forget-all; goal from chat with review; consent for remembering preferences. Code against current APIs, and for V4 contracts (spending_plan, catalogue cards with "Using what you told me" line, plans) write tests guarded with skipUnless(endpoint exists) so they turn on when lanes merge. Owns only new test files + docs/PERSONALIZATION.md (what is personal, where it shows, how to verify).

## Lane A — AI coach prompt and tone — branch v4-ai

Prompt-only work in scoach/agent.py (the SYSTEM prompt text and its builder; do not touch the loop, fallback or verification code owned by lanes N/C): at most one clarifying question and only when the answer would really differ; answer multi-part questions in order; lead with the answer in ≤3 short sentences; empathy first for distress/life events, then one practical step; use the profile summary naturally ("since you're between jobs…"); never lecture about baskets unless asked; FI/SV answers use local number formats; never invent benchmarks; mention the plan modules (mortgage/tax) only when relevant. Add `scripts/eval_agent.py`: runs a list of 30 questions (EN/FI/SV, incl. brief's four, emotional, multi-part, follow-ups) against a running server's /api/agent and writes a markdown table (source, ms, verification, answer) — the lead will run it against the owner's live server. Add prompt unit tests (prompt contains rules; builder includes profile summary and mode).

# Personalization: what is personal, where it shows, how to verify

The owner's rule for V4 (docs/V4_SPEC.md, 2026-11-15): no lane may lose the existing personalization strengths. This page lists each one, where the customer sees it, which code carries it, and the test that pins it. Lane G owns this page and the guard tests. It changes no product code.

## How to verify

```bash
cd "s bank"
python3 -m unittest discover -s tests -p test_personalization_v4.py -v   # guard only, about 10 s
python3 -m unittest discover -s tests -q                                 # full suite
python3 tests/browser/personalization_walk.py --out /tmp/pg-walk         # real browser walk (Playwright)
```

- `tests/test_personalization_v4.py` runs the real HTTP application (`Application.handle`) on a temporary synthetic ledger with two customers, so it does not need the demo database. The UI checks render the API's JSON with the real ES modules through `node`.
- `tests/browser/personalization_walk.py` starts its own server on a temporary copy of the demo database, using a scripted AI coach so the chat flows are reproducible without a model key. It prints PASS/FAIL for each check and saves screenshots. unittest does not run it (the file name does not start with `test`). Options: `--chrome /usr/bin/google-chrome`, `--width 1280 --height 800`, `--locale fi`.

## The behaviours

| # | Personal behaviour | Where the customer sees it | Code | Pinned by (test class) |
|---|---|---|---|---|
| 1 | **Money profile** entries carry a source ("You told me", "From your transactions", "From our chat", "Year in review"). Every entry can be viewed, edited and deleted, all audited, and undo works. Entries are private to the customer. | Me → "What your coach knows about you" | `money_profile.py`, `/api/profile*`, `web/money-profile.js` `renderProfilePage`, `web/v3.js` `renderProfile` | `ProfileEntriesStayVisibleAndEditable` |
| 2 | **Confirm before save.** Every personal write needs `confirmed: true`: entries, update, delete, forget, Keep, Not this, migrating browser notes, goals. | Draft/review cards with Save / Change / Not now | `api.py` (POST guard), `web/draft-card.js` | `ProfileEntriesStayVisibleAndEditable.test_every_personal_write_needs_explicit_confirmation` |
| 3 | **Profile changes the numbers.** The saving target holds back target % of the last salary. Declared loans and regular investing are held back once per pay cycle, and are not double-counted when a recurring payment within 10 % already covers them. Deleting an entry or forgetting everything restores the baseline. The API, the AI tool and the offline coach all give the same figures. | Spending → Safe to spend; Coach answers | `forecast.safe_until_payday(profile=…)`, `api.planning_profile`, `agent_tools` `safe_to_spend` | `ProfileChangesTheNumbers` |
| 4 | **Steady mode** turns on after a `job_loss`, `income_drop` or `large_loss` life event. It lasts 6 months unless the event is ended or deactivated. While it is on, the reserve is at least one month of must-pays, no saving is planned, and the AI is told "Coaching mode: steady" with its supportive rules. "Turn off" deactivates the event. | Me → steady banner with "Turn off"; Safe to spend; Coach tone | `money_profile.steady_reason/coaching_mode`, `forecast` step 7, `agent.py` prompt | `SteadyModeAfterALoss` |
| 5 | **Protected categories** are never put forward for cuts. The AI prompt and `get_profile` say "Protected categories (do not suggest cutting): …". Category names are validated. The browser preference "Don't cut restaurants" is proposed and only saved after the customer confirms it. | Me → "Spending I leave alone"; Coach | `money_profile.profile_summary`, `web/experience.js` `suggestedMemory`, Home plan in `app.js` | `ProtectedCategoriesAreRespected` (+ guarded catalogue check) |
| 6 | **"Things I noticed"**: reading saves nothing. Every item is phrased as a question, with evidence. Keep saves the item with source "From your transactions". Not this hides the item for good (undo brings it back). Confirming the housing payment as a mortgage does not double-count it. Other customers cannot answer my suggestions. | Me → Things I noticed (Keep / Not this); intro summary | `money_profile.profile_suggestions/confirm/dismiss` | `ThingsINoticed`, `ProfileChangesTheNumbers.test_a_mortgage_…` |
| 7 | **Forget everything** clears all entries and dismissals. Mode returns to normal, the numbers return to baseline, and the AI prompt goes back to "nothing shared yet". It can be undone. | Me → Forget everything (asks first) | `money_profile.forget_all` | `ForgetEverything` |
| 8 | **"The coach recorded this."** A profile fact from chat appears as a review card ("I'd like to note this in your profile"). It is saved only through the confirmed POST, with source "From our chat" and provenance `gemini_proposed_user_confirmed`. The coach uses it on the next turn. Proposals cannot invent amounts. The notices exist in EN, FI and SV. | Coach → review card; toast "Saved to your money profile…" | `agent_tools` `propose_profile_update`, `v3.js` `handleAgentAction('update_profile')`, `i18n.js` `v3.*` | `ReviewBeforeSavingFromChat`, `RecordedNoticesAreLocalized` |
| 9 | **Goals from chat**: the coach proposes, the Goals form opens prefilled, and the goal is saved only on submit, with provenance recorded. | Coach action button → Goals planner | `agent_tools` `goal_plan`/`propose_action`, `app.js` | `ReviewBeforeSavingFromChat.test_goal_from_chat_…` |
| 10 | **Local preference consent**: browser memory (style, protected spending, notes, wishes) is kept only for the current visit unless the customer ticks "Remember my preferences on this browser". `save()` cannot grant consent. Revoking consent or Forget clears the memory. Each persona is separate. Moving browser notes into the profile needs confirmation and removes duplicates. | Preferences dialog; Goals → wishes | `web/experience.js`, `/api/profile/migrate-local` | `LocalPreferenceConsent` |
| 11 | **Intro stays reachable** from Me (empty and filled profile), even after Coach stops opening it automatically (lane U). | Me → "Start the intro again" | `renderProfilePage` `data-profile-onboarding` | `ProfileEntriesStayVisibleAndEditable` |

## Guarded V4 checks (switch on when the lane merges)

| Lane | Guard condition | What it pins |
|---|---|---|
| N `spending_plan` | `hasattr(forecast, 'spending_plan')` | `/api/safe-to-spend` returns the plan shape and matches the function. The saving target adds exactly target % of salary to `held_back`. A declared loan appears as `kind: 'loan'`. Steady mode raises `reserve_floor_cents` and drops the planned saving. Forget-all returns the plan to the unpersonalized one. |
| C catalogue | `GET /api/catalogue` is not 404 | The safe-to-spend card has a line starting "Using what you told me" only when a profile is used; FI/SV cards change too and contain no English. The "save more" card never puts a protected category in pickers, followups, headline, chart or lines (except the "Using what you told me" line). A life-event message gets a supportive line and suggestions, and saves nothing. |
| P plans | `'plan_mortgage' in money_profile.KEYS` (and `/api/plans/mortgage` exists) | A plan is a confirmed, visible profile entry that is removed by forget-all and restored by undo. `POST /api/plans/mortgage` without confirmation is rejected. If the sample plan value stops validating, the test skips with the reason, so update `MORTGAGE` in the test. |

These guards were exercised before committing: the plans checks pass on lane P's work-in-progress copy, and the spending-plan checks pass against a throwaway adapter in a scratch copy.

## Known gaps (not covered by any lane yet)

- **Emergency-fund months** reach the AI prompt and `planning_inputs` but no number uses them. Neither the safe-to-spend calculation nor the buffer reads them. The owner's rule says they should change the numbers. The obvious home is lane N's `buffer_cents`.
- **Protected categories on the server** are enforced only through the AI prompt. `what_if_reduce` and the offline coach do not check them. The Home "Try 20 % less on …" button reads the browser preference, not the server profile. Lane C's catalogue guard above covers the new offline path.
- **Steady-mode tone offline**: the offline coach (and its catalogue replacement) has no gentler wording in steady mode. Only the AI prompt changes.
- **Browser walk findings (2026-11-15, Alex)**: the "Add something" options on Me do nothing (lane F is fixing this; the walk saves the target through the API so later checks still run). The chat review card shows "(optional)" twice on the note field.

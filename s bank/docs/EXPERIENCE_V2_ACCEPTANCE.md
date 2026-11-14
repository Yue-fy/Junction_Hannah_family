# S-Coach V2 acceptance record

**Historical V2 record:** the subsequent natural-language conversation and functional repairs are documented in [CONVERSATION_REPAIR_ACCEPTANCE.md](CONVERSATION_REPAIR_ACCEPTANCE.md), including the latest test result. This page preserves the earlier V2 verification.

This record covers the [V2 plan](EXPERIENCE_V2_PLAN.md) and [current demo script](DEMO_SCRIPT.md). Source inspection can establish wiring and calculation intent; it cannot establish visual quality, native browser behavior or customer understanding. V2 rendered acceptance is pending. Prior test totals in `ACCEPTANCE_STATUS.md` describe an earlier state and are not the V2 completion result.

## Experience acceptance map

| Outcome | Current source evidence | Acceptance still required |
|---|---|---|
| Four clear primary pages | `web/index.html` and `web/app.js` expose Home, Spending, Coach and Goals; Journal/notebook are secondary | Walk navigation and verify useful first-screen content |
| One category donut in Spending | One `spending-donut`; category list/selection share `spendingRing` and `spendingCategories`; Home uses compact basket rows | Check aligned arcs/track, labels, selection, touch and keyboard targets at all widths |
| Optional financial detail | Spending's trend, forecast, investment-transfer and VAT sections use collapsible details; tax planning is under Coach's topics | Check collapsed default, expansion and readable evidence |
| A complete conversation page | `coach-view`, transcript, scope, composer, sending state and retry; question buttons dispatch through `askCoach` | Submit starters and typed questions; navigate away/back; check scrolling and reachable composer |
| Useful inline results | `completeCoachAnswer` and `toolResultHTML` fetch/render forecast, transfer and historical financing results; scoped evidence remains available | Confirm real endpoint responses and evidence in rendered turns |
| Exact scenario handoff | The goal action posts the answer's category, percentage and month; modeled and observed values are separate | Verify 10%, 12.5%, 20% and 30% retain scope, then confirm the optional goal link |
| A wish before a numeric plan | `wish-form` requires a title only; `goal-planner` is optional; `experience.js` scopes wishes and consent per persona | Save without target/date; navigate; test session-only, opt-in, revoke, remove and unavailable storage behavior |
| Three real demo entry points | `openDemoStory` selects Kai/Alex/Taylor, September 2026, then submits the corresponding question | Verify each story starts with its own account and usable answer |
| Clear scope boundaries | Customer/month changes clear scoped state; language changes clear conversation; responses carry account/date context | Verify stale requests, drafts, evidence and scenario actions do not cross personas or periods |
| Bounded language support | Deterministic tools and EN/FI/SV copy remain available; unsupported requests require clarification | Check supported expressions and honest limitations; do not claim unrestricted understanding |

These are implementation observations. The integration test result and completed independent source review below are separate from rendered acceptance.

## Audited dataset baselines

All figures are EUR, for the stated account and dates, subject to saved corrections. They come from the current data audit, not a browser observation. Names are synthetic aliases.

| Account | Baseline facts | Interpretation boundary |
|---|---|---|
| Alex · `CUST00001` | September 2026 restaurants 225.70 / 10 transactions; August restaurants 115.43 / 10; September groceries 379.79; restaurant contributions 20% = 45.14, 12.5% = 28.21, 10% = 22.57; seven-day safe estimate 3,288.31 | Scenarios do not change observed spending. Saved exclusions/corrections can change the modeled base. |
| Kai · `CUST01331` | Last balance 1,780.94 on 2026-09-30; seven-day safe estimate 78.14 after 500.00 reserve, 975.26 scheduled housing and 227.54 historical allowance | Expected obligations and allowance are pattern-based. The result is not a spending guarantee; goal allocations and unsaved tax plans are not deducted. |
| Taylor · `CUST00296` | Last balance 41,695.70 on 2026-09-27; linked `C0115` has 19 events from 2026-07-15 to 2026-08-12; historical property 290,000, requested loan 266,000, equity 24,000, fees 630; historical rejection reason `insufficient_income` | Historical application context does not establish a current mortgage, repayments, present available equity, affordability or a new decision. |
| All six personas | No explicit tax records in the current dataset; no household/spouse/children data | Missing tax evidence is not zero tax liability. Family wishes must be hypothetical or user-declared. |

Consumption excludes saving/investment transfers. Account inflows and investment withdrawals are not proof of earned income or investment returns. VAT is an estimate already inside purchases, distinct from income tax and personal liability. Forecasts use recorded patterns; their historical variation is not a probability. Wishes, preferences and entered saved amounts are user declarations, not independently observed savings or life events.

## Validation status

| Check | Status | Evidence / next action |
|---|---|---|
| V2 source/documentation reconciliation | Inspected | Current `index.html`, `app.js`, V2 plan and existing finance definitions used for this record |
| Focused regressions | Passed within the integration suite | Query scope/percentages, aspirations/consent, conversation, presentation and integration suites included in the current run |
| Full suite and API checks | 305 passed; 1 skipped | Final integrator run: 306 tests in 14.590 seconds, `OK (skipped=1)`; the skip is optional browser integration. Restarted local API also returned the same Kai estimate for EN/FI/SV starters. |
| JavaScript syntax checks | Passed | Integrator reported all web JavaScript syntax checks passing |
| Whitespace/diff checks | Passed | Integrator reported `git diff --check` passing; documentation checked again after this update |
| Independent source review | Complete; no remaining Critical/Important source findings | Reviewer separately checked plan compliance and implementation quality, then independently rechecked the three repairs below |
| Browser and responsive acceptance | Unverified; saved origin permission remains denied | User elected to open the local app/device-preview URLs manually; no manual acceptance result has been supplied |
| Live Gemini | Unconfigured / unverified | A successful provider response and diagnostic source are required before claiming this path |
| Human usability | Not performed | Source/tests do not establish that customers understand or prefer the experience |

The integration run on 2026-11-14 used this command from the repository root:

```sh
env -u SCOACH_PLAYWRIGHT_PATH PYTHONPATH='s bank' python3 -m unittest discover -s 's bank/tests' -q
```

Independent review identified three issues, each reproduced before repair and checked again afterward:

- Unsent Coach drafts survived a persona change. They now clear on persona, period, language, reset and new-conversation changes; ordinary page navigation retains the draft.
- A demo story waiting on account data could resume under a different customer. It now keeps the initiating context and conversation sequence, cancelling after persona/period/language changes or a new conversation, including a language round trip.
- The exact FI/SV safe-to-spend starters failed to reach the calculation. Bounded query handling now accepts the shipped prompts, and Home reuses the same canonical localized prompt. Unsupported historical safe-to-spend requests still ask for clarification.

The final suite ran after these repairs. JavaScript syntax and whitespace checks passed. The local server was then restarted with the final backend; live API checks returned Kai's EUR 78.14 estimate for all three supported starter languages using 2026-09-30 and seven days. Health still reports Gemini unconfigured.

No browser, Playwright, CDP, proxy, alternate origin or other route has been used to bypass the denied origin permission. Historical screenshots are not V2 visual evidence.

## Remaining rendered acceptance checklist

Once approved CUA access is restored, use the existing demo and device-preview page to record only observed outcomes:

- [ ] At 320, 390, 768 and 1440 CSS-pixel widths, inspect four-page navigation, wrapping, donut geometry, labels, tap targets and the Coach composer without overlap or horizontal overflow.
- [ ] In EN/FI/SV, complete the three demo stories, inspect account/date scope and open readable evidence without raw identifier clutter.
- [ ] Submit the 20% dining starter, 12.5% and 10% variants, a supported dated question, a scoped follow-up and an unsupported/ambiguous request; verify an answer, clarification or recoverable error for every question action.
- [ ] Keep a title-only wish; verify navigation persistence, explicit browser-memory consent, persona isolation, removal/revocation and the optional numeric planner.
- [ ] Inspect inline forecast, investment transfers, historical financing and VAT; verify assumptions, missing-data language and the exact scenario-to-goal handoff.
- [ ] Exercise keyboard focus, native scrolling, loading/retry, stale responses and language/persona/month changes.

The final handoff must retain any unchecked items and distinguish source/test results from browser and live-provider evidence. No commit, publication or deployment is part of this documentation update.

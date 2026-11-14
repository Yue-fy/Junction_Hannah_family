# Conversation and logic audit

This follows the user's movie-planning screenshot and [repair plan](CONVERSATION_REPAIR_PLAN.md). It supersedes the V2 record's conversation presentation and verification totals; the earlier record remains historical evidence.

## Customer-visible behavior

Coach now leads with a natural-language answer containing the relevant amount, meaning and date scope. Calculation cards, charts and source details are supporting disclosures. A request for a chart can open the supporting view; Direct style still leads with prose.

The reported prompt, `I want to go see a movie this week`, asks for a total budget instead of returning September Entertainment spending. A simple reply such as `€20` continues that plan within the same customer/month/language. Using Alex's September 30 synthetic snapshot, the returned comparison is EUR 20 against a seven-day allowance of EUR 3,288.31, leaving EUR 3,268.31 in that model. This is not a statement about today's bank balance or a spending guarantee. Explicit historical Entertainment questions still return the observed EUR 386.06.

This remains a bounded local financial-query experience when Gemini is unconfigured. Exact-price previews cover recognized everyday purchases and one EUR total up to 500; larger purchases, recurring commitments, ambiguous prices and unsupported dates require clarification. Invalid or ambiguous amounts request a full restatement rather than silently choosing a number. The change does not claim unrestricted conversational understanding.

## Reproduced defects and repairs

| Area | Prior failure | Repair / evidence |
|---|---|---|
| Intent and scope | A category word converted future plans into historical statistics; unsupported week predicates were ignored | Planned-purchase routing precedes statistics; unsupported or mixed scope asks for clarification; `test_planned_spending.py` |
| Prose and details | Generic introduction plus a large card, with Direct style putting the card first | Tool-specific factual prose, collapsed details, missing-value handling and EN/FI/SV tests in `test_coach_narrative.py` |
| Follow-ups | Movie clarification retained an unrelated historical category | A price reply continues only the immediately pending purchase plan; unrelated previous statistics scope clears |
| Retained actions | An older scenario lost its action; dated forecast/investment actions opened the current global period | Actions remain associated with their turn and use its response; inline detail uses that answer's dates |
| Evidence | Safe-to-spend and forecast omitted historical buffer sources; comparison sources used only one period | Union and deduplication of calculation/history sources, including nested forecast records; both comparison periods remain inspectable |
| Comparison details | Income/count prose disagreed with a supporting table hardcoded to outgoing money | Details honor the requested metric and unit |
| Spending ring | Category evidence included positive refunds omitted by the consumption chart | The row request uses the same consumption filter |
| Customer switching | A failed new-account load could leave the previous customer's amounts visible | Scoped financial surfaces clear before loading; `test_feature_audit.py` |
| Goal retry and reset | A successful goal POST followed by failed refresh could duplicate on retry; reset desynchronized the visible page | Retain acknowledged creation until refresh completes; preserve the visible navigation state |
| Goal capacity | Another customer's longer history could supply nonexistent months | Capacity uses the selected account's observed span; `test_goal_boundaries.py` |
| Scenario linking | Linking an occupied scenario could silently remove it from another goal | Reject reassignment and preserve the original link and audit state |
| Tax planning | Some future tax-planning questions selected historical tax evidence; clarification lost its form action | Explicit planning intent and a reachable amount/date form; historical paid-tax and VAT remain separate |
| Insufficient funds wording | A zero allowance could still imply the reserve and bills were covered | State that no extra spending room is estimated; describe deductions without promising funded reserves |

## Validation record

- New defects were reproduced before repair, then checked again in focused tests.
- A read-only API sweep exercised six personas, three dates per persona and ten feature routes: 180 successful responses. This verifies availability, not every possible interpretation.
- Client regressions use the actual app code with a minimal DOM. Backend write tests use isolated temporary databases; the live demo database was not reset or rewritten for testing.
- Final integration on 2026-11-14: **361 tests discovered, 360 passed, one optional browser test skipped**, in 16.536 seconds. Command: `env -u SCOACH_PLAYWRIGHT_PATH PYTHONPATH='s bank' python3 -m unittest discover -s 's bank/tests' -q`. JavaScript syntax and whitespace checks passed.
- Independent source review rechecked the repaired conversation paths, metric/evidence consistency, future tax planning, liability and unsupported timing guards. No Important findings remained in those reviewed paths.
- The local server was restarted with the final code. Eleven live read-only question checks passed, including the screenshot's movie prompt, its EUR 20 continuation, historical totals, zero spending room, tax planning/liability, explicit payday timing, forecast, investment and VAT. Actual responses were also passed through the narrative formatter; the movie request produced a budget question and the EUR 20 continuation produced the dated planning explanation.

## Explicit remaining limits

The browser tool's saved local-origin denial is still in place. No alternate browser, Playwright, CDP, proxy or origin bypass was used. The supplied screenshot establishes the reported failure, but this repair has no new rendered desktop/mobile walkthrough or screenshots. Native layout, keyboard and touch acceptance remain unverified.

Gemini is unconfigured on the local server; no live-provider or unrestricted-language success is claimed. The existing synthetic dataset does not establish current balances, household finances, tax liabilities, investment returns or a current mortgage.

# Conversation and functional repair

The user reports that a planned cinema visit receives a historical Entertainment statistics card. The requested behavior is natural-language coaching first, with tables and visualizations as supporting material. This continues the authorized redesign and functional testing; it does not introduce a new framework, endpoint, data schema, dependency or provider configuration.

## Observed causes

- A recognized category currently enters statistics even without a request for historical facts. Requested week/item precision can be discarded.
- Calculation responses use generic introductions, followed by large cards; Direct style explicitly puts the card first.
- Actions belong only to the newest rendered answer, while older answer text remains.
- Account-switch failure can retain old rendered data; a successful goal creation followed by refresh failure can create duplicates on retry; reset can desynchronize the visible page and navigation state.
- Coach evidence can omit the historical flexible-spending buffer used in safe-to-spend.

## Implementation

- [x] Recognize everyday planned purchases before historical statistics. Ask only for missing information; a known cost can be compared with the existing dated spending estimate, without claiming general affordability.
- [x] Stop unrelated fallback stories and clarify unsupported date/item scopes instead of substituting monthly broad-category totals.
- [x] Lead supported tool answers with concise factual prose: answer, relevant scope, and necessary interpretation. Keep detailed calculations/evidence collapsed; show optional graphics after the answer only when requested.
- [x] Retain useful actions with their original turn and exact scenario scope. Carry a bounded price clarification only within the initiating account/month/language; other questions must remain independent.
- [x] Repair the confirmed account-loading, goal-retry, reset and evidence issues, each with a failing-before/passing-after regression.
- [x] Exercise representative free-form requests and all main feature families using temporary databases, actual read-only API responses and the client harness. Run the final full suite and independent review.

## Review focus

1. “I want to go see a movie this week” must not become September Entertainment spending; “€20” must continue the appropriate clarification safely.
2. Historical questions retain exact metric, dates and filters; missing data is not zero; broad categories are not proof of specific purchased items.
3. Prose contains the actual answer and useful qualification before any card, including Direct style and no-history cases.
4. Switching identity, failed refreshes, retry and reset must not leak a prior customer's values or duplicate an acknowledged write.
5. Every retained action and evidence source uses its original answer scope; no preview moves money or saves a scenario automatically.

The saved browser-origin denial still prevents rendered desktop/mobile testing. No alternative browser route will bypass it. The supplied screenshot is valid evidence of the reported defect; Node/HTTP tests do not establish rendered acceptance. Live Gemini remains separately unverified.

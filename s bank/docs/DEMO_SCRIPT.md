# S-Coach V2 demo script

Start the project with the repository-root commands in the [README](../README.md). Reuse the existing database and preserve saved customer work. If a fresh import is needed, use a separate output path. The six customer names are aliases for synthetic accounts, not biographies.

This is a recording script, not evidence of a completed browser walkthrough. Approved CUA access to the local origin is currently blocked; phone, tablet, desktop and live-AI acceptance remain unverified. See [V2 acceptance](EXPERIENCE_V2_ACCEPTANCE.md). Gemini is unconfigured: demonstrate bounded deterministic coaching, not unrestricted language understanding.

## The four-page journey

**Home** gives a recorded-balance summary, a useful next question and a compact spending overview. **Spending** holds the single category donut, selectable category rows and transaction evidence; trends, forecast, transfers and VAT are collapsible details. **Coach** is a full page with account/date context, inline answers and a composer. **Goals** starts with a title-only wish; a numeric plan is optional. Journal and the editable notebook remain secondary tools.

Use **Try a story** to enter each story. The button selects the correct persona and September 2026, opens Coach and submits a real question. Confirm the displayed account, dates and response before continuing.

## Story 1 — Kai: make room for the coming week (30–45 seconds)

1. Choose **Try a story → Make it through the week** (`CUST01331`). The weekly-spending question should produce an inline estimate.
2. Show the last recorded balance: **EUR 1,780.94 on 30 September 2026**. Explain the seven-day estimate: **EUR 78.14** after a **EUR 500.00** reserve, **EUR 975.26** scheduled housing and **EUR 227.54** historical everyday allowance.
3. Open the assumptions/evidence. Expected bills come from past patterns; this is not a guarantee or a live bank balance. Goal allocations and unsaved tax plans are not deducted.
4. Ask `Show cash flow` and inspect the inline ending/lowest balance estimates. The forecast's reference date and assumptions matter; the shaded variation is not a probability.

> “A balance is only the starting point. Here is the room the recorded patterns leave for this week.”

## Story 2 — Alex: a small change, then a wish (60–90 seconds)

1. Choose **Try a story → Turn a small change into a possibility** (`CUST00001`). The restaurant comparison should show **EUR 225.70 across 10 September transactions**, versus **EUR 115.43 across 10 August transactions**. This is a spending change, not evidence of changed motivation or household circumstances.
2. Open **Spending**, select Eating out and inspect its rows. The donut represents the selected consumption group; saving and investment transfers are separate. Return to **Coach**; navigation should preserve the conversation.
3. Use the exact starter `How much could I save by reducing dining out by 20%?`. The baseline contribution is **EUR 45.14**. Try `How much could I save by reducing dining out by 12.5%?` for **EUR 28.21**, or `... by 10%?` for **EUR 22.57**. Show observed and modeled spending together. Reading an answer saves no scenario and moves no money.
4. Ask `I want to save but I do not know how much`. Follow the invitation to **Goals** and keep a title such as **A little more breathing room**. No amount or deadline is required. Without browser-memory consent the wish lasts for this visit; explicit consent permits storage in this browser for that persona.
5. Only if useful, choose **Make a detailed plan** and supply a customer-selected target, date, saved amount and reserve. Alternatively, the scenario's explicit goal action saves that exact category, percentage and month before opening the planner. Confirm any goal link separately; it creates no payment or automatic transfer.

An optional scope check is `How much did I spend on restaurants in August 2026?`, followed by `And groceries?`. Both answers must show August. Starting a new September question about groceries has a baseline of **EUR 379.79**. Unsupported dates, qualifiers or ambiguous affordability requests should ask for clarification instead of silently changing the question.

## Story 3 — Taylor: historical context and a future home wish (45–60 seconds)

1. Choose **Try a story → Understand a home-financing history** (`CUST00296`). Open the inline timeline: **19 historical events, 15 July–12 August 2026**, linked to mortgage customer `C0115`.
2. Show the historical property estimate (**EUR 290,000**), requested loan (**EUR 266,000**), equity recorded then (**EUR 24,000**) and recorded fees (**EUR 630**). The application was historically rejected with reason `insufficient_income`. Taylor's separate latest balance record is **EUR 41,695.70 on 27 September 2026**; it does not turn the old equity into current available savings.
3. Choose the future-home wish action and keep **A future home**, with no target or date. A detailed plan begins only when the customer supplies those inputs.

> “These records describe a past application. They do not establish a current mortgage, repayment status, household finances, affordability or a new lending decision.”

The dataset contains no spouse, children or household composition. Any family-home narrative must be explicitly hypothetical or declared by the demo user.

## Optional details to preserve

- **Preferences and Journal:** let the customer choose a focus, protected categories and coaching style. Inspect source-backed money moments and editable notes; do not infer holidays, motives or life events from a payment. Browser memory is optional and can be revoked. Milestones use only entered saved amounts.
- **Investment transfers:** ask `Show my investment transfers`. Read the inline period and deposits/withdrawals. These account transfers do not establish holdings, returns, risk or investment advice. Incoming transfers are not earned income; credited salary does not establish gross pay before tax.
- **Tax and VAT:** all six personas have no explicit tax records in the current dataset. Missing records do not establish zero tax paid or owed. VAT is estimated inside purchases from date/category mappings, not income tax or personal liability. Review coverage and assumptions; do not add VAT to spending again.
- **Tax planning:** in **Coach → More ways to explore → Tax & VAT**, enter a user-declared amount, due date and where any existing set-aside is held. Inspect monthly set-aside, protected balance, reserve and any funding gap. This remains an unsaved planning scenario, not tax advice.

## Baseline and recording checks

All amounts above are audit baselines for the stated synthetic account and period, subject to saved corrections. A one-off exclusion changes the repeatable scenario base, not observed spending. Alex's audited seven-day safe-to-spend baseline is **EUR 3,288.31**. If displayed values differ, inspect account, period, corrections and assumptions before recording; do not reset customer work merely to match the script.

- Complete the authorized rendered walkthrough before recording. Target 390 × 844 for the primary recording, then check 320, 768 and 1440 CSS-pixel widths using the approved surface and existing device-preview page.
- Check EN/FI/SV copy, category selection, evidence, keyboard focus, conversation navigation, composer visibility, error/retry and persona isolation.
- Keep the synthetic-data disclosure visible at least once. Do not expose keys, terminal environment, raw CSV or personal messages.
- Claim live Gemini only after a configured response's diagnostic source proves a successful provider call. Older screenshots and prior test totals do not validate V2.

## Conversation repair check

On Alex / September 2026, ask `I want to go see a movie this week`, then answer `€20`. The first turn should ask for a total budget; the second should explain the dated planning comparison in prose. It must not substitute September Entertainment spending. Calculation details remain optional. Ask `How much did I spend on restaurants?` to see the exact observed EUR 225.70 stated in a sentence before supporting details. Ask `How much tax do I owe?` to see the data limit and declared-payment planner, rather than a historical-tax total. These are bounded local paths; live Gemini and rendered browser acceptance remain unverified.

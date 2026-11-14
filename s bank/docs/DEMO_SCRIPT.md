# S-Coach V2 demo script

Start the project with the repository-root commands in the [README](../README.md). Reuse the existing database and preserve saved customer work. If a fresh import is needed, use a separate output path. The six customer names are aliases for synthetic accounts, not biographies.

The Coach page now uses the tool-calling agent when configured, with the existing deterministic answer as fallback. DeepSeek is configured through the ignored local environment; Gemini remains an alternative. Verification details and limits are recorded in [the development log](DEVELOPMENT_LOG.md). Historical V2 acceptance documents describe their earlier runs, not a fresh acceptance claim for this build.

## Agent chat walkthrough

1. Open Coach and check the account/month chip. Ask `How much did I spend on restaurants in September?`. The footer identifies an AI answer or offline fallback; do not present a fallback as live AI.
2. Ask `What about groceries then?`, then `Compare restaurants with August`. Check the same period/context, returned amounts and the comparison chart. Open **How I worked this out**, then an evidence item to inspect matching transactions.
3. Ask `How much could I save if I reduced dining out by 20%?`. If offered, open **Review spending scenario**. Nothing is saved until **Confirm & save scenario**; the existing goal planner can then link the saved scenario.
4. Try `I want to save EUR 3000 for Italy by June 2027`. A goal proposal opens an editable form; inspect its amount/date before confirming. No money is moved by this prototype.
5. Use **New chat**, change month through the scope chip, and change persona to check that prior messages clear. At `/device-preview.html`, inspect 375×812, 390×844 and desktop layouts with three exchanges.

The current minimum packages do not include open-data benchmarks, the generic exploration tool or the newer payday-horizon calculation. Do not claim those capabilities. A missing peer comparison must stay unavailable. Model wording and optional cards can vary; broader live conversational evaluation remains separate work.

The three original stories below describe the deterministic flows and their recorded dataset values. Use them as offline demonstrations; they are not promises that every live-agent answer chooses the same wording, card or action.

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
- **Tax planning:** in **Coach → account/month chip → More ways to explore → Tax & VAT**, enter a user-declared amount, due date and where any existing set-aside is held. Inspect monthly set-aside, protected balance, reserve and any funding gap. This remains an unsaved planning scenario, not tax advice.

## Baseline and recording checks

All amounts above are audit baselines for the stated synthetic account and period, subject to saved corrections. A one-off exclusion changes the repeatable scenario base, not observed spending. Alex's audited seven-day safe-to-spend baseline is **EUR 3,288.31**. If displayed values differ, inspect account, period, corrections and assumptions before recording; do not reset customer work merely to match the script.

- Complete the authorized rendered walkthrough before recording. Target 390 × 844 for the primary recording, then check 320, 768 and 1440 CSS-pixel widths using the approved surface and existing device-preview page.
- Check EN/FI/SV copy, category selection, evidence, keyboard focus, conversation navigation, composer visibility, error/retry and persona isolation.
- Keep the synthetic-data disclosure visible at least once. Do not expose keys, terminal environment, raw CSV or personal messages.
- Claim a live model answer only when the footer/response identifies the agent, using the configured provider. Numeric verification or provider failure can trigger offline fallback even when a key is configured. Older screenshots and prior test totals do not validate a later build.

## Conversation repair check

On Alex / September 2026 with offline coaching, ask `I want to go see a movie this week`, then answer `€20`. The first turn should ask for a total budget; the second should explain the dated planning comparison in prose. It must not substitute September Entertainment spending. Calculation details remain optional. Ask `How much did I spend on restaurants?` to see the exact observed EUR 225.70 stated in a sentence before supporting details. Ask `How much tax do I owe?` to see the data limit and declared-payment planner, rather than a historical-tax total. These are bounded local paths; live agent responses need separate semantic checks. Current browser and DeepSeek evidence is recorded in the development log.

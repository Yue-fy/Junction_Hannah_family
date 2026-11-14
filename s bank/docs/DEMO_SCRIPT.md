# S-Coach Demo Script

Start the project using the repository-root commands in the [README](../README.md). Reuse the existing demo database when it contains all six personas, including `Kai · CUST01331`. If a fresh import is necessary, build to a new output path and start the server with that path; do not overwrite the existing database or its saved demo state.

Use a 390 × 844 viewport for the recording, then briefly widen the browser at the end to show the same app adapts to desktop. The development-only `/device-preview.html` page also offers phone, tablet, and desktop presets.

This script covers a supported deterministic demo path. Narrow-category interpretation, dates written in a question, and follow-up context remain known gaps; see the [README](../README.md). Select the period in the interface and use a complete question. Do not present the taxi prompt as a correct taxi-specific answer.

## Two-minute judge story

### 0:00–0:12 — one useful home, not another statement list

Open Alex (`CUST00001`) in September 2026.

> “S-Coach lets an S-mobiili customer talk with their own money. It starts with a readable overview, not a blank chatbot: balance, income, the three financial-literacy baskets, saving, and the one issue worth looking at.”

Point to the month selector and the regular / irregular / everyday labels. Mention that the corrected partner mapping places groceries and transport under regular essentials and replacement appliances under irregular essentials.

### 0:12–0:37 — ask an exact private-account question

Select **Alex → September 2026 → English**, open **Ask coach**, and type **How much did I spend on restaurants?**

> “This demo works without an AI key. A local router selects the statistics tool, which calculates the restaurant total from the selected account and month. The optional AI adapter can help interpret questions, while the local service still performs the arithmetic.”

Show the local result: **EUR 225.70 across 10 restaurant transactions**, with a **EUR 22.57 average purchase** and evidence access. The answer remains available with Gemini disabled. Confirm the selected month and matching restaurant rows rather than treating a valid total as proof that every possible question is understood correctly.

### 0:37–0:58 — understand behavior, then try a change

Choose **What kind of spender am I?** and show the neutral three-basket amounts without a score or judgment. Then choose **Reduce dining out by 20%**.

Show the read-only **EUR 45.14 per month** preview from the observed **EUR 225.70** base.

> “A suggestion is not an action. This preview is unsaved, actual spending stays untouched, and linking it to a goal still needs confirmation.”

If time permits, open the restaurant story, mark the EUR 36.47 row as a one-off, and show the scenario changing to **EUR 37.85** while actual spending remains EUR 225.70.

### 0:58–1:18 — make tax understandable

Go to **Trends → VAT inside your spending**.

> “Finnish prices often include VAT, but most people cannot see it. S-Coach estimates the tax inside supported purchases using the transaction date and MCC first, with a visible category fallback. Ambiguous rows are labelled or left uncovered.”

Show **approximately EUR 212.38 VAT inside EUR 1,878.66 of September spending**, the rate split, mapping coverage, and a transaction's rate/source quality. State that coverage is not confidence, and that excise duties and personal tax liability are not included.

### 1:18–1:42 — personalized young-adult cash-flow coaching

Switch to Kai (`CUST01331`).

> “Personalization changes the first story. Kai is 18. After rent and a larger clothing purchase, the observed balance reached minus EUR 11.82 one day before salary. The coach highlights timing rather than blaming the purchase.”

Open the payday insight and the pattern-based 30-day preview. Point out the reserve, qualified recurring outflows, historical unscheduled-spending buffer, and assumptions.

### 1:42–2:00 — goals and S-mobiili fit

Open **Goals**, select **A vehicle** or **A home**, and show target, amount saved, date, and reserve.

> “The same engine works for a buffer, car, home or any goal. It creates no transfer and predicts no loan approval. The responsive web experience can be embedded in S-mobiili; on desktop it becomes a two-column workspace using the same source-backed calculations.”

Briefly widen the viewport. End on the synthetic-data and planning-support disclosure.

## Optional second experience: home preparation (45–60 seconds)

Switch to Taylor (`CUST00296`) and open **Ask coach → Home or vehicle preparation → Explain linked home-financing history**.

Show the chronological historical context and recorded fees. Say explicitly:

> “These are past synthetic mortgage events. They help the customer prepare questions; they are not a current affordability assessment, offer, recommended loan amount or approval probability.”

Move to **Goals**, choose **A home**, and enter a customer-selected target/date/reserve. Show the monthly pace and calculation drawer. Then switch the template to **A vehicle** to demonstrate that the planner is personalized and not mortgage-only.

## Optional tax-planning experience (30 seconds)

Open **Ask coach → Tax and VAT → Plan a tax payment**. Enter a customer-declared amount and future due date.

Show the monthly set-aside, balance protected, reserve, and funding gap. Point to **Unsaved scenario** and **Not tax advice**. Then open **VAT inside spending** to show that purchase VAT is a different, transaction-derived feature.

## Recording checklist

- Check that the existing database contains all six personas. Use a separate fresh database for a clean recording when preserving saved demo state matters; reset Alex only when you intend to clear that persona's user-created state.
- Keep Gemini disabled for the deterministic core. Only claim a live Gemini path after configuring it and verifying the response's diagnostic source; configuration alone does not prove a successful model call.
- Do not expose a key, terminal environment, raw CSV, or personal Discord content.
- Keep the browser URL local and the disclosure visible at least once.
- Capture exact values before recording; stop if any number differs from the gold checks above.
- Record the phone-sized primary flow first. Desktop adaptability and optional flows come after the main story is safely captured.

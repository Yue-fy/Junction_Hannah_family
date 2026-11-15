# trust: are S-Coach's numbers correct and consistent?

Server: own copy on :8105. Personas checked: Alex (CUST00001), Taylor (00296), Robin (00676), Sam (05097, irregular income), Kai (01331), Jules (00756). Months checked: Sep and Aug 2026. Locales checked: EN, FI, SV. Screenshots are in `shots-trust/`.

**Verdict.** The arithmetic is honest: every euro figure ties back to the ledger, balance chains have zero breaks, and Home, Spending and the year review agree on income and spending for a given month. The problem is **definitions**. "Saved", "safe to spend", "payday" and "capacity" mean different things on different screens. A judge will see the numbers contradict each other within 30 seconds.

## Ranked discrepancies

### 1. "Saving rate 9.6%" every month, including months where Alex ran a deficit
- **Where it appears:** Spending › Money in vs money out says "Your saving rate stayed at 9.6% from October 2025 to September 2026". The chart directly above it shows the "Left over" line below zero in Jul (−€327.53) and Aug (−€365.50). `/api/cashflow/summary` reports `saving_rate_percent: "9.6"` together with `net_cents: -36550` for 2026-08. The year review card says "9,6 % tuloistasi", the spender profile says "share_of_salary 9.6", and Me says "about €228 to investments … fixed amount €227.74".
- **Cause:** both the data and the formula.
  - **Data:** in the synthetic set, `Invest Deposit` is exactly a fixed percentage of each salary, identical to two decimals in all 24 months. Alex is 9.63%, Taylor 10.58% and Sam 25.18%. Robin, Jules and Kai have no deposits, so they show 0.0% forever.
  - **Formula** (`scoach/cashflow.py:19`): savings transfers ÷ income. Money that stays in the account is never counted as saved.
- **Consequences:**
  - Taylor's 2025 year review says "saved €3,270, 5.6%", yet the balance rose €14.3k → €30.6k (income €58.5k, spending €38.9k).
  - Jules shows 0.0% while the balance grew €3.7k.
  - Taylor's Spending sentence reads "saving rate went from **-46.5%** in October 2025". A €2,548 investment withdrawal produced a negative saving rate.
- **Fix:** define saving rate as (income − consumption) ÷ income, and show "of which moved to investments" as a sub-line. Add ±noise to deposits in the generator.

### 2. Payday is wrong: the median of a bimodal set gives the 22nd, a day salary never arrived
- **Where it appears:** Safe-to-spend says "until payday on 22 Oct 2026 (22 days)". The forecast books salary on 22 Oct. Me says "Your salary arrives on different days each month".
- **Data:** Alex's last six salaries came on the 15th, 29th, 30th, 31st, 15th and 15th. `forecast.py:36-39` takes the median day, (15+29)/2 = **22**.
- **Effect:** with as_of 2026-09-10 the app predicts payday on 09-22, but salary actually landed on 09-15. Per-day and per-week allowances are spread over 22 days instead of 15, and the forecast's "lowest balance 21 Oct" is an artefact. Sam (irregular income) also gets "22 Oct (23 days)".
- **Fix:** use the mode of the day-of-month, or the most recent day. When the spread is large, show "payday unclear" and let the user set it.

### 3. Safe-to-spend contradicts itself, and contradicts Goals
For Alex as of 30 Sep, the Spending › Room to spend card shows:
- "You can spend this week **€1,138.27**", about €162.61 a day. That is Alex's whole €3,577.63 free balance divided by 22 days.
- "You could **also** move about **€2,298.84** to savings and still cover a typical run to payday."
- Spending €162.61/day × 22 = €3,577 **and** saving €2,298 = €5,876, which is more than the €3,577 free. The "also" double-counts.

The per-day figure also ignores Alex's own pattern. His median 30-day everyday spend is €1,401, about €47/day. Groceries are classed as "Must-pays" but are **not** in "Bills before payday" (only Housing and Utilities are), so they are reserved nowhere.

Goals › "A summer in Italy" (€3,000 by 31 Mar 2027) shows "Cautious monthly capacity: **€0.00** … Planning gap: €500.00 / month. Try a later date or a smaller target", plus "Available above reserve: €4,223.58". So Spending says "move €2,298 to savings now", while Goals says he cannot afford €500/month. The cause is that `goals.py:56` uses the 25th percentile of the last six free-cash-flow months (−€327), which floors to 0.

**Fix:**
- free = balance − reserve − bills − everyday buffer.
- per-day = free ÷ days.
- safe-to-save = what is left after that.
- Feed the same number into Goals.

### 4. Two different "this week" numbers for the same moment (the old 7-day number is still live)
- **Alex, as of 2026-09-30:**
  - `horizon=until_payday` gives this_week **€1,138.27** (shown in the Spending card and the offline Coach).
  - `horizon=week`, and the default `/api/safe-to-spend` with no horizon, give **€3,288.31**.
- **Kai, as of 08-31:** €49.63 from one horizon and €43.42 from the other.
- **Where the old number can still surface:** the legacy renderers are still in place (`app.js:470` and `app.js:664`), and `agent_tools.py:418` routes `safe_to_spend` to the 7-day function whenever the model passes `days`.
- **Offline Coach text mixes both models:** "The spending estimate is €1,138.27 for the next 7 days, **through 22 Oct 2026** … deducts €500.00 demo reserve and €645.95 expected outflows." 4,723.58 − 500 − 645.95 = 3,577.63, not 1,138.27. The sentence does not add up.
- **Fix:** delete the 7-day path or make it alias until_payday, and rewrite the Coach sentence as "€3,577 free until 15 Oct → about €X this week".

### 5. Safe-to-spend gives absurd figures for savers
Weekly figures shown in Spending:
- **Taylor** ("Optional home goal" persona): "You can spend this week **€15,490.65** … €2,212.95 a day".
- **Sam:** €11,375.14 a week.

Both persona stories are about saving, but the entire savings balance in the current account counts as spendable. The weekly figure should be capped by typical spending (e.g. p75 × 1.5). Above that cap, show "You have plenty of room; consider moving €X to savings."

### 6. Month switching shows two months in one card
With **August 2026** selected, the Home balance card shows "Last recorded balance €4,723.58 · Recorded 30 Sept 2026" next to "Income €2,408.31 / To savings €231.92" (August values). The safe-to-spend card in the same view says "Balance now €4,390.15" (31 Aug). Two different "now" balances appear in one month view.

**Fix:** either label the card "Today" with the Sep figures, or show the month-end balance for the selected month. Pick one.

### 7. The spender archetype contradicts both the persona and the data
- **Alex:**
  - The persona story is "Everyday spending", but the archetype is **"Big-Ticket Occasional"**, based on "1.5 Little-leaks purchases a week".
  - In September alone Alex had 15 restaurant and entertainment purchases (3.5 a week).
  - The rule says "54.9% of Little leaks came from purchases of €100+"; in the year review it is 73.1%. "Little leaks" that are mostly €100–€677 purchases (a car rental) make the basket label nonsensical.
- **Sam:**
  - Spender profile (Sep, six months) says **"Balanced"**, with Little leaks at 44% of spending and "Travel adds up to about €20,218.80 a year".
  - The 2025 year review says "Big-Ticket Occasional".
- **Kai:** the "strength" shown is "Must-pays were 82.4% of your spending", which is a risk, not a strength.
- **Entertainment annual figure for Alex disagrees across screens:** spender profile says "€1,904.10 a year" (six months × 2); the 2026 year review says "€2,551.00 a year" (nine months scaled up).
- **Fix:** exclude Travel and one-off purchases above a threshold from Little leaks, never present a Must-pays share as a strength, and use one window for every "per year" claim.

### 8. Year review: partial-year comparisons and overlapping "left over" and "saved"
- The 2025 "Saved" card says "Edellisenä vuonna: 661,87 €". That is 3 months of 2024 against 12 months of 2025, with no caveat. The API knows `comparable: false`, but the UI ignores it.
- 2026 (9 months) is compared with 2025 (12) as −27.1%.
- Card 1 says "Jäi yli 4 618,84 €" (left over) and card 2 says "Säästöön 2 817,83 €" (saved). The actual balance change was €1,801. Left over already includes the €2,818, so a user reads "€4.6k + €2.8k".
- "Busiest day" is 2025-07-04 with **count 1**, the same transaction as "largest purchase".

### 9. Tax estimates are plausible, but unlocalised and missing payroll deductions
- **No estimate without user input:** with no tax card, `has_tax_data: false` and nothing is estimated. That is honest, but empty for the demo.
- **Payroll deductions ignored:** with 24% and €3,400 gross entered, the app shows "Gross ≈ €30600.00 → withheld ≈ €7344.00 → received €21324.32". That line has no thousands separators, is **in English in the FI UI**, and is followed by English "Waiting for your tax decision" and English tasks.
  - The model ignores employee pension and unemployment contributions (roughly 8% in Finland), so `gap_is_large` will fire for every realistic user.
  - **Fix:** deduct about 8% for these contributions before comparing, and localise the server strings.
- **Tax calendar:** the 2026 tax-decision dates are plausible (decisions by 31.10, refunds and back-tax instalments per vero.fi).
- **VAT** is correct: 14% before 2026 and 13.5% from 2026, applied by date. Keep it.
  - **Bug:** the API returns `rate_display: "1E+1%"` for the 10% band (Nov 2024), from `Decimal.normalize()` in `vat.py:131`.

### 10. Benchmarks are mostly fair, but not price-adjusted
- **Mostly fair:** the "per consumption unit" figure for a single-person account, the age band from the customer record, and the clear caveats are good.
- **Not price-adjusted:** Alex's groceries (Apr–Sep 2026, €474/month) are compared with **2022 prices** (€360) as "+31.7% more". Food prices rose roughly 10–15% since 2022 (approximate), so about half of the "more" is inflation.
  - **Fix:** deflate with StatFin CPI (table 11xs) and say "in 2026 euros".
- **Coach does not route to benchmarks:** the offline starter "How do I compare with others my age?" gets classified as `compare_periods` and asks "Which category and dates?". The benchmark never appears in Coach.

### 11. FI/SV number formatting is inconsistent
- **Server percentages:**
  - FI shows "Säästöasteesi pysyi **9.6 %:ssa**".
  - SV shows "sparkvot låg kvar på **9.6 %**".
  - Both should use a decimal comma.
- **EN mixes separators:** because `en-FI` uses a decimal comma, the English VAT list shows "13,5 %" right next to "9.6%".
- **Untranslated strings in FI/SV:**
  - "Safe to save keeps back a busy…" assumption
  - all four "Things I noticed" questions
  - category labels on the year cards ("Groceries")
  - the archetype label "Big-Ticket Occasional" / "Balanced", even though FI and SV labels exist in the API
- **Chart axis labels are truncated:** "marras 2", "maalis 2".

### 12. Spending tab mislabels
- **Restaurant footnote under total spending:** the 12-month comparison (€25,369.24 → €24,972.69, which is total consumption) is footnoted "Observed **restaurant** spending".
- **"Average unavailable":** shown even with 275 purchases.
- **No sign on the change:** "Same-month change: €107.09" does not say up or down.
- **Inconsistent axis labels:** "25-10" style labels sit next to "Nov 25" elsewhere.

## Synthetic data problems a judge could spot
- **Salaries on weekends:** 43 of 139 salary credits fall on a Saturday or Sunday. Finnish employers pay on banking days.
- **Rent changes every month:** Alex has 24 distinct rent amounts (€490–€539).
- **Deposits are an exact fixed percentage of salary**, which is the cause of finding 1.
- **No refunds anywhere**, and no holiday bonus (lomaraha) in June or July.
- **Sam is 81 and paid a "Salary"** with irregular "Other income". That should be pension.
- **Unexplained overdrafts:** Robin has 85 rows with a negative balance (down to −€457) and Kai has 54. There is no overdraft line or fee, and the app never comments on it.
- **Odd archetype input for Robin:** "Payday Sprinter" is based on "Your balance dipped below €357.43 …", an arbitrary-looking threshold.
- **Safe-to-spend rejects month-end for three personas:** `/api/safe-to-spend` with `as_of=2026-09-30` fails for Taylor, Jules and Sam ("as_of is outside observed history") because their data ends 27–29 Sep. The UI avoids this by using `latest_balance_date`, but any other caller passing a month-end date gets an error.

## What works and should be kept
- **Ledger integrity:** zero balance-chain breaks across 3,626 rows, and every figure carries transaction refs.
- **Cross-screen agreement:** Home recap, three baskets, Spending totals and cashflow agree to the cent for a given month (e.g. Sep €1,878.66, Aug €2,541.89, delta €663.23).
- **VAT:** rates are applied by date (14% → 13.5%), with honest coverage notes.
- **Honest benchmark caveats**, plus a tax module that refuses to guess without a tax card.

## Top 5
1. The saving rate is a constant 9.6%: a fixed-percentage deposit in the data plus a transfers-only formula. It says "saved 9.6%" in months with negative net and ignores €16k of balance growth for Taylor.
2. The payday detector takes the median of a bimodal set, giving the 22nd, a day salary never arrived. Every until-payday figure and the forecast is spread over the wrong number of days.
3. Safe-to-spend contradicts itself: €1,138/week spend "and also" €2,298 to save, more than the €3,577 free. Goals says capacity is €0 and there is a €500/month gap.
4. Two "this week" numbers for Alex: €1,138.27 (until_payday) vs €3,288.31 (still the API default and reachable from the agent). The Coach sentence mixes "next 7 days" with "through 22 Oct" and its stated deductions do not add up.
5. Mixed months and locales: in August view the balance card shows 30 Sep €4,723.58 while safe-to-spend shows €4,390.15. FI/SV show "9.6 %" and English server strings (tax flow, notices, archetype, categories).

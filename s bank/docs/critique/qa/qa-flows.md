# QA: flows (390x844, English, port 8406)

Screenshots: /home/claude/critique/qa-flows/

## P1: broken, contradicting or confusing

1. **The mortgage plan double-counts housing on Home (Taylor).** I saved my own numbers (€200k, 2.3+0.6 %, 20 y) with the payment field empty and payment day 20. Home then held back both "Rent 4 Oct −€1,362.60" and "Mortgage payment −€1,099.21", so Held back went from €1,363 to €2,462 (`taylor-home-mort2-0.png`, `-1.png`). Payment day 20 comes after the 15 Oct payday, so the mortgage payment should not be held back before payday at all. When the payment is left equal to the detected €1,362.60, the line still says "Rent". Fix (payday-plan builder, scoach/cashflow.py or plans.py): when a mortgage plan is on, replace the detected housing bill with the plan payment, label it "Mortgage payment", and respect `payment_day`.

2. **The mortgage card mixes the entered payment with the calculated one (Goals, Taylor and Kai).** With the €1,362.60 payment entered, the headline says "You pay about €1,362.60 a month for 20 years… Of the €263,810 still to pay". €263,810 is 240 × €1,099, the calculated payment. The first year shows €13,191 (12 × €1,099). "If the rate rises by 1 point" shows €901.09, which is lower than the current €975.26 (`kai-mort-ratechange.png`). Fix (plans-mortgage.js and scoach/mortgage.py): base totals, the payoff date, the yearly split and the rate scenarios on the payment shown. Or, when they differ, show the payment shown and solve for the payoff date.

3. **The shortfall message blames bills when the cushion causes it (Home, Robin and Kai in steady mode).** Kai has €1,780.94 and €975 of bills, but the message says "Bills before payday are €965.35 more than you have free" (`kai-home-steady-0.png`). The gap comes from the €1,639 steady-mode cushion. For Robin, €1,220.72 includes €541 of cushion and buffer, while the 30-day chart says the lowest point is −€773 (`robin-home-0.png`, `robin-fc.png`). Fix (home-v4.js shortfall copy): split the message. Example: "Rent €853 is €541 more than your balance; your €500 cushion can't be kept this time." Use whole euros like the rest of the card.

4. **The saved surprise buffer is not held back (Home, Alex).** "Set aside €400 monthly" saves "about €400 each payday", but the payday plan still holds back "Surprise buffer, this payday −€204.58" and Could be saved stays €2,914 (`alex-buffer-saved-*.png`). Fix: use the saved buffer plan amount in the breakdown.

5. **The coach card repeats its prefix.** It reads "Using what you told me: Using what you told me: steady mode (lost your job)." (`kai-coach-safe.png`). The prefix is added in both scoach/catalogue.py:311 and web/answer-card.js:178 (`usingProfile`). Remove one.

6. **An empty tax plan says your tax is fine (Goals, Alex).** "Turn on my tax plan" with every field empty (all are optional) gives "Nothing to set aside. Your tax withholding looks enough for now." That claim is based on no data. Fix (plans-tax.js): require gross salary and rate, or show "Add your tax card numbers to check this".

7. **Home "Goals and plans" says "Nothing planned yet" while the mortgage plan is on** (Taylor; also Kai after turning on the mortgage plan). The tax and buffer plans are not listed either. Fix (home-v4 goals slot): list active plans.

## P2: polish and smaller inconsistencies

8. **"Careful mode" and "Steady mode" are used for the same thing.** Home says "Careful mode is on…" and Me, the safe card and coach say "Steady mode". Use one name.

9. **Steady mode still pushes saving.** The Surprise buffer card still says "€120 a month, ready by 31 Jan 2027". The coach follow-up chip offers "How much can I save this month?" right after "I won't push saving goals". On Me, "Would you call your income steady?" stays after the job loss. Hide or reword these while steady mode is on.

10. **Turning off steady mode on Me deletes the life event with no confirmation or undo.** "Lost my job" disappears from Me. Ask first, or keep the event and add a "steady mode paused" flag.

11. **Life-event "Since" is a free-text field that needs YYYY-MM-DD,** with no placeholder (`kai-me-after-0.png`). Use `type=date` or a month picker.

12. **Spending and Home show different "free" amounts (Taylor).** The Spending safe card says "Free until payday €38,447.05". Home says Free to spend €353 and Could be saved €38,094. Use the same split on both.

13. **Reopening "Change numbers" on the mortgage plan puts the detected €1,362.60 back in the payment field** after it was cleared. Saving again silently changes the plan. Prefill from the saved plan only.

14. **The tax plan accepts an expected back tax (€630) and an expected refund (€200) for the same year** and shows both. Warn about this, or net them.

15. **Me has two "Taxes" sections** (tax plan, then "Tax year 2026…"). The salary figure also disagrees: "about €2,365 after tax" on Me vs "about €2,325.60 after tax" in the tax form.

16. **The goal card on Goals was stale after Forget everything.** It showed "€2,861.01 more in your account" (the amount with the tax plan) until a reload, when it became €2,913.51. Re-render goals after profile changes.

17. **Alex's goal is "€500 a month" next to "you have about €195.51 left each month", with no warning.** Adding the €400 buffer makes €900 a month in commitments, and nothing flags it.

18. **"Make it a goal" (Home coach card) just opens the top of Goals with nothing prefilled.** The €2,914 suggestion is lost (`alex-makegoal.png`). Prefill a savings goal with that amount.

19. **The Forget everything confirmation has a "Change" button that does nothing useful** (it just disappears) and the copy "Nothing is saved until you tap Delete" (`alex-forget-confirm.png`). It also doesn't say that the tax and mortgage plans are removed (they are). Then a second "Are you sure?" step follows. Drop "Change" and say what gets removed.

20. **The payday date differs between screens in the first month (Alex, Oct 2024).** Home and the safe card say "Thu, 14 Nov". The 30-day chart labels payday "15 Nov".

21. **Reload resets the persona to Alex and the month to the latest** without saying so. Back and forward keep the tab, but not the persona or month. Persist both in the URL or sessionStorage.

22. **Status messages stick across pages.** The "Plan saved. It is now held back…" banner stays after moving from Goals to Home (`taylor-makegoal.png`).

23. **Home shows two different buffer numbers (Robin).** "Buffer €541" in the payday plan and "Suggested buffer €450" in the card below. Label the first "Cushion + buffer".

24. **Goals text says "around the 4."** where Me says "around the 5th". Use the ordinal helper.

25. **The coach safe answer shows a one-colour donut in steady mode** when everything is reserve (`kai-coach-safe.png`). Hide the donut when there is only one segment.

## P3: nice to have

26. Changing persona from any tab jumps to Home.
27. Kai's mortgage example is not sized to his €975 housing payment, but Taylor's is (Taylor is the persona with mortgage history).
28. "You told me 15 Nov 2026" uses the real date inside a Sept 2026 demo.
29. "Is this rent or a mortgage payment?" still shows on Me after a mortgage plan is saved.
30. The "Tell me about you (1 min)" chip still shows in Coach after the profile has facts.
31. In Oct 2024 the app calls `/api/comparison` with comparison_month=2024-09, which returns 400 ("outside observed coverage"), plus a 404 in the console on every load.
32. The headline "€18 a day" is rounded down from the €18.90 in the breakdown. Next to "Free to spend €174", readers may divide and get €11.60.

## Worked as expected

- The Taylor example is sized to the detected payment (€1,358.99 vs €1,362.60).
- Mortgage extra-payment suggestions are hidden in steady mode.
- The tax plan shows on Me and adds €52.50 to Held back on Home.
- Forget everything clears the tax plan and puts Held back back to normal.
- Comma decimals ("2,3", "200 000") are accepted.
- Negative or empty loan amounts are rejected with clear messages.
- Changing the month in Coach changes it on every screen.
- Back and Forward keep the tab, and close open sheets and dialogs.
- Robin's 30-day chart draws below zero clearly.
- The August vs September deltas on Home match the coach answer (€1,878.66, −€663.23).
- The empty "Surprise must-pays" filter shows a friendly message.

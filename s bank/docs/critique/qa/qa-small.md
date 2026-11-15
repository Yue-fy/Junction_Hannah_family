# QA: small phones (320x640, 375x812, English)

Server: 127.0.0.1:8401, persona Alex, Sept 2026. Screenshots and scripts are in /home/claude/critique/qa-small/ (file names below are relative to it). An automated check found no horizontal page overflow on any page (docW = viewport). Everything below comes from looking at the screenshots.

## P1: broken, ugly or confusing

1. **Me > Add something > "Coming up" cannot be saved.** Me, both viewports. The form sends `value: [{what, month, amount_cents}]` (an array). The server answers 400 `"upcoming must be an object"`, and the sheet shows "Could not save. Please try again." (e-320-add-after.png, me-320-b.png). "Note" saves fine. The same indexed-list form is probably used for **Loans** (debts) and **Life event**, so those likely fail too. File: web/money-profile.js (indexed list form, around line 1040, `type_0, monthly_0…`) against scoach/money_profile.py `_v_upcoming` / MULTI_KEYS. Fix: for MULTI_KEYS, POST one entry per row (`value: {what, month, amount_cents}`). Add a UI test that saves each key.

2. **The add form labels show dev indexes: "What is coming up (1)", "When (1) (optional)", "Rough cost (1)".** (me-320-a.png). Fix: drop the "(n)" suffix when there is one row, or use a "Row 2" style group heading.

3. **"Money in vs money out" chart is clipped and overlapped at 320.** Spending > More about your money, 320. The legend's left edge is cut off ("ey in"), and so are the x labels ("v 25", "Sep 26" at the right edge). In Year view the "Left over" legend item runs into "Partial period" ("Left ov▨Partial period"), at 375 as well. The tap highlight column also covers the legend and the "Mar 26" label. With no y scale, the "Left over" line sits almost flat on the bars' scale. (h-320-inout.png, h-320-inout-year.png, h-375-inout-year.png). File: web/charts.js cashflow svg (`legendItems`, around line 415). Fix: put the legend in HTML above the svg (wrapping) or in two rows. Add left/right padding in the viewBox for x labels. On narrow screens, label every 3rd month. Keep the highlight band inside the plot area.

4. **Coach answers open scrolled to the bottom.** Coach, both. After tapping a starter question, `scrollCoach()` scrolls to `#coach-end`, so the user lands on the follow-up chips. The question, the headline €1,878.66 and the bullets are scrolled out of view (mc-320-ans0.png, compare with md-320-a.png at scrollTop=0). File: web/app.js:801. Fix: scroll the new user bubble / answer card start to `block:'start'`.

5. **The Coach reading area on 320x640 is about 327px (51% of the screen).** Header 57 + Coach bar 57 + "Browse topics" 50 + composer with disclaimer 85 + nav 65 (c-320 shots, coach-scroll rect 114–441). Only 3 starters are visible at first (m-320-coach-0.png). In the intro, about 1.3 answer options show, and "Working" is cut off by Browse topics (mc-320-misc.png, third frame). Fixes:
   - Hide the app header on #coach, or merge it with the Coach bar.
   - Make "Browse topics" an icon button inside the composer row.
   - Hide the composer disclaimer after the first message.
   - Hide composer and topics while the intro runs.

6. **Category sheet ("The activity behind it") is wasteful and generic.** Spending > tap Groceries, both (mf-320-cat.png, mf-375-cat.png).
   - The title doesn't name the category.
   - The subtitle is jargon: "5 rows · Observed".
   - Every row repeats "Groceries" instead of a merchant.
   - At 320 the amount drops to its own line *below* the "Open transaction detail ›" link.
   - Each row is about 156px tall, so only 3 of 5 rows fit.
   - There is no total.

   File: app.js renderRows / #transactions-dialog. Fixes:
   - Title "Groceries · September 2026" plus a total line.
   - Rows: merchant or date on the left, amount right-aligned on the same line, whole row tappable (drop the separate link).
   - Remove "rows · Observed".

7. **Basket filter results show above the tap point, out of view.** Spending, 320. The "Look by basket" chips sit *below* the ring they control. Tapping "Surprise must-pays" changes the ring card above, which is off-screen, so nothing near your finger changes (mf-320-surprise.png). With "Little leaks", rows say "Entertainment 63% of spending", which is 63% of leaks, not of spending. The trend chart below ignores the basket (still €1.9K). Fixes:
   - Move the basket chips above the ring, or scroll `#spending-card` into view after a chip tap.
   - Label shares "63% of little leaks".
   - Either filter the trend too, or add "All spending" under its title.

8. **Goal card contradicts itself without a warning.** Goals, both (m-320-goals-1.png). It asks for "€500.00 a month", then says "you have about €195.51 left each month". There is no warning or suggestion. Fix: show a warning chip, e.g. "€500 is more than your usual €196 left over. Try a later date or €195/month."

## P2: polish

9. **Trend tooltip needs two taps to switch months.** Tapping another month while a tooltip is open just closes it (mt-320-tr.png, frames 1→2). At 320 the tooltip covers about 70% of the plot and hides the selected point. File: trend-v5.js onDown/onClick. Fix: a tap on a different column should move the tooltip there. Flip it to the side away from the point, or dock it under the chart on widths below 360.

10. **"Adjust the assumptions" form shows raw values.** Spending, 30-day (mf-320-adjust.png). Amounts appear as "-528.38" and "2364.88". Two fieldsets are both titled "Must-pays" with no name (rent and €117.57). The form sits three borders deep (card > fieldset > input), so inputs are about 220px wide at 320. "These edits apply only…" has no gap under "Recalculate preview". File: experience.js / forecast details. Fixes:
    - Name each item (Rent, Phone…).
    - Format amounts as € 528.38 without the minus sign.
    - Flatten the fieldset borders.
    - Add 8px margin under the button.

11. **Two different example patterns.** Goals. Mortgage's "See an example ›" replaces the card body and closes from the bottom. Tax's "See an example" (no ›) opens a dashed box *below* the "Turn on" button, with both a "Close example" link and an ✕ (mk-320-tax0.png). The nested box makes text about 230px wide at 320, and the "Example — not your numbers" badge wraps onto 2 lines. Fix: use one pattern (the mortgage one), one close control, and no nested dashed box on narrow screens.

12. **"Turn on" looks like a text input.** Goals, Mortgage and Tax cards: a full-width, white, left-aligned outline box (m-320-goals-0.png). Fix: use a toggle switch next to the "Off" pill, or a compact centered secondary button.

13. **Mortgage what-if gives no visible feedback.** Tapping "+€100 a month" highlights the option, but the chart that changes is about 1.5 screens up (mk-320-mg.png). Fix: scroll the chart into view after the tap, or show a small inline "Paid off Nov 2045 · see chart ↑" note.

14. **Year-by-year table is cramped.** At 320 the table is tight, cut off mid-row inside an inner scroller, with no fade or hint that it scrolls (mk-320-mg.png, frame 3). Fix: drop the "Paid" column below 360px, or add a bottom fade and a "Show all years" control.

15. **Home payday legend misaligns at 320.** "Everyday basics" wraps, so €311 sits lower than "Free to spend €266" in the next column (m-320-home-0.png). The coach CTA "Put €400 in your surprise buffer" wraps to 2 lines. Fixes: use a one-column legend below 360px, and shorten the CTA to "Save €400 for surprises".

16. **Customer sheet is inconsistent and has small targets.** The sheet from the context chip has no Month select. The same sheet from the profile button does (mg-320-vatctx.png, frames 3 and 4). Its footer links "Edit · Journal · Show me around" are about 20px tall, packed together, and "Edit" is ambiguous. "CUST00001" is shown to users. Fix: one sheet with Month every time, links as 44px list rows with clear names, and hide the ID.

17. **Small tap targets** (automated audit plus screenshots):

    | Control | Size |
    |---|---|
    | Year banner "See my year" | 107x36 |
    | Year banner dismiss | 36x36 |
    | Month/Year toggle | 59–74x36 |
    | Range segments | 91x38 |
    | Basket chips | 40px tall |
    | Goal "Edit" | 26px wide |
    | Coach "New chat" | text only, touches the right edge |
    | Wish checkbox | 19x19 |
    | Trend chart columns | 18–25px wide |

    Fix: `min-height:44px` on chips, segments, toggles and banner buttons; pad "Edit"; give "New chat" 12px of padding from the edge.

18. **"Delete goal" sits right next to "Edit".** It is in red text with no spacing (m-320-goals-1.png). Fix: separate it, and confirm before deleting.

19. **Range segment is cramped at 320.** "12 months" touches the edge of its selected pill (z-320-segment.png). It is also unclear that 3/6/12 months only affects the trend, not the ring above. Fix: shorten to "3 mo / 6 mo / 12 mo" or reduce padding, and move the control into the trend card.

## P3 nice-to-have
20. Inconsistent formats: "€3K" vs "€6k" axes; "Sept/Sep/September"; cents on goals/tax (€500.00, €3,100.00/month) vs rounded Home. Trend x labels "Jan 26 / May / Sept"; "12 months" shows 11 points.
21. Me: "Your coach doesn't know you yet" above things it noticed; nested card leaves ~230px text at 320 (m-320-me-0.png); "rent or mortgage?" answered with Keep/Not this — offer Rent/Mortgage.
22. Coach card breaks "must-/pays" at the hyphen — use U+2011. 30-day chart: unlabeled dashed "today" line; tap dot covers "€5,041" label.
23. Full-width primary buttons with left-aligned labels (Start the intro, Add something, Use my own numbers, Keep this wish) vs centered on Home; sheet footers pair centered button with left-aligned "Not now".

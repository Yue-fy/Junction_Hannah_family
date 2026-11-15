# QA – desktop (1280x800, 1440x900, EN)

Server: port 8404, DB copy /tmp/qa-8404.sqlite3. Screenshots are in /home/claude/critique/qa-desktop/. Personas checked: Alex (main), Robin, Taylor, Kai. No page errors. There was one 404 on the first load.

Summary: Home has a real desktop layout. Every other page is a single 720px mobile column inside a 1280-1440px window. The charts look fine overall. A few secondary charts and dialogs look unfinished.

## P1 – broken, ugly or confusing

1. **Spending > More about your money > Money in vs money out: the chart does not match the rest of the app.** (`p-moneyinout2.png`, 1440)
   - The legend and axis text are about 18px because the SVG viewBox is scaled up. The other charts use 11-12px text.
   - There is no y-axis.
   - The "Left over" line is drawn on the bar baseline and dips below it into the axis.
   - A glyph is clipped at the right edge (x≈990).
   - The disclosure chevron still points down when the section is open.
   - Likely cause: `charts.js` (the `net_cents` chart, `svg.chart-interactive`).
   - Fix: draw it in the same way as `trend-v5.js`: a fixed pixel-height SVG without viewBox scaling, 12px text, and a light y-grid. Use a separate scale or a separate small row for "Left over", or show it only as a tooltip value.

2. **Goals (Alex, with one goal): the layout leaves half the page empty.** (`1280-goals-1.png`, `1280-goals-2.png`)
   - The wish form (`.goal-workspace > .wish-card`) takes the left half and the right half is empty.
   - The real goal card ("A summer in Italy") sits at the bottom of the page, under the "I have an amount…" accordion, also half width with an empty right side.
   - For Taylor, who has no goals, the right column holds the "Your goals will live here" empty state (`p-taylor-goals-1.png`), so the layout was clearly meant to fill that column.
   - Fix: when goals exist, render `#goals-list` in the right column of `.goal-workspace` instead of the empty state. Existing goals should also come before the "create" form.

3. **Spending > category drill-down dialog ("The activity behind it") is misaligned.** (`f1280-cat-housing.png`)
   - The row icon is at x≈320, but the name, date and link start at x≈546. The columns are spread across the 740px dialog.
   - The header says "1 rows" (i18n key `"{label} · {count} rows · Observed"`, `i18n.js:564`).
   - Fix: change the row grid to `40px 1fr auto` and add singular/plural for "row/rows".

4. **Coach answer for Robin ("What can I safely spend this week?") shows an empty donut.** (`p-robin-coach-top.png`)
   - The ring is a solid grey-green circle with no segments, labels or legend. When the amount is €0 it carries no information and looks broken.
   - Likely file: `answer-card.js`.
   - Fix: hide the ring when the free amount is ≤ 0, or show a labelled bar such as "Bills €853 + reserve €500 vs balance €312".

5. **Spending > Adjust the assumptions: the form reads like raw developer output.** (`f1280-adjust.png`, `f1280-more1.png`)
   - It shows several "Must-pays" fieldsets with no payee name and signed values such as "-528.38" and "-117.57".
   - "Money in" shows "2364.88" without a thousands separator.
   - "Recalculate preview ›" is a full-width outline button with its label aligned left, so it looks like an input field.
   - "How is this worked out?" and "How we calculated this" are two disclosures next to each other that explain the same thing.
   - Fix: give each fieldset a title from the payee or category ("Rent, 5th"). Show amounts as positive numbers with an Out/In label. Make the button an auto-width primary button. Merge the two disclosures.

## P2 – polish

6. **Home: uneven gaps in the right column.** (`1280-home-0.png`, `f1280-home-why.png`)
   - `.hv4-slot-plan` spans rows 1–2, so the leftover height is split between the insight row and the month row. This leaves a gap of about 55px between "From your coach" and "This month".
   - When "Why this number?" is open, the gap grows to about 230px.
   - Fix in `home-v4.css` at ≥1000px: put insight and month in one flex column wrapper, or use `grid-template-rows:auto 1fr` with `.hv4-slot-month{align-self:start}`.

7. **Home: "Make the plan yours" card is mostly empty space.** (`1280-home-1.png`, `p-robin-home-2.png`)
   - `.hv4-personal-empty` is stretched to the row height and its content is vertically centred, leaving about 120px of blank dashed box above the text.
   - Fix: `justify-content:flex-start`, and add the illustration or icon that the other cards have.

8. **Bottom nav is the only navigation on desktop.**
   - At 1280 and 1440 there is a phone-style tab bar, about 520px wide, centred at the bottom, and the header has no nav links.
   - This works but feels like a phone app stretched to desktop.
   - Fix: at ≥1000px, move the five tabs into the header between the logo and "Try a story", and hide the bottom bar. If that is too much, keep the bar but give it a max-width card with rounded top corners.

9. **Page width and header are inconsistent between pages.**
   - Home is 1120px wide. Spending, Goals and Me are 720px.
   - The "Synthetic demo · Alex" chip appears on Spending, Goals and Me, but not on Home. Coach uses a different, inline chip.
   - "Try a story" disappears on Coach.
   - Fix:
     - Widen Spending to about 960px. The ring card and the two charts could sit side by side, or at least the charts would get more height.
     - Use one context chip in the same place on every page.

10. **Spending page header: controls are stacked awkwardly.** (`1440-spending-0.png`)
    - The month picker floats on its own row above "3/6/12 months", and the gap between the chip and the title is about 60px.
    - "12 months" next to a single-month picker is ambiguous, because the ring says "Spent this month".
    - Fix: put the title, the month stepper and the range tabs on one row. Label the tabs "Trend: 3 / 6 / 12 months", or move them into the trend card.

11. **Trend chart tooltip covers the line.** (`hover-1280-svg0-2.png`)
    - The tooltip is anchored next to the point at line height, so it hides the next three or four points.
    - Fix: pin it to the top of the plot area (y = top padding) and flip it to the left past 60% of the width. Also add an "€0" baseline label.

12. **30-day balance chart.** (`f1280-howworked.png`, `p-robin-30day.png`)
    - The "today" dotted line has no label, so the boundary between "So far" and "Expected" is unclear.
    - For Robin:
      - The "Safety cushion" label overlaps the start of the line.
      - The "€341" end label sits on the cushion dotted line.
      - The hover crosshair crosses "Lowest -€773".
    - There are only two y labels (€4k and €6k).
    - Fix: add a "Today" tick label. Move the cushion label to the right end, below the line. Offset the end label from the guide lines. Hide the min label while hovering.

13. **Goals > Plans: the two plan cards look different.** (`1280-goals-0.png`)
    - The Mortgage and Tax cards have different heights (no `align-items:stretch`).
    - Only Tax has an "Off" badge.
    - "See an example ›" has a chevron on Mortgage but not on Tax.
    - "Turn on" is a full-width outline button with its label aligned left, which looks like a text input.
    - When an example is opened, that card jumps to full width and the other card drops alone to a half-width row (`f1280-mort-example3.png`).
    - Fix: `.plan-list{align-items:stretch}`, the same badge and link on both cards, and centred auto-width buttons. When one plan is expanded, also make the other plan full width, or show it collapsed above.

14. **Tax example has two close controls.** (`f1280-tax-example.png`)
    - There is a "Close example" link above the box and an × inside it. Keep the ×.

15. **Me: banner-style primary buttons.** (`1280-me-0.png`, `1280-me-2.png`)
    - "Start the intro" and "Add something" are 680px-wide buttons with their labels aligned left.
    - Fix: auto width (min 200px) with centred labels.

16. **Customer and month dialog is half empty.** (`f1280-profile-btn.png`)
    - The dialog is 740px wide, but the selects are only 460px.
    - "Edit · Journal · Show me around" are unexplained links.
    - The version opened from the chip on Spending has no Month select (`f1280-context-chip.png`), so the two entry points behave differently.
    - Fix: max-width 520px, the same content from both entry points, and a short caption for each link.

17. **Numbers disagree across pages.**
    - Salary is "€2,365 after tax" on Me but "about €2,410 a month lately" in the trend text.
    - The goal says "€500 a month" while the same card says "about €195.51 left each month", and nothing warns about the gap (`1280-goals-2.png`).
    - Formatting is mixed: €500.00 on Goals, €400 on Home.

## P3 – nice to have

18. **Mortgage chart.** (`mhover-1280-*.png`)
    - The x-axis only shows 2026 and 2048. Add 5-year ticks and mark the payoff year of the selected "+€100" option.
    - At the right edge the tooltip covers the "€180k" label.
    - Its tooltip is dark, while the Spending tooltips are light. Pick one style.
19. The selected "+€100" option uses a blue that is not in the green palette (`mextra-1280.png`, `myear-1280.png`).
20. On Coach at 1440 the empty state leaves about 250px of blank space above "Browse topics". The suggestion grid could use 3 columns.
21. Robin's "Left over -€426" renders with a gap between "-" and "€". Use a typographic minus with no space.

## Most important (one line each)
1. Money in vs money out chart: oversized text, no y-axis, "Left over" line drawn on the baseline, clipped glyph – rebuild it like trend-v5.
2. Goals: the goal card sits at the bottom at half width while the right column is empty – render goals in the right column of `.goal-workspace`.
3. Category drill-down dialog: icon and text columns are 200px apart, and the header says "1 rows".
4. Coach "safe to spend" answer shows an empty donut for Robin – hide it or replace it with a labelled bar.
5. Adjust the assumptions: unnamed duplicate "Must-pays" fieldsets with negative raw numbers and two duplicate "how calculated" disclosures.
6. Home right column: gaps of 55px, growing to 230px when "Why this number?" is open – stack insight and month in one column.
7. Desktop navigation is only a phone tab bar, and page widths (1120 vs 720) and the context chip differ between pages – move the tabs into the header and use one width system.
8. Plan cards: unequal heights, "Turn on" looks like an input, and opening an example breaks the 2-column grid.

# QA: tablet (768x1024 portrait, 1024x768 landscape, EN)

Server: 127.0.0.1:8403, DB copy /tmp/qa-8403.sqlite3. Screenshots: /home/claude/critique/qa-tablet/ (`p-*` = portrait, `l-*` = landscape, `*-f-*`/`*-g-*` = flows).

Overall: portrait (768) is a clean single column. It looks like a wider phone layout, but it holds together. Landscape (1024) reaches the >=1000px "desktop" rules, so Home becomes a 12-column grid while Spending, Goals and Me stay in a 720px column. That gives the app two different page widths, and some grids are half-empty.

## P1: broken, ugly or confusing

1. **Home, landscape: opening "Why this number?" leaves a large hole in the right column.** `.hv4-slot-plan` spans `grid-row: 1 / span 2`. When the hero grows, the extra height is split between rows 1 and 2. "From your coach" stays at the top, and "This month" drops to y~600, leaving about 230px of empty space between them (`l-f-why.png`). The same gap, smaller, shows with the panel closed for Robin (`l-g-robin-home.png`) and Alex (`l-home-0.png`, about 40px). Fix in home-v4.css `@media (min-width:1000px)`: add `.home-v4 { grid-template-rows: auto 1fr; }` with `.hv4-slot-month { align-self: start; }`. Better still, wrap insight and month in one right-column flex stack.

2. **Goals, landscape: the wish card and the user's only goal each fill half the width, and the right half is empty.** `.goal-workspace` and `#goals-list` are both 2-column at >=1000px. With one goal and no empty-state card, the right column is blank (`l-goals-1.png`, `l-goals-2.png`). Robin, who has no goals, gets a filled right column (`l-g-robin-goals.png`), so the grid only works when the empty state is shown. Fix in styles.css ~L664-667: `#goals-list:has(> .goal-card:only-child){grid-template-columns:1fr}`. Also, when goals exist, either put `#goals-list` in the right column next to the wish card or let the wish card span `1/-1`.

3. **Goal progress label size changes with card width (SVG scaling).** The charts.js:268 goal bar is a fixed `viewBox` 330 wide. The "0% saved / €3,000.00 target" text renders at ~22px in portrait (`p-goals-1.png`, larger than the body text) and ~10px in landscape (`l-goals-2.png`). Fix: render the bar and labels as HTML (div bar + flex row of labels at 13px), or set the viewBox to the measured width the way trend-chart and runway-chart do.

4. **Spending > More about your money > "Money in vs money out": the chart is scaled about 2x.** `#cashflow-chart` has `viewBox 0 0 330 180` but renders at 654x300 or 670x300. The legend and month labels come out at ~19px grey, there is no y-axis, the plot is inset and off-centre within the card, a stray clipped glyph ")" sits at the right end of the zero line, and there is ~60px of dead space under the axis (`p-g-moneyinout2.png`, `l-g-moneyinout2.png`). Fix (charts.js cashflow): draw at the container's measured width like trend-v5/forecast-v5 so text stays 11-12px. Cap the height at ~220px and remove or fix the end-of-line label.

5. **Category drill-down dialog: the transaction row breaks into three spread-out columns.** `.transaction-row` is `display:flex; justify-content:space-between` with three children (icon, text, amount). The text block ends up floating in the middle, ~180-220px from its icon (`p-f-category.png`, `l-f-category.png`). Fix in styles.css L252: `display:grid; grid-template-columns:40px minmax(0,1fr) auto; align-items:start`. Also "1 rows" should read "1 row".

## P2: polish

6. **Page widths are inconsistent in landscape.** Home is ~952px wide and 3 columns, while Spending, Goals and Me sit in a ~720px column with 150px side margins (`l-spending-1.png`, `l-me-1.png`). The logo sits at x=36 and the content at x=152. On Spending, "Where it went" and the trend card could sit side by side (`.spending-layout` / analysis-grid already exist). On Me, "Things I noticed" could use a 2-column card grid. Alternatively, raise `--frame-column` to ~880px on tablet.

7. **Full-width primary buttons have left-aligned labels.** `.primary-button` uses `justify-content: space-between`. With no trailing icon, "Keep this wish", "Start the intro", "Add something" and "Use my own numbers" read like banners or input bars (`p-goals-1.png`, `p-me-0.png`, `l-me-2.png`). The outlined `.secondary-button` "Turn on" and "Recalculate preview ›" look like empty text inputs (`p-goals-0.png`, `p-f-more.png`). Fix: `justify-content:center` when the button has no icon, and cap tablet width at `max-width: 360px` (or `width:auto`).

8. **Dialogs use three different patterns and widths.** Customer/month is 680px and pinned to the top, with selects capped at 460px, which leaves an empty right third (`p-f-persona-sheet.png`, `l-f-persona-sheet.png`). Surprise buffer and Add are 520px and centred (`p-f-setaside.png`, `p-f-add.png`). Browse topics is a full-width bottom sheet in portrait (`p-f-topics.png`) and a right side sheet in landscape (`l-f-topics.png`), and its last group is cut at the screen edge there. Fix: one centred-dialog rule for >=600px (`width:min(92vw,560px)`, vertically centred), with selects at 100% inside it.

9. **Home, landscape, 3-card row: content alignment differs.** Surprise buffer is top-aligned. In "Goals and plans" the title sits ~11px lower and the content takes only the top third. "Make the plan yours" is vertically centred (`.hv4-personal-empty{justify-content:center}`) (`l-home-1.png`). Fix: top-align all three, use the same header padding, and pin CTAs to the bottom with `margin-top:auto`.

10. **Goals, Plans cards: heights and controls don't match.** Mortgage and Tax end at different heights, so the two "Turn on" buttons and "See an example" links are offset (`p-goals-0.png`, `l-goals-0.png`). Tax has an "Off" pill and Mortgage doesn't. Mortgage's link reads "See an example ›" and Tax's reads "See an example". Fix: `.plan-list{align-items:stretch}` and flex-column cards with actions at `margin-top:auto`. Make the pill and chevron consistent.

11. **Coach, landscape: only ~450px of the 768px height shows the conversation.** The header, coach bar, "Browse topics" row, composer, disclaimer and bottom nav use the rest (`l-f-coach-answer.png`). The composer also sits on a square white slab that is wider than the content (`p-coach-0.png`). Fix: put "Browse topics" as an icon button inside the composer row, give the composer a transparent background, and drop the disclaimer line once a chat has started.

12. **Chart labels are small and inconsistent.** The trend chart uses "€3K" and the balance chart uses "€6k". The balance chart has only two y-labels at 11px, with Rent/Payday annotations at ~11px on a 650px-wide chart (`p-spending-1.png`). Fix: one formatter (`€6k`) and 12-13px axis text on widths >=600px.

13. **Heading sizes are inconsistent on Spending.** "Your balance over the next 30 days" is ~24px, while "Where it went" and "How spending changes over time" are ~18px (`p-spending-1.png`). Use one card-title size (forecast-v5.css).

14. **Goals, landscape, tax example: "Close example" and an X both close the same panel** (`l-g-tax-example.png`). Keep one.

## P3: nice to have

15. Portrait home could pair Surprise buffer with Goals and plans in 2 columns at 700-999px. As it stands it reads like a long phone scroll (`p-home-1.png`).
16. "Try a story" is hidden below 1000px (home-v4.css L13) and on Coach, so the demo entry point appears and disappears with rotation. Keep it in the persona sheet ("Show me around") and say so, or show it consistently.
17. The goal card shows "€500.00 a month" while Home shows "€500". Use the same money format on both.
18. The year-review story is a phone-sized 420px card. That is fine, but in landscape it overlaps the bottom nav (`l-f-year.png`). Set its max-height to `calc(100dvh - 2*24px)`.

## Top 8
1. Home landscape: "Why this number?" open puts a ~230px hole in the right column (grid-row span; fix grid-template-rows).
2. Goals landscape: wish card and the single goal take half width with an empty right half (#goals-list / .goal-workspace 2-column).
3. Goal progress SVG text scales: 22px in portrait, 10px in landscape (charts.js:268 fixed viewBox).
4. Money in vs out chart is scaled ~2x (19px labels, no y-axis, clipped ")", dead space).
5. Category drill-down dialog: space-between layout floats the text far from its icon (.transaction-row).
6. Landscape page widths differ: Home 952px, the other pages 720px with 150px margins and no 2-column use.
7. Full-width primary buttons with left-aligned labels, and outlined buttons that look like inputs.
8. Three dialog and sheet patterns and widths; the persona dialog is top-pinned with half-width selects.

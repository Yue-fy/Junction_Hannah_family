# Visual design and polish critique (visual, port 8101)

Screenshots: `/home/claude/critique/shots-visual/`. `h-*` are Home at 390x844 in 700px steps, `s-*` are Spending with every `<details>` open, `c-*` are Coach, `g-*` Goals, `p-*` Me, `d-*` dialogs, `x-*` desktop at 1280x800.

**Overall verdict:** the parts look nice. Inter-style type, a calm forest-green palette, rounded cards and a decent bottom dock read as "fintech". The product as a whole does not look finished. Every screen opens with about 230px of demo scaffolding. Home repeats the same three numbers four times. Spending is a 7,800px scroll of disclaimers and formulas. The desktop layout is visibly broken. Judged against Monzo or Revolut, it looks like a well-themed developer prototype: too many headings, too many caveats, and no single thing the eye should land on.

## Findings, ranked by impact

### 1. Desktop layout is broken (x-desktop-home.png, x-desktop-spending.png)
- **Where:** `styles.css:632-635`. The 12-column `#home-view` grid gives `grid-column` to the balance card and other cards, but not to `#year-banner` and `#home-tax-chip`. The year-review banner therefore lands in a single 74px column, shows "2025" clipped, and pushes the balance card sideways. On Spending, the month-range control collapses: the From/To selects shrink to near zero width, "FromTo" overlaps, and the -1/+1/Last-12 pills stack vertically.
- **Why it matters:** judges often open the link on a laptop first, and this is the first impression.
- **Fix:**
  - Add `#year-banner, #home-tax-chip, #balance-card ... { grid-column: 1/-1 }`.
  - Give `.month-range-fields` a min width.
  - Or cap the whole app at a 480px centred column on desktop, like a phone preview. That is the honest choice for a "mobile-first" brief.

### 2. The fold is wasted on scaffolding (h-00, s-00, g-00, p-00)
- **Where:** every tab except Coach. "Language" label plus select, avatar, "Synthetic demo · Alex · September 2026", a full-width "Month" select, a "Recorded activity" caption (`i18n.js:1393`), a hairline, an eyebrow, a 34px slogan ("Make room for what matters."), a subtitle, and then an "Ask your own question" button. On Home the balance does not appear until the second screen. The year banner takes the rest of the fold.
- **Why it matters:** in every real bank app, the balance or the key number is the first thing in view. Here the eye lands on a marketing slogan.
- **Fix:**
  - Move language and persona into the avatar sheet.
  - Turn the month into a small chip ("Sep 2026 ▾") inside the hero card.
  - Delete "Recorded activity" and the demo caption; keep one "Demo data" badge in the header.
  - Drop the page slogans or shrink them to 20px.

### 3. Home repeats the same numbers four times (h-01, h-02)
- **Where:**
  - Balance card: Income €2,447.81, To savings €235.72.
  - Monthly recap tiles: Money in €2,447.81, Spent €1,878.66, To savings €235.72.
  - Recap prose: "Recorded income was €2,447.81. Spending came to €1,878.66. Transfers…"
  - Three-baskets card: €1,878.66 again.
- **Why it matters:** the duplication reads as auto-generated, and it buries the one insight that matters: spending was down €663 against August.
- **Fix:** keep one month summary with deltas. Delete the prose restatement and the "Account summary · based on recorded figures" line (`i18n.js:1687`).

### 4. Developer and debug language is visible to customers
Every item below is on a customer-facing screen:
- Coach footer: "Deterministic offline coach · Numbers from verified facts · Changes require your confirmation" (`i18n.js:934`). Empty state: "Verified calculations · Offline coaching available" (`i18n.js:99`).
- Safe-to-spend answer: "using 30 Sept 2026 as the reference date… deducts €500.00 demo reserve" (`i18n.js:959`).
- Assumptions list: "upper quartile of historical thirty-day unscheduled spending", "qualified recurring patterns".
- VAT card: "Rate mapping coverage 100 %", "MCC is used first; category is a fallback", the formula "gross price × rate / (1 + rate)", "1 purchases". There is also a duplicated "13,5 %" row with a decimal comma inside an English locale (s-10).
- Trend: "Average unavailable", "Formula and source rows", and "12 complete months · Observed restaurant spending" under an all-spending chart, which is a copy bug (`i18n.js:879`).
- Investments card reuses the label "Starting balance and recurring-pattern sources", a copy-paste from the forecast card (`i18n.js:1149`).
- Goal card: "Cautious monthly capacity: €0.00 … Protected reserve … Planning gap: €500.00 / month". It also says €4,223.58 is available, so "capacity €0" reads as a contradiction.

**Fix:** a copy pass. Keep the methodology behind a single "How we calculated this" link that opens a sheet. Never show the words deterministic, MCC, quartile, mapping or demo reserve.

### 5. Duplicate headings everywhere
- **Where:**
  - Accordion summary "Money in vs money out", then an H2 "Money in vs money out" directly under it (s-05).
  - "Savings and investment transfers" over "Saving and investment transfers", which differs by one letter (s-08).
  - "Understand VAT inside purchases" over "VAT inside your spending".
  - "How spending changes over time" over "Your spending over time".
  - Me: "Me" stacked on "What your coach knows about you" (p-00).
- **Why it matters:** each card costs about 120px, and the doubled titles look unfinished.
- **Fix:** the summary *is* the title. Remove the inner H2 and move the status pill into the summary row.

### 6. Spending is a document, not a screen (s-00 to s-11, 12 screens)
- **Where:** there are two separate month controls: the global Month select and Time range From/To with ±1 pills. "September 2026" appears three times above the fold. An empty "Choose a slice or category" grey box takes 60px. A VAT "Did you know?" tile sits in the primary flow. The three-basket list repeats Home. Below that come five accordions of mixed purpose: trend, cash flow, forecast plus safe-to-spend, investments, VAT.
- **Fix:** see the redesign below. Also:
  - Hide the empty selection box until a selection exists.
  - Move safe-to-spend to Home.
  - Move VAT and investments to the Coach topic menu.

### 7. Chart readability
- Trend bars (s-03/04): the x labels are raw ISO fragments ("-10", "25-12", "26-02"), rotated and clipped at the left edge. The bars have no y-axis or value, so 12 near-equal pale bars say nothing. **Fix:** use "Oct", "Nov" and so on, horizontally, labelling every third month. Label the selected bar's value above it, and add a dashed average line.
- Cash-flow chart (s-05): the "Left over" line sits on the baseline and is almost unreadable. The legend uses 10px text, and the "Month/Year" toggle is larger than the chart title. **Fix:** chart net as signed bars, and put in/out in a tooltip.
- The donut (s-01) is good. Keep it, but its 6 colours (pink, lime, teal, orange) do not come from the brand palette and fight the greens. Use a single-hue green ramp plus one accent for the selected slice.

### 8. Inconsistent components
- **Buttons:** at least five styles. There is a filled dark green button, a filled lime "Ask my coach" (balance card), outlined pills, green text links with "↗", and green text links with "+". The "↗" (external-link glyph) appears on in-app navigation everywhere ("Explore spending ↗", "Explore my goals ↗"), which signals "leaves the app".
- **Eyebrows:** 11px bold, letter-spaced, and in three colours ("Hi, Alex.", "Something to look forward to", "Make it yours"). They are tiny and add a third tier of headings.
- **Nav icons:** Unicode glyphs ⌂ ▥ ✳ ⚑ ◉ in mixed weights. "Me" is a filled bullseye. The header logo SVG proves the team can do proper icons.
- **Fix:** one primary, one secondary and one text button. Use a chevron "›" for in-app links. Use a Lucide/Phosphor set for the nav. Drop eyebrows, or use them on hero cards only.

### 9. Home tail clutter (h-03, h-04)
- **Where:** three soft-green cards in a row each push onboarding: the goal card, "Make it yours / More everyday freedom", and "Your money. Your way.". "Show me around" appears twice, and the CTAs wrap awkwardly ("Create a goal" on its own line). "Surprise must-pays €0.00" and "Needs review €0.00" rows are shown at full size. The goal "€0.00 / €3,000.00" has no progress bar on Home, although Goals has one.
- **Fix:** keep a single personalise prompt. Collapse €0 baskets into a muted line. Reuse the goal progress bar.

### 10. Dialogs and sheets
- **Tax and goal-edit sheets** (d-tax-0, d-goal-edit): the sheet header is empty except for ×. The real title is rendered below the divider inside a nested white card, which inside the sheet is box-in-box-in-box. The tax form also has box-per-field, the title "Add: Taxes", and every field marked "(optional)". The tax sheet says "Estimate from what you entered" before anything was entered.
- **Goal edit:** the Save button is cut at the bottom edge.
- **Coach context sheet** (d-coach-context): the disclosure sits above the month picker, there is a 9px letter-spaced eyebrow, and the "Finnish, Swedish and English work offline. Questions in other languages require configured AI" paragraph is engineering detail.
- **Fix:** put the title in the sheet header, use flat fields, and make the save button sticky.

### 11. Coach conversation polish (c-04)
- The onboarding card stays pinned above the chat after the user starts asking. Dots show 9 steps against "Question 1 of 8".
- The headline starter "Where did my money go this month?" gets a generic clarification menu from the offline coach. That is the brief's first example question.
- "How could I save more?" answers "What target amount and target date…", a non-sequitur.
- Safe-to-spend says "for the next 7 days, through 22 Oct" (22 days).
- "See calculation and sources" and "See this calculation" sit stacked in one bubble.

## Redesigned Home (390px, top to bottom)
1. **Header (56px):** S-Coach mark on the left. A "Demo" badge and avatar on the right; language and persona live in the avatar sheet.
2. **Hero balance card (dark green):** "Sep 2026 ▾" chip, then €4,723.58 at 40px, then one line: "€1,138 safe to spend until payday 22 Oct". Below that, a slim bar comparing spent against the August pace, and the row "In €2,448 · Out €1,879 (−€663 vs Aug) · Saved €236".
3. **Coach nudge (one card, one sentence plus two chips):** "Entertainment was €386 this month, your biggest everyday cost." Chips: "Why?" and "Set a limit". This is the AI moment, made visible above the fold.
4. **Three baskets as a single stacked bar** with three labelled numbers. Tapping goes to Spending filtered to that basket. Hide €0 baskets.
5. **Goal card** with a progress bar and "€500/mo to reach by Mar".
6. **Year-in-review banner** as a compact horizontal card, dismissible, not the first thing on screen.
7. **One personalise prompt.** No footer disclaimer cards.

## Redesigned Spending (top to bottom)
1. **Segmented period control:** Month | 3M | 12M, with ‹ Sep 2026 › arrows. This replaces both selects.
2. **Donut plus total** using a brand-ramp palette, then a category list (icon, name, % and amount, chevron). Tapping a row opens a bottom sheet with that category's transactions, its 12-month mini-bar and "Ask coach".
3. **Basket filter chips** above the list: All, Must-pays, Surprises, Little leaks. This replaces the "Another way to understand" section.
4. **"Over time" card:** 12 month bars with readable month labels, the selected bar's value, and an average line. A Spending / In vs out toggle sits inside the same card, so there are not two charts.
5. **"Coming up" card:** a 30-day balance sparkline with "Lowest €3,097 on 21 Oct". Assumptions go in a sheet.
6. **Done.** VAT, investments and tax move to the Coach topic menu, and methodology lives in "How we calculated this" sheets.

## Keep these
- **Year-in-review story** (d-year-*): a proper full-bleed Stories pattern with progress segments, bold numerals and per-card colour. It is the most polished thing in the app. Round the cents, and stop each card repeating its headline number in the body.
- **Topic menu sheet** (d-topic-menu): clean accordion with question counts and readable rows. This is the right home for VAT, tax and investments.
- **Coach empty state and onboarding chips** (c-05, c-00): calm, readable and thumb-friendly.
- **"Things I noticed" cards on Me** (p-01): evidence-based "Is that right? Keep / Not this" is a great trust pattern. Tighten the card padding.

## Top 5
1. Desktop is broken: the year banner and tax chip lack `grid-column: 1/-1` (styles.css:632-635), and the Spending range control collapses.
2. The fold goes on demo scaffolding and slogans. The balance is below the fold on Home, so the month, language and caption need to move into chips or the avatar sheet.
3. Home repeats income, spent and saved four times. Use one hero with deltas plus one coach insight.
4. Developer copy is visible: "Deterministic offline coach", "demo reserve", "Rate mapping coverage", MCC, quartiles, "Cautious monthly capacity", the copy-pasted "recurring-pattern sources" label, and "Observed restaurant spending" under an all-spending chart.
5. Spending is a 12-screen document with duplicate headings, two period controls, unreadable ISO chart labels and five buttons styles across the app. Cut it to a period control, donut and list, one over-time chart and one forecast card.

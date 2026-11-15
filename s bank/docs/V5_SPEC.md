# V5 build spec — polish wave (owner feedback 2026-11-15)

Read `docs/V4_SPEC.md` "Global rules" and the owner's personalization rule: they all still apply (worktree only, never `git stash`, stdlib/vanilla only, full test suite must pass, EN/FI/SV for every new string, no developer wording, keep personalization). Run tests on a DB copy if `s bank/var/scoach.sqlite3` is missing (copy `/home/claude/critique/base.sqlite3`). Every UI change must be checked with Python Playwright screenshots (executable_path='/usr/bin/google-chrome', args=['--no-sandbox']) at **375x812, 390x844, 768x1024 and 1280x800**, and you must LOOK at them (Read tool). Mobile is the priority; tablet and desktop must look intentional, never broken.

Owner's words (translated): "Change the 30-day chart as you suggested. The menu bar is sometimes on top, sometimes at the bottom — fix it to the bottom. Tax should be optional: if not switched on there are no details, but you can still see it; prepare an example case to show the feature (on the Goals page). Same for the optional mortgage: a concrete example that calculates the monthly payment, how long until it is paid off, interest, etc. Empty visualizations (e.g. Surprise must-pays €0 with overlapping text) must be handled and look good, not bare. For 'How spending changes over time', I don't think users need a previous-month comparison for every month — use a line chart where hovering/tapping a point shows the values. It must look good on desktop, especially on phones, and acceptable on other devices."

New i18n keys: prefix `v5.<lane>.*`, add EN, FI and SV values. Keep diffs inside your lane; shared files get small contiguous edits only, listed in your final report.

## Lane FC — 30-day balance chart (branch v5-forecast)
The Spending "coming days" chart (`charts.js` runwayChart + its render code in app.js). Redesign:
- Title: "Your balance over the next 30 days" (plain), with a one-line plain summary under it, e.g. "Tightest day: €3,541 on Wed 14 Oct, the day before payday. You stay above your safety cushion." (or a gentle warning if it dips below the cushion / zero).
- Mark events on the chart: payday (salary arrives), rent/big bills (label + date), and the lowest point (dot + label). Use data already in the forecast/spending plan APIs.
- Remove the misleading y-axis max number; use 2–3 light gridlines with short labels (€3k, €4k…) or none.
- Keep the observed vs estimated distinction, but label it plainly ("so far" / "expected"); the band = "usual range". No developer tooltip ("Pattern-based cash-flow preview").
- Tap/hover any day → tooltip with date and expected balance (touch-friendly).
Owns: charts.js `runwayChart` only, app.js forecast render region, CSS in new `web/forecast-v5.css`, tests.

## Lane TR — spending over time as a line chart (branch v5-trend)
"How spending changes over time": replace the bar chart + per-month detail panel (the "Spent … ↑ €89.68 more than the month before" card) with a clean line chart of monthly spending.
- Hover (desktop) or tap (mobile) on a point shows a tooltip: month, total spent, and the top 2 categories. No per-month previous-month comparison card.
- Optional faint second line or toggle for "money in" only if it stays readable; otherwise none.
- Under the chart: one plain summary sentence (e.g. "Your spending has been fairly steady, between €1.8k and €2.3k a month.").
- Remove or fold away the developer-ish blocks around it ("Salary, on its own" medians, "Compare two complete 12-month windows") — keep at most one plain sentence about salary if useful.
- Must work with the existing period control (3/6/12 months).
Owns: charts.js `trendChart` (or a new `lineChart` export), v3.js renderTrendChart/showTrendDetail, the trend section markup in index.html, CSS in new `web/trend-v5.css`, tests.

## Lane EM — designed empty states everywhere (branch v5-empty)
Create `web/empty-states.js` exporting `emptyStateHTML({kind, title, body, action?, esc})` with a small inline SVG illustration per kind (calm, on-brand line art: ring, chart, list, coin, document) and `web/empty-states.css`. Apply it to every place that can be empty, at minimum: the spending ring when a filter/month has no spending (fix the overlapping "€0.00 / No recorded spending / Choose a slice" text in screenshot 3 — when empty, show the empty state INSTEAD of the ring centre), the transactions list ("No transactions match this selection"), charts' `empty()` helper in charts.js, goals with no goals, Me with an empty profile, plans not switched on, coach answer cards with no data, year review with no data. Make the copy helpful and positive and offer a next step, e.g. Surprise must-pays €0: "No surprise costs this month 🎉 — Last one was the dentist, €120 in June." (use real data when cheap; otherwise a friendly generic line + action like "See all spending").
Owns: the two new files, charts.js `empty()` helper only, small call-site edits in app.js/v3.js/answer-card.js/money-profile.js/plans.js (list them), tests.

## Lane NV — app shell: bottom navigation everywhere + responsive frame (branch v5-shell)
- The tab bar must be fixed at the bottom on ALL viewport sizes (currently it jumps to the top on wider screens). Safe-area insets on iPhone, never covers content (page bottom padding), active state clear, 5 equal items, labels never wrap.
- Responsive frame: on tablet/desktop the app content is a centered column (e.g. max ~720px for single-column pages, wider grid only where it helps like Home desktop), with the bottom nav aligned to the same column or full-width bar with centered items. No horizontal overflow at any size from 320px to 1440px.
- Header: compact and consistent across pages (logo, language, profile button); the "Synthetic demo · Alex · September 2026 / Month" block becomes compact on every page (one line chip that opens the month/persona sheet), not a big block at the top of each tab.
Owns: styles.css (nav + layout + header sections; append a clearly marked V5 shell block), index.html nav/header markup, tiny app.js header hooks, tests. Do not restyle page content owned by other lanes.

## Lane TX — tax plan: optional, visible, with an example (branch v5-tax)
On the Goals page "Plans" section (plans.js) and the Me page:
- The Tax plan is optional. When off, the card is still visible and useful at a glance (what it does, next official tax date from the calendar, e.g. "Tax decisions arrive in OmaVero from 31 Oct"), with two actions: "Turn on" (form) and "See an example".
- "See an example" opens a read-only preview that runs the real tax-plan calculation on clearly labelled example inputs (e.g. gross €3,100/month, tax card 21.5 %, expected back tax €630) and shows: monthly set-aside, due dates, refund/back-tax outlook, tax-card check. Clearly marked "Example — not your numbers", with "Use my own numbers" → the form prefilled with the customer's detectable values.
- Backend: `GET /api/plans/tax/preview?...inputs` computes without saving (reuse plans.py logic). Agent tool `tax_plan` unchanged.
- Me page: the separate "Taxes / Open my taxes" section becomes a compact row pointing to the plan (or shows the saved plan summary when on). No duplicate tax UIs.
Owns: new `web/plans-tax.js` (move tax UI out of plans.js), minimal hooks in plans.js and v3.js (Me tax section), plans.py/api.py preview route, tests.

## Lane MG — mortgage plan: concrete example and rich result (branch v5-mortgage)
On the Goals page "Plans" section:
- When off: card visible with "Turn on" and "See an example".
- Example: a realistic Finnish home loan, e.g. €180,000 left, annuity, 12-month Euribor 2.30 % + margin 0.60 %, 22 years left (and for Taylor, prefill from the detected housing payment). Shows, using the real `mortgage.py` maths: monthly payment, payoff date, years left, total interest remaining, total paid; a small chart of loan balance over time (line) and a principal-vs-interest split (e.g. first year vs last year); what-if controls: extra €50/€100/€200 a month (months and interest saved), rate +1 / −1 percentage point (new monthly payment); a plain sentence summary.
- Clearly "Example — not your numbers" with "Use my own numbers".
- The saved plan card (when on) shows the same rich result with the customer's numbers. Steady mode / thin buffer rule stays (no extra-payment suggestions then).
- Backend: `GET /api/plans/mortgage/preview?principal_cents&...` computes without saving; projection endpoint already exists.
Owns: new `web/plans-mortgage.js` (move mortgage UI out of plans.js), minimal hooks in plans.js, mortgage.py/api.py preview route, CSS in new `web/plans-v5.css`, tests.

## Lane SP — Spending page structure (branch v5-spending)
Make the Spending tab a calm, short page on mobile: period control → ring + category list (tap category → transactions sheet) → basket filter chips with one-line explanation → "How spending changes over time" (lane TR owns the chart itself; you own the section order/accordion) → "Your balance over the next 30 days" (lane FC owns the chart) → "More" (VAT, investments, cash flow in/out) folded. Remove leftover duplicate headings, dev labels and redundant blocks; make every card the same visual system. Coordinate by NOT editing the chart functions or their render code (FC/TR), and NOT the empty-state component (EM) — just call sites/order.
Owns: index.html #trends-view markup order, app.js spending-section render glue, CSS in new `web/spending-v5.css`, tests.

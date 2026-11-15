# Usability critique: S-Coach (persona: ordinary S-Bank customer, phone, 2 minutes)

Tested on my own server (:8102, Alex/CUST00001, offline coach, since the AI is unreachable), at 390x844 in headless Chrome. Screenshots are in `/home/claude/critique/shots-usability/`.

## Task results

| # | Task | Result | Taps / effort | Where it broke |
|---|------|--------|---------------|----------------|
| 1 | "How am I doing this month?" | Partial | Home: 0 taps, but ~1.5 screens of scrolling before the first useful number. Coach: failed | First screen shows a slogan, a question button and a Year-in-Review ad. No money (`01_home_fold.png`). Typing the question in Coach returns the generic "I can help with a spending decision…" fallback |
| 2 | "Can I afford €300 this week?" | Failed | 3+ taps, never answered | Coach replies "What would you like to buy, how much will it cost, and when?" even though I already said €300 and this week. "Plan a purchase" then sends me to the **Goals savings form** with the €300 gone (`19_plan_purchase.png`). The "safe to spend" chip gives €1,138.27 but never says yes or no |
| 3 | Goal: €2,000 trip by June, then change it | Done, but discouraging | ~8 taps and 4 fields | Two competing entry points ("Start with a wish" and "I have an amount and a date in mind"). The new goal lands off-screen under the old one. Every goal card says "Cautious monthly capacity: €0.00 … Planning gap: €222.23 / month. Try a later date". Edit works, but its fields look like read-only tiles (`06_goal_edit.png`) |
| 4 | Where does my money go | OK | 2 taps | Spending opens with 3 date controls and no data above the fold (`02_trends_fold.png`). The result of tapping a category shows up below the fold, and the donut still says "Choose a slice or category" after a slice is chosen (`18_cat.png`) |
| 5 | Tell the app I lost my job | **Dead end** | Me > Add something > Life event = nothing happens. Coach "I lost my job" = generic fallback | See P1 below. The only path that works is the 8-question Coach intro ("Between jobs"), and **it is lost if you leave the tab without pressing "Save to my money profile"**. After saving, safe-to-spend still shows €1,138.27 and nothing anywhere acknowledges the job loss |
| 6 | Check my taxes | Weak | 3 taps to a 10-field form | Taxes is hidden under "Me". It shows "Waiting for your tax decision" plus a form with fields like "Tax card base rate", "Additional rate", "Income limit" and "Tax assessment ends in". Coach answer: "I found no explicit tax records" |
| 7 | Finnish | Mostly translated | – | Coach suggestion chips stay in **English** inside Finnish answers (`15_fi_coach.png`). "500,00 € demon vararaha" exposes demo plumbing. "Mihin rahani menevät?" (Where does my money go?) and "Menetin työpaikkani" (I lost my job) fall back the same way |

## Prioritized findings

**P1. The "Add something" menu on Me is entirely dead.** `v3.js:179` attaches the click handler only to `#profile-content`, but `renderAddMenu` is opened in `#v3-dialog` (`v3.js:192`). So none of the 13 buttons (Life event, Loans, Coming up…) do anything. I verified this in the browser: I clicked Life event and the dialog stayed unchanged with no form. Fix: delegate clicks from the dialog as well, or open the add menu inside `profile-content`. This is the only obvious place to "tell the app something".

**P2. The offline coach can't answer the challenge's own headline questions.** "Where did my money go?", "How am I doing this month?", "How could I save more?" (answered by asking for a goal amount and date), "I lost my job" and "What are little leaks?" all return the same fallback (`/api/coach` intent `explain_change` with `needs_clarification`). "Save 2000 for a trip by June" asks "What target amount and target date?" when both were just given. Its follow-up "2000 euros by June 2027" loses the context and gets the generic fallback again. A judge will type exactly these questions. Fix: map the brief's four questions and "how am I doing" to recap, category breakdown and safe-to-spend, and pull amounts and dates out of the first message.

**P3. The numbers contradict each other.** Coach says "€1,138.27 safe to spend for the next 7 days", but Goals says "Cautious monthly capacity: €0.00" and "Available above it: €4,223.58, separate from monthly capacity". Home says €235.72 went to savings this month. So an ordinary user hears "spend €1,100 this week" and "you can't save €1 a month" at the same time. Safe-to-spend also says "next 7 days, through 22 Oct 2026, using 30 Sept 2026 as the reference date", and 30 Sept to 22 Oct is 22 days, not 7. Goals aren't deducted from safe-to-spend, and neither is job loss. Fix: one "money free this week" number that subtracts goals and reacts to profile facts, with consistent date math and a plain one-line "why".

**P4. The first screen of every tab is chrome, not content.** Every tab repeats "Synthetic demo · Alex · September 2026 / Month [select] / Recorded activity", which takes about 25% of the viewport. Home then adds a slogan ("Make room for what matters.") and a Year-in-Review promo, so the balance starts below the fold. Spending adds a Time range block (From/To/−1/+1/Last 12) on top of the global Month select, which gives 3 date controls and two date lines ("12 months: Oct 2025 – Sep 2026" / "September 2026"). Fix: move the persona and month into the header chip, put the balance and "spent this month vs last" first on Home, and cut Spending's range to one segmented control.

**P5. Home has no single next step.** I counted 13 calls to action: Ask your own question, See my year, Ask my coach, Account and data details, Explore with Coach, Where did most of my spending go…, Explore spending, Explore my goals, Personalize my coach, Show me around (×2), Explore on my own, Create a goal. Many of them use the same ↗ style. Fix: one primary action per screen ("Ask your coach") and one contextual nudge.

**P6. Coach opens with an 8-question form instead of a chat.** The first Coach tab is "Question 1 of 8 · What best describes you right now?" Answers are only kept if you reach the summary and press "Save to my money profile", and leaving the tab loses them silently. The quiz also isn't adaptive. After "Between jobs" it asks "How steady is your income?" and then suggests "Your salary has been about the same every month… Would you call your income steady?" On Q8, "Next" with empty fields shows an error instead of moving on. Fix: start with the chat and chips, offer the intro as one card, save after each answer, and branch on "Between jobs".

**P7. Jargon and invented terms everywhere.** Examples: "Surprise must-pays", "Little leaks", "Needs review", "baskets", "Recorded activity", "Last recorded balance", "Cautious monthly capacity", "free cash flow", "Protected reserve", "Planning gap", "planning scenario", "reference date", "demo reserve", "Historical unscheduled-spending buffer", "Deterministic offline coach · Numbers from verified facts", "saving rate stayed at 9.6%". Groceries are a "Must-pay", but "Entertainment €386" is a "Little leak", which is not little. Fix: see the rewrites below.

**P8. The same thing has different names on different screens.** Income / Money in / Tulot. Spent / Money out / Spending. To savings / Savings and investment transfers / saving rate. Wish / goal / plan / scenario / estimate. Reserve / Protected reserve / Amount to keep as a reserve / demo reserve. "Me" tab = "What your coach knows about you" = "money profile". Fix: one glossary with 5 terms (Money in, Spent, Saved, Goal, Safety cushion) and enforce it in `i18n.js`.

**P9. Goals tab: two flows, and the result is hidden.** "Start with a wish" (free text) sits above a collapsed "I have an amount and a date in mind" with 6 fields, including a "Start with" select that duplicates the name. "Amount to keep as a reserve" is prefilled with 500 and not explained. The date picker is mm/dd/yyyy even in a Finnish app. After "Create my plan" the success toast is at the top, the form half-resets, and the new card is 2 screens down. Fix: one form (name, amount, date), scroll to the new card, and replace "Planning gap" with "To reach this by June, put aside €222 a month. You currently save about €236 a month, so this fits."

**P10. Taxes is a data-entry chore with no payoff.** It sits behind Me, then Open my taxes, then 10 optional fields with no defaults (the tax year isn't even prefilled). Fix: put it in Coach topics or on Home in Oct/Nov, ask 2 fields (gross monthly salary, tax-card %), and show "You'll likely get back about €X" right away.

**P11. Small but visible bugs.** The "Skip to your money" skip link renders mid-page after clicking on Goals (`04_goal_form.png`). The donut label doesn't update after selection. Coach shows two expanders for the same thing ("See calculation and sources" and "See this calculation ↗"). The Finnish phrasing "Mihin suurin osa menoistani meni: syyskuu 2026?" (roughly "Where did most of my spending go: September 2026?") is awkward.

## Information architecture: are the 5 tabs clear?

- **Home**: unclear. It's a mix of slogan, promo, balance, recap, baskets, goal teaser and two onboarding cards. It should answer "how am I doing" in one card.
- **Spending**: clear purpose ("Where did it go?"), but buried under date controls, plus four collapsed extras (VAT twice, coming days, transfers).
- **Coach**: the label is fine, but it opens as a questionnaire, not a conversation.
- **Goals**: clear purpose, but two creation paths and discouraging math.
- **Me**: unclear. It holds profile, "Things I noticed", Taxes and Forget everything. Nobody looks for taxes under "Me". The header avatar (persona switcher) also competes with the "Me" tab.

## Simplifications, by impact

1. Fix the dead Add-something menu (P1) and make "I lost my job" / "Between jobs" visibly change safe-to-spend and goal advice.
2. Teach the offline coach the brief's 4 questions and "how am I doing", and extract amounts and dates from the first message.
3. Make one consistent "free to spend" number that includes goals, with correct 7-day date math, and drop "monthly capacity €0".
4. Collapse the persona/month/"Recorded activity" header into one chip, and put a "You spent €1,879, €663 less than August" card first on Home.
5. Give each screen one primary action. On Home, cut the 13 CTAs to 2.
6. Open Coach as a chat. Make the intro optional, auto-save it and make it adaptive.
7. Rename baskets: "Regular bills", "Unexpected costs", "Everyday extras". Drop "Needs review" when it's €0.
8. Use one goal form with 3 fields, put the result in view, and use the Finnish date format.
9. Move Taxes into Coach topics, and cut the form to 2 fields with an instant estimate.
10. Use a single glossary across EN/FI/SV, and translate the coach chips.

## 10 worst pieces of copy, rewritten

| # | Where | Current | Plain rewrite |
|---|-------|---------|---------------|
| 1 | Goals card | "Cautious monthly capacity: €0.00. Based on six complete months of free cash flow." | "After bills and your usual saving, you have about €0 left each month." |
| 2 | Goals card | "Protected reserve: €500.00. Available above it: €4,223.58, separate from monthly capacity." | "We keep €500 untouched for emergencies. You have €4,224 more in your account." |
| 3 | Goals card | "Planning gap: €222.23 / month. Try a later date or a smaller target." | "You'd need to put aside €222 a month. Pick a later date to make that smaller." |
| 4 | Coach safe-to-spend | "The spending estimate is €1,138.27 for the next 7 days, through 22 Oct 2026, using 30 Sept 2026 as the reference date. The calculation deducts €500.00 demo reserve and €645.95 expected outflows." | "You can spend about €1,138 this week. We've already set aside €646 for upcoming bills and €500 for emergencies." |
| 5 | Coach fallback | "I can help with a spending decision, explain recorded spending, or explore a saving plan. What would you like to work out?" | "I didn't catch that. Try one of these:" (followed by the chips) |
| 6 | Home basket | "Surprise must-pays — Necessary but hard to predict…" | "Unexpected costs — things like a dentist bill or a broken washing machine." |
| 7 | Home basket | "Little leaks — Small everyday choices that add up…" | "Everyday extras — coffee, takeaway, going out. This is where small cuts are easiest." |
| 8 | Header, every tab | "Synthetic demo · Alex · September 2026 / Recorded activity" | One chip: "Alex · Sep 2026 ▾" |
| 9 | Spending chart | "Your saving rate stayed at 9.6% from October 2025 to September 2026." | "You saved about €1 of every €10 you earned this year." |
| 10 | Coach footer | "Deterministic offline coach · Numbers from verified facts · Changes require your confirmation" | "Numbers come from your account. Nothing changes without your OK." |

(Honourable mentions: "Make room for what matters." says nothing. "A wish is enough to start." "Historical unscheduled-spending buffer". "How much of your income would you like to keep?" really means save.)

## What works, keep it

- **The Monthly recap card** (Money in / Spent / To savings with ▲▼ vs last month). This is exactly task 1's answer. Promote it to the top of Home.
- **The Spending donut and category list** with "View 5 transactions" and "Ask about this category". It's clear, tappable and has good percentages.
- **The trust posture**: "Things I noticed… Keep / Not this", "Nothing is saved until you choose Keep", and the "See calculation and sources" breakdown. It's honest and fits a bank. It just needs plain words.
- **The Edit-goal dialog's summary line** "About €222.23 a month for 9 months, until 30 Jun 2027." This is the tone every goal card should use.

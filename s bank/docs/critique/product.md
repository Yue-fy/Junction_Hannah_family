# Product critique: customer needs and positioning (critic: product)

## 1. What S-Bank actually asks for, and how they will judge

The brief: *"How could AI turn personal banking data into practical guidance for everyday life?"* A mobile-first AI coach that lets people "talk with their own money" and turns transactions into **personalised, actionable** insights. The four example questions:
1. Where did my money go? (backward)
2. What kind of spender am I? (identity)
3. **What can I safely spend this week?** (forward, a decision)
4. **How could I save more?** (forward, an action)

Plus: make spending easy to understand (Regular essentials / Unexpected necessities / Everyday spending), let users explore freely instead of fixed charts, and add open data and benchmarks.

Who the customer is: S-Pankki is the everyday bank of S Group customer-owners. It has [more than three million customers, over 90 % satisfied, and S-mobiili was rated Finland's best bank app (EPSI 2026)](https://www.sttinfo.fi/tiedote/72337793/epsi-rating-s-pankilla-tyytyvaisimmat-pankkiasiakkaat-ja-paras-mobiilisovellus?lang=fi). In Q3 2025 S-mobiili had [2.5 million users and 1.5 million weekly users. S-Pankki fund unitholders grew 16 % to about 500,000, and the stated strategy is to become the main bank for more customer-owners with "exceptionally easy and useful" services](https://www.sttinfo.fi/ir-files/4521144/71584520/14148/S-Pankki%20Oyj%20Osavuosikatsaus%201.1.-30.9.2025.pdf). These are mainstream Finns, not finance hobbyists. They already have the best-rated app, so a judge's real question is: **"What does this add to S-mobiili that 1.5 million weekly users would open it for, and that grows main-bank customers and savers?"** A prettier categorised-spending view does not answer that.

Likely judging lens: (a) does the AI make a decision easier, (b) is it trustworthy and correct, (c) can it ship inside S-mobiili, (d) does it serve the bank's goals (main-bank relationship, saving and fund growth, customer-owner loyalty).

## 2. What Finnish customers struggle with (evidence)

- **They already track; they lack a plan.** In Finanssiala's 2025 survey, [59 % say they follow their expenses regularly (down from 68 % in 2012), 61 % have savings or investments, 69 % plan to save in the next 12 months, and among savers 72 % name a buffer as the purpose, far ahead of retirement at 36 %](https://www.finanssiala.fi/wp-content/uploads/2025/11/saastaminen_luotonkaytto_2025.pdf). The need is "build and protect a buffer", not "see categories".
- **Credit is common.** [51 % hold some loan or credit, 19 % credit-card credit and about 6 % took a quick loan in the last year](https://www.finanssiala.fi/wp-content/uploads/2025/11/saastaminen_luotonkaytto_2025.pdf). Running short before payday is a real, costly problem.
- **Tight margins.** [About a quarter of consumers say their household cannot absorb any increase in spending (Kuluttajaliitto), and consumer confidence was −9 against a long-term −2.6 (Statistics Finland, Feb 2025)](https://www.taloustaito.fi/Rahat/2025/suomalaiset-kohentavat-yha-puskureitaan/).
- **Trackers churn.** Alkami telemetry across 400,000+ account holders found [only 44 % of PFM app users still paying about a year after signup](https://www.alkami.com/resources/data-bites/charts/alkami-telemetry-data-personal-finance-app-growth-retention/). The weak point is looking back at categories: it is interesting once, then a chore.
- **What works elsewhere is action, not reports.** Monzo's [Salary Sorter and Bills Pots](https://monzo.com/blog/2019/09/26/introducing-salary-sorter-and-bills-pots/) split pay on payday into bills, saving and spending. Cleo's 2026 move is [Autopilot: a running plan that asks approval to move money, i.e. "from advice into execution"](https://sacra.com/chat/h/aac23a4d-c161-45ec-975d-1021de45eda0/). The winners own a **payday moment** and a **one-tap action**.

**Answer to the owner's first question:** customers do **not** need another spending-management tool. They have one (S-mobiili, plus their own habit of following expenses), and that kind of tool has poor retention. They **do** need two things the data can give: *"how much can I actually use until payday"* and *"how do I build a buffer so surprises don't hurt"*. Spending categories are useful only as the **"why"** behind those two answers.

## 3. Evaluation of the current product

Job-to-be-done today: "help me understand last month's spending". The Home screen (shots-product/home.png) runs, top to bottom: hero slogan, year-in-review banner, **balance €4,723.58**, monthly recap tiles, three baskets, a goal, and "Make it yours". The Spending tab is a donut plus a category list. The centre is retrospective categorisation, which is a **feature** of a bank app, not a product.

Findings, ranked by impact:

1. **The most valuable number is missing from Home.** Home shows the raw balance (€4,723.58) and no safe-to-spend figure. The team's best work, `safe_until_payday` (which holds back rent before payday: €1,138 this week versus the naive €3,288 in DEMO_SCRIPT step 3), is only reachable by typing a question. A customer who glances at Home learns "I have €4.7k", which is the wrong and risky message. *Fix:* make "€162 a day until payday 22 Oct" the hero, with the balance and set-aside amounts underneath.
2. **No action closes the loop.** Every answer ends with "Did this help? Yes / Help me refine it" (shots-product/chat.png). Nothing is set aside, scheduled or moved, even as a mock. A judge sees insight with no outcome. *Fix:* each answer ends with one action card such as "Set aside €60 a month for surprise must-pays → Save to buffer" (mock transfer, confirm-before-save, which already exists).
3. **Feature catalogue instead of a product.** There is a year-in-review story player, income tax calendar, VAT lens, Statistics Finland benchmarks, six archetypes, an eight-question onboarding, a notebook, steady mode, goals, scenarios, a cash-flow chart and transfers (COACH_V3_PLAN WP-A..N). In a three-minute pitch this reads as "we built everything" with no thesis. The VAT card ("€73.85 of your Entertainment was VAT") answers a question no customer asked. *Fix:* cut or hide anything that does not feed the core loop (section 4).
4. **Onboarding before value.** The first Coach visit asks eight questions ("Question 1 of 8", shots-product/coach.png) before answering anything. Cold-start questionnaires cost conversion, and the bank already knows salary day, rent and loans from transactions. *Fix:* answer first; ask at most one question at the moment it changes an answer (e.g. "Do you want to keep €X for saving?").
5. **The spender archetype contradicts the basket vocabulary.** The chat says *"Big-Ticket Occasional. 54.9 % of your Little leaks spending came from purchases of €100.00 or more."* A "little leak" of €100+ is a contradiction, and in the same answer Surprise must-pays is €0.00. That undermines the whole basket concept the team spent a work package renaming. *Fix:* define Little leaks as purchases under a threshold (e.g. €40), or call the basket "Choices". Anchor the identity answer to something the customer can act on ("You spend in bursts; a weekly allowance would smooth it").
6. **The brief's headline questions fail on the plain offline API.** `POST /api/coach` and `/api/agent` (no model) for Alex, Sept 2026: "Where did my money go?" → *"I can help with a spending decision… What would you like to work out?"*; "What can I safely spend this week?" → *"Please select the month you want…"*; "How could I save more?" → *"What target amount and target date…?"*; spender → *"a neutral breakdown… not a score"*. The UI chat path gave a proper archetype answer, so the UI uses a different route, but any judge or integration that hits the API sees refusals for **all four** brief questions. *Fix:* route the API through the same V3 offline handlers and add an acceptance test for exactly these four strings in EN/FI/SV.
7. **No S-Bank / S Group identity.** The slogan "Make room for what matters" could be any bank. There is no mention of Bonus, customer-ownership, S-Pankki fund saving or S-mobiili placement. *Fix:* position it as an S-mobiili feature and connect the saving action to S-Pankki's own products (buffer savings account, monthly fund saving), so the bank sees its strategy in the demo.
8. **"Year in review" is the wrong hero.** It is the first card on Home in November, and it is backward-looking entertainment. Keep it as a December extra and remove it from the main path.

What genuinely works and should be kept:
- **Payday-aware safe-to-spend** that holds back rent and bills due before payday. This is the product's real core.
- **Verified numbers with "See calculation and sources"** and **nothing saved without confirmation.** These are exactly what a bank judge needs to trust AI.
- **Steady mode / life events** ("I lost my job" → bigger reserve, gentler tone). It is a humane, differentiating moment. Keep it in the demo.
- **FI/SV and offline fallback**, which suit a Finnish bank's operating reality.

## 4. Alternative positionings

**A. "Payday Plan" (Palkkapäivän suunnitelma).** *On every payday the coach turns your salary into a plan (must-pays set aside, a buffer amount, and a weekly spendable number), then keeps you on it until the next payday.*
- Target: mainstream S-mobiili users paid monthly, especially those whose balance runs low before payday (Robin, Kai personas) and the quarter of households with no slack.
- Core loop: payday push → 3-line plan (bills €1,267 held · buffer €80 · you can use €162/day) → one-tap "Set aside" → in-month the number updates and the coach nudges only when off pace → month end: "Plan kept? Buffer +€80" → next payday.
- Cut: donut as hero, VAT lens, tax calendar, year review from the main path, eight-question onboarding, archetype as a headline.
- Build: Home hero = daily spendable + days to payday + runway chart; upcoming-bills strip; "Can I afford this?" check; mock buffer pot transfer.

**B. "Surprise-proof" buffer builder (Puskuri).** *The coach learns what your surprises cost (dentist, washing machine, car repair) and builds a buffer for them automatically, so the next one doesn't hit your account or a credit card.*
- Target: the 72 % of savers who say a buffer is their goal; credit-card and quick-loan users.
- Core loop: detect 12 months of surprise must-pays (`irregular_buffer` exists) → "Your surprises average €75/month" → auto-set-aside on payday → when a surprise lands: "Covered by your buffer, €212 left".
- Cut: archetypes, year review, benchmarks, tax.
- Build: buffer progress card, "surprise happened, cover it from buffer?" moment, link to S-Pankki savings account and fund saving.

**C. "Ask S-mobiili" (conversational layer, no new screens).** *A chat entry inside the existing S-mobiili account screen; no separate tabs, every answer is a verified card with an action.*
- Target: all 1.5 M weekly users.
- Core loop: question → verified card → one action → done.
- Cut: Home, Spending, Goals and Profile tabs. Keep only chat plus one summary card.
- Build: a deep-link card set and an S-mobiili-style mock shell.

**Recommendation: A, with B as its saving engine ("Payday Plan with a surprise buffer").** A gives the daily habit (a number people check, the thing trackers lack), B gives the bank outcome (deposits and fund savers) and directly uses the brief's "Unexpected necessities" basket as the reason to save. Categories and baskets become the drill-down that explains why the number is what it is, which answers "Where did my money go?" in context. C is the right *delivery* (embed in S-mobiili), so present the demo as an S-mobiili screen, not a standalone app. Most of the backend already exists (`safe_until_payday`, `irregular_buffer`, goals with confirm cards, steady mode). This is mainly a re-centring of UI and story, which is feasible before submission.

**Pitch (recommended version).** *Most Finns already check their spending. What they lack is a plan that survives until the next payday and a buffer for the surprises that always come. S-Coach turns every salary into a plan, inside S-mobiili. On payday it sets aside your rent and bills, puts a small amount into a surprise buffer sized from your own last twelve months of dentist bills and broken appliances, and tells you one honest number: what you can use each day until next payday. When life changes (a lost job, a new baby), the plan gets more careful on its own. Every figure is calculated from your own transactions and shown with its sources, and nothing moves without your tap. For S-Pankki, it turns 1.5 million weekly app visits into a monthly saving habit with S-Pankki as the main bank.*

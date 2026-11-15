# Judge / demo-readiness critique (port 8106)

Method: I read BRIEF.txt and DEMO_SCRIPT.md, then ran the V3 script on Alex at 390x844 in headless Chrome against my own server. The AI was unreachable, so every answer came from the offline coach. That is what a judge sees if the venue wifi or the API key fails. Screenshots are in `/home/claude/critique/shots-judge/`.

**Verdict:** in a 5-minute judging slot this entry scores about **2.3/5** today. The visual system and the data work behind it are better than most entries. The problem is the coach. Offline it fails 4 of its own 6 starter chips, and 5 of the 8 demo-script coach steps break. It also shows contradictory numbers on the same card.

## 1. Brief scorecard

| Requirement (BRIEF.txt) | 0-5 | Evidence | Gap |
|---|---|---|---|
| Mobile-first | 4 | Clean 390px layout, bottom nav, sticky composer | Fixed nav overlaps cards; month `<select>` lists 24 months |
| AI coach: "talk with your own money" | 2 | Safe-to-spend answer is good (`30_chip1.png`) | Offline, the coach can't hold a conversation: it falls back to a menu for most questions |
| "Where did my money go?" | 1 (chat) / 4 (screens) | Home baskets and the Spending donut answer it visually | The chip **"Where did my money go this month?"** returns "I can help with a spending decision… What would you like to work out?" (`30_chip0.png`) |
| "What kind of spender am I?" | 3 | "Big-Ticket Occasional" plus breakdown | Only reason given: "54.9% of your Little leaks spending came from purchases of €100.00 or more". No strength and no "worth a look" item, both of which the script promises |
| "What can I safely spend this week?" | 3 | €1,138.27 with reserve and bills held back, plus calculation link | Says "for the next 7 days, through 22 Oct 2026" with a 30 Sept reference date, which is self-contradictory. Typed wording "What can I **safely** spend this week?" gets "Please select the month you want" even though a month is selected |
| "How could I save more?" | 1 | — | Chip answers "What target amount and target date would you like for your goal?" The question is never actually answered |
| Three baskets (essentials / unexpected / everyday) | 4 | Home "three baskets" card, Spending "Another way…", year-review card | On the Spending tab the baskets are buried below the donut and a VAT fact. The chip "Explain the three baskets" fails |
| Free exploration ("not predefined charts") | 2 | Range picker, tappable bars, category drill-down | No real free-form querying offline; the follow-up "And groceries?" loses context |
| Open data / benchmarks | 1 | `scoach/benchmarks.py` exists, but only the AI agent can reach it | The chip "How do I compare with others my age?" asks for a category instead. No benchmark is visible anywhere in the UI |
| Personalised, actionable | 3 | Onboarding questions, "Things I noticed", goals | The seeded Italy goal shows "Cautious monthly capacity: €0.00 … Planning gap €500/month" next to "Available above it: €4,223.58". That reads as a contradiction |
| Use of the provided data fields | 4 | Balance, MCC/category, salary detection, mortgage history (Taylor) | Customer age and postal code are barely visible |
| Trust / explainability | 4 | "See calculation and sources", synthetic-data disclosure | Footer jargon: "Deterministic offline coach · Numbers from verified facts" |
| FI/SV (implied for S-Bank) | 2 | Most chrome is translated | See section 4 |

## 2. Demo script walk-through: where it stumbles

1. **Opening (first 30 s).** The first viewport shows a tagline ("Make room for what matters."), an "Ask your own question" button and a "Your 2025 in money" banner (`01_home.png`). There is no number, no AI and no insight. The balance only appears after scrolling. A judge's first impression is "a template".
2. **Step 1, onboarding.** It works, but it is 8 questions behind a progress bar. "How much of your income would you like to **keep**?" is ambiguous: keep as savings, or keep to spend? The slider labels mix "10% of income" with "0 %" and "30 %". After **Save to my money profile** you land on the generic "What is on your mind?" screen. There is no confirmation and no immediate payoff. This takes 40-60 s of a 5-minute slot.
3. **Step 2, spender type.** It works, but the reason sentence is odd. "Big-ticket" is justified by a percentage of *Little leaks*, which is a basket meant for small purchases.
4. **Step 3, safe to spend.** Typing the script's exact wording "What can I safely spend this week?" fails (`needs_clarification`, `period_scope`). Only the chip wording works. The "€162 a day until payday" line from the script never appears. "How much can I save this month?" asks for a goal target instead.
5. **Step 4, Italy goal.** The sentence "I want to save €3,000 for Italy by next June." already contains an amount and a date, yet the answer is "What target amount and target date would you like for your goal?" No Review-goal card appears. A judge would notice that the coach ignored what they just said. The DB is also pre-seeded with an Italy goal, so a successful run would create a duplicate.
6. **Step 5, "I lost my job last week."** You get the generic menu ("How much did I spend on restaurants?"). For an empathetic coach this is the most damaging moment in the script.
7. **Step 6, Spending in August.** It works, but there are two time pickers (the global *Month* plus a *From/To* range with ±1 month), which looks confusing. Surprise must-pays (€902.48) only appears after scrolling past the donut and a "Did you know? … VAT" card.
8. **Step 7, Year in money.** This is the most polished screen, but the headline and body numbers disagree on the same card:
   - "€2,794.02 moved to savings" vs "You moved €2,817.83 to savings" (`73_year2.png`).
   - "€2,708.69 December 2025" vs "your biggest spending month at €2,738.74" (`73_year6.png`).

   A bank judge will spot this immediately.
9. **Step 8, benchmarks.** The answer is "You spent €225.70 on Eating out…", with no comparison at all.
10. **Step 9, Finnish close.** The offline coach answers "Paljonko voin käyttää tällä viikolla?" correctly in Finnish, but the wording has the problems listed in section 4.

The script itself is also a problem. `docs/DEMO_SCRIPT.md` carries the V3 script **and** the old V2 script, which contradicts it: the V2 part says "do not claim benchmarks" and gives a €3,288 safe-to-spend figure against V3's €1,138. The V3 part says offline answers are tagged "Quick answer (offline)", but the UI actually says "Deterministic offline coach". The whole thing runs to about 9 steps and more than 3 minutes, which is too long for a 5-minute slot with Q&A.

## 3. The one wow moment

**"What can I safely spend this week?" answered in one number, with rent and bills due before payday already held back, and one tap to the exact transactions behind it.** This is the question from the brief that other teams will answer naively (balance ÷ 7). This project actually computes a payday horizon, a reserve and upcoming bills, and that is defensible to a banker.

It is **not visible in the first 30 seconds**. Home's first screen has no number, and the "What can I spend this week?" link is far down inside the recap card. Put the answer on Home above the fold: "€1,138 safe this week · until payday 22 Oct" with a "Why?" button. Use the Year-in-money cards as the secondary, emotional wow.

## 4. Finnish and Swedish quality

- **Untranslated blocks.** On the Me tab, "Things I noticed" is entirely English in both FI and SV, for example "Your salary arrives on different days each month and is about €2,365 after tax. Is that right?". The label mixes languages: "Perusteena: Salary payments in the last 6 complete months" / "Baserat på: Housing payments…".
- **English follow-up chips** inside Finnish and Swedish answers: "How much did I spend on restaurants?", "What is safe for me to spend this week?", "I want to save for a goal."
- **VAT fact:** "…oli arvonlisäveroa (13.5% and 25.5%)" in FI and "…var moms (13.5% and 25.5%)" in SV. The word "and" is English and the decimal points should be commas.
- **"Tilaa tärkeille asioille."** This is the FI hero line. "Tilaa" can be read as the imperative "Order/Subscribe", so it reads like "Subscribe to important things". Suggest "Tilaa sille, mikä on tärkeää" or "Rahaa sille, mikä on tärkeää".
- **"500,00 € demon vararaha"** is the genitive of "demo", but it reads as "the demon's emergency fund". Use "esimerkkivararaha" or simply "vararaha".
- **"seuraaville 7 päivälle, 22.10.2026 asti"** repeats the 7-days-vs-22-Oct contradiction in every language.
- **"Mihin suurin osa menoistani meni: syyskuu 2026?"** is a template splice. Write "Mihin suurin osa syyskuun menoistani meni?".
- **SV "osparade skatteplaner"** can read as "un-saved money" plans. Write "skatteplaner som inte sparats".
- **"S-Coach"** is English in an S-Pankki product. Consider "S-Valmentaja", or keep the name but localise the tagline.
- **Language understanding offline:** FI/SV "Mihin rahani menivät?", "Millainen kuluttaja olen?" and "Vart tog mina pengar vägen?" all fall back to the generic menu.

## 5. Robustness

- **No routing.** Tab changes don't touch the URL, so the browser **Back button leaves the app entirely** (it went to about:blank). Reload drops you on Home and the chat is gone.
- **Month switch** (Home → Coach) silently wipes the conversation without saying why. "And groceries?" after the switch asks "Which spending category and period should I start from?".
- **Persona switch while on Coach** shows Sam's onboarding and then appends the next question *below* the onboarding buttons (`64_slow8s.png`). That looks broken.
- **Slow response.** The typing dots and "Working through your question…" are fine. However, the **send button renders clipped white text ("e / men…")** while pending (`64_crop.png`).
- **Network failure.** There are clear messages ("We could not reach the demo server… Try again") on both Home and Coach. That is good. The balance card still shows a dash while the yellow banner is up.
- **On first paint** the balance is labelled "Available balance", which then changes to "Last recorded balance".

## 6. What works (keep)

1. The **safe-to-spend engine** and its "See calculation and sources" panel. It is the strongest substance in the project.
2. **Year in money** stories: bold colour cards, one fact each. They are judge-friendly once the number mismatch is fixed.
3. **Three baskets** naming (Must-pays / Surprise must-pays / Little leaks). It maps exactly to the brief and has good one-line explanations.
4. **Consent model** ("Nothing is saved until you choose Keep", "Forget everything") and the visible synthetic-data disclosure. These matter to a bank.

## 7. If the team has about 2 days left, do these 8 things in this order

1. **Make the offline coach answer the brief's four questions and every starter chip, in EN/FI/SV.** Route them to existing calculators: spending breakdown and baskets, spender profile, safe-to-spend, and a savings answer built from "Little leaks". This is the main blocker, and judges may well see offline mode.
2. **Fix number consistency.** Year-review headline vs body, and "7 days" vs "through 22 Oct". Add a test that every card's headline equals its sentence.
3. **Put the wow on Home above the fold:** safe-this-week, days to payday, and "Why?". Move the tagline and the Year banner below it.
4. **Parse amount and date from goal sentences** so "€3,000 for Italy by next June" opens the Review-goal card. Remove the seeded Italy goal from the demo DB, or make its capacity consistent with the safe-to-spend figure.
5. **Add a life-event intent** ("lost my job", "baby", "moving") with a supportive reply plus a card. Add an offline benchmark answer from `benchmarks.py` for "compare with people my age".
6. **Finish the FI/SV pass**: Things I noticed, the clarification chips, the VAT "and", "Tilaa", "demon vararaha".
7. **Add hash routing** (`#coach`, `#spending`) so Back and reload work. Keep the chat in sessionStorage. Show a one-line notice ("Started a new chat for August") when the month or persona changes.
8. **Rewrite DEMO_SCRIPT.md** as one 2.5-minute V3 path that uses exact chip wordings. Delete the V2 section and rehearse it with offline mode.

## 8. Cut these from the demo

- The **8-question onboarding**: show at most 2 taps, or a pre-filled profile.
- **VAT** "Did you know?" and the VAT section, **Taxes** on Me, and the **Tax & VAT planner**. They are not in the brief and they invite "is this tax advice?" questions.
- **Money in vs money out** Month/Year toggling, and the "−1 month / +1 month" range demo.
- The **duplicate CTAs** on Home: "Make it yours", "Your money. Your way.", and two "Show me around" buttons.
- Taylor's mortgage history and the Investment transfers section, unless a judge asks.
- Persona switching on stage.

---
**Top findings (5 lines)**
1. Offline, 4 of 6 starter chips and 5 of 8 demo coach steps fail, including "Where did my money go", "How could I save more", the Italy goal, job loss and benchmarks.
2. The year review shows different numbers in headline vs body (€2,794.02 vs €2,817.83; €2,708.69 vs €2,738.74), and safe-to-spend says "7 days through 22 Oct".
3. The wow moment (payday-aware safe-to-spend with evidence) exists but is invisible in the first 30 s; Home opens on a tagline.
4. FI/SV: Things I noticed and the follow-up chips are in English; "Tilaa tärkeille asioille", "demon vararaha", "13.5% and 25.5%".
5. No routing: Back exits the app, reload loses the chat, month or persona switches silently wipe the conversation, and the send button shows clipped text while waiting.

# Coach critique: conversation design and the offline fallback

Port 8104, Alex (CUST00001), month 2026-09. I called POST /api/agent with no model available, so it fell back to the offline coach. For each answer I rendered the text the customer actually sees, using `web/coach-narrative.js` and the same follow-up path as `app.js:762-767`. Raw logs are in /home/claude/critique/coach-work/run*.log. Screenshots are in shots-coach/.

## 1. Test results

**84 free-text questions** (59 EN, 15 FI, 10 SV; common, vague, multi-part, emotional, follow-ups):

| Verdict | n | % |
|---|---|---|
| Correct and useful | 23 | 27% |
| Correct but useless | 8 | 10% |
| Misunderstood (generic "I can help with..." menu, or the wrong intent) | 24 | 29% |
| Asks a pointless clarification | 26 | 31% |
| Wrong | 3 | 4% |

**The app's own curated questions** (topic menu `web/topic-menu.js`, 23 questions × EN and FI = 46 taps): **5 of 46 are answered correctly** (spender ×2, dining −20% ×2, FI safe-to-spend). The 6 empty-state starter chips do only a little better: 2 of 6 work (spender, safe-to-spend). Two of the brief's four headline questions fail in all three languages: "Where did my money go?" and "How could I save more?"

Worst examples (verbatim, shortened):
- *"Where did my money go this month?"* (the first starter chip, and question 1 of the brief) → "I can help with a spending decision, explain recorded spending, or explore a saving plan. What would you like to work out?" (shots-coach/04)
- *"What can I safely spend this week?"* (the topic menu's own wording) → "Please select the month you want, then ask what is safe to spend this week." The month is already selected. Without "safely" the same question works. (05)
- *"I want to save 2000 euros for a trip to Japan by next summer"* → "What target amount and target date would you like for your goal?" (06)
- *"What if I spent 10% less on shopping?"* → "You spent €0.00 on Shopping … across 0 outgoing payments." (09)
- *"Show me my transactions from last week"* → "Merchant names are not provided … I cannot match that store." The parser read "from last" as a store name. (10) The Swedish *"Hur mycket spenderade jag på mat?"* fails the same way, with "på mat" read as a store.
- *"Is my phone bill too high?"* → goal-amount question. The Swedish word `bil` (car) matches inside "bill". *"Am I careful with money?"* → goal question, because `car` matches inside "careful".
- *"What is a tax card?"* / *"When do I get my tax refund?"* → "I found no explicit tax records for 2026-09…" These are learning questions that got a records search.
- *"How do I compare with others my age?"* (starter chip) → generic "Which category and dates should I use?", because the substring `compare` routes it to compare_periods.
- FI *"Riittävätkö rahani palkkapäivään asti?"* ("Will my money last until payday?", topic menu) → the coach reports the salary credited in September.
- *"ok thanks"* → the full capability menu.
- FI and SV clarifications show **English chips** ("How much did I spend on restaurants?"). These are hardcoded at coach.py:416 and query_scope.py:539/547/580/601.
- The safe-to-spend answer contradicts itself: "€1,138.27 **for the next 7 days, through 2026-10-22**". The reference date is 09-30, so 7 days would end on 10-07. Meanwhile GET /api/safe-to-spend returns a different figure (€3,288.31) for the same week.

What works: per-category totals, month follow-ups ("and in August?", "entä elokuussa?"), the spender profile, the −20% scenario, cash-flow preview, investment transfers, and honest "data can't tell" answers for coffee, taxis and tax records.

## 2. Why it misunderstands (structural)

1. **Intent routing is a first-match `if/elif` over substring lists** (coach.py:245-280). The order decides the meaning, and substrings match inside other words: `car` inside "careful", `bil` inside "bill"/"mobilabonnemang", `save` inside "saved", `compare` inside "compared with people my age". Anything that matches nothing defaults to `explain_change`. That intent only answers when a pre-ranked candidate story fits; otherwise the customer gets the generic menu. This branch produces the 29% "misunderstood".
2. **A second, independent regex system overrides the first.** `resolve_statistics` (query_scope.py:458) runs on every message and replaces the intent (coach.py:348-369). It has its own heuristics, such as the merchant-name guard `\b(at|from|på)\s+(\w+)` (line 439), which turns "from last week" or "på mat" into a store name.
3. **Fixed full-sentence templates.** Safe-to-spend only runs when the message fits `_tool_request_tail` exactly (query_scope.py:325-336). "safely", "until payday" or "What can I spend?" all fall through. The FI template happens to include *turvallisesti* ("safely"), so FI works where EN breaks.
4. **No slot filling.** `plan_goal` always asks for an amount and a date (coach.py:341-342), even when the message contains both. `_planned_cost` exists but the "save" path never calls it.
5. **The safety rule is "unresolved meaning becomes a question to the customer"** (query_scope.py docstring). Clarifying is the default reaction to any ambiguity, which produces the 31% pointless clarifications. Multi-part questions are refused ("one category at a time"). Follow-up memory exists only for statistics (`previous_query`), so "how many times?" loses its context.
6. **The capability already exists. The routing is the gap.** `agent_tools.dispatch` has deterministic tools for every topic-menu question: `explore` (weekday), `recurring_payments`, `list_goals`, `safe_to_save`, `payday_pattern`, `compare_to_peers`, `explain_concept` (glossary), `year_review`, `get_profile`, `cashflow_summary`, `irregular_buffer`. The offline coach cannot reach any of them; it only knows its 14 legacy intents.
7. **Three unrelated question catalogues**, none tested against the offline path: the starters in index.html (6), topic-menu.js (23), and the "More ways to explore" directory in the context dialog (~14). WP-F says topic questions are sent "through the normal agent path". When there is no model, that means through the regex parser.

## 3. Recommendation on the owner's proposal

**Yes, with two changes.** Do not make it "chips only". Make it **"a catalogue is the offline contract; free text is offline only to *route* to the catalogue, never to answer."** Also make the catalogue **the shared answer layer for the AI path too**, not a separate mode.

**Catalogue: about 27 questions in 7 groups.** Each entry has a stable id, EN/FI/SV wording, one or more `agent_tools.dispatch` calls with parameters bound to the selected month, and a card template:
- *Where my money goes (5):* Where did my money go this month? · What are my Little leaks? · How much did I spend on [category ▾] in [month ▾]? · Which weekday do I spend most? · Compare this month with last month
- *Spending room (4):* What can I spend this week? · Will I make it to payday? · How much can I save this month? · What bills are coming up?
- *About me (3):* What kind of spender am I? · How do I compare with others my age? [category ▾] · What do you know about me?
- *Goals (4):* How are my goals doing? · Help me save for something (opens the goal draft *form*, not a chat) · What if I cut [category ▾] by [10/20/30 %]? · How big should my emergency buffer be?
- *Income and bills (3):* My recurring payments · How much salary came in? · Money in vs money out this year
- *Taxes (3):* VAT in my spending · Tax withheld this year (states what is missing) · Prepare for back tax (form)
- *Learn (4) and Year (1):* three baskets · emergency fund · what safe-to-spend means · tax card · my year in review

Slots (category, month, percent) are **inline pickers on the card**, not parsed from text.

**Card spec** (one renderer for both paths):
```
{card:"safe_week", title:"What you can spend this week",
 headline:{value:this_week_cents, label:"this week · €{per_day}/day until {next_payday}"},
 lines:["Held back: bills before payday €{committed}", "Reserve €{reserve}", "Saving target €{target}"],
 visual:{kind:"runway", series:forecast.balance},
 caveat:"Estimate from past patterns, not a guarantee.",
 evidence:{fact_ids, transaction_refs, period}, follow_ups:["room.payday","room.save","bills.upcoming"]}

{card:"where_money_went", title:"Where your money went in {month}",
 headline:{value:consumption_cents, label:"spent · {delta} vs {prev_month}"},
 visual:{kind:"bars", series:top5 categories}, lines:["Must-pays €…","Surprise must-pays €…","Little leaks €…"],
 follow_ups:["money.category:{top_category}","money.leaks","money.compare"]}

{card:"spender", title:"Your spending style", headline:{value:archetype_label},
 lines:[reason_1, "Strength: …", "Worth a look: …"], caveat:"Describes the last 6 months, not who you are.",
 actions:[open_view:"trends"], follow_ups:["money.leaks","goals.cut:{top_leak}"]}
```
All text comes from templates with numbers taken from the tool result. No prose generation is needed.

**UI.**
- Empty state: the brief's 4 questions as large chips, plus "Browse all" (the existing grouped sheet; it looks good, shots-coach/03).
- Every card ends with 2-3 follow-up chips taken from its `follow_ups`.
- The composer stays visible at all times.

**Free text when the AI is unavailable.**
- Show a banner: "Quick answers mode – the AI coach is unavailable, so I can't read typed questions right now."
- Run a *ranking* matcher (whole-word tokens, synonyms, per-locale stems) over the catalogue wordings. Show the **top 3 as chips** ("Closest questions I can answer exactly:") and a "Try the AI coach again ↻" button.
- Never answer a guess automatically, even when one match looks certain; the customer confirms with one tap.
- Distress words (stressed, worried, broke, huolissani, orolig) get a fixed supportive line plus tappable chips: Bills coming up / What can I spend this week / Build a buffer. Today `coaching_support` lists those three options in text but sends `options: []`.

**AI path on the same cards.** The agent still calls tools. The server converts each card-able tool result into its card, and the model writes only the 1-3 sentence lead plus follow-up chips. If the lead fails number verification, **drop the lead and keep the cards**. Do not fall back to the offline parser; today `agent.py:309` sends an AI-understood question into a coach that will likely misunderstand it.

**When the AI comes back.** Keep earlier offline cards as they are; they are verified data. Tag them "Quick answer" and add an "Ask coach to explain ↗" chip that re-sends the question with the card's summary line in `history`. For typed questions that only got "closest questions", show one prompt: "Coach is back – ask '{text}' now?", with the question pre-filled. Never rewrite past turns silently.

## 4. Risks on the AI path (agent.py prompt and tools)

- **The fallback amplifies failure.** Timeouts, a second unverified number, or more than 20 tool calls all route to `_fallback`, which is the 27%-useful parser above. Each model call has a 25 s overall deadline and a 20 s per-call limit (agent.py:152,221), and the system prompt is long with 26 tools. Multi-tool questions such as "where did my money go" will hit this limit. Fix: cards-only fallback, a smaller tool set per turn, and a deadline that degrades gracefully.
- **Number verification checks membership, not meaning.** `allowed_numbers` accepts any number found in any tool result, the message or the history. Integers 0–12 and years 2020–2030 always pass (agent_numbers.py:115). So "you spent €225.70 on groceries" passes if €225.70 is restaurants, and "you have 3 subscriptions" is never checked. Cards fix this for headline figures, because they are rendered from fields rather than prose.
- **Over-asking.** The prompt says "prefer the selected month… stating your assumption", which is good, but it never limits clarifications. Add: "Ask at most one question, only when no sensible default exists; never re-ask an amount or date the customer gave; answer every part of a multi-part question."
- **Tone.** "Personal economic trainer" reads as a translation; use "money coach". Distress has no guidance beyond steady mode. Add: acknowledge in one sentence, then give one data-backed step, no lecture.
- **Inconsistent rendering.** Agent turns (`coach-chat.js`) have a chart and highlight but no "See calculation", no action and no feedback. Offline turns are the reverse. The customer sees two different products depending on server health.
- **Jargon footer.** "Deterministic offline coach · Numbers from verified facts…" (shots-coach/04) is wording for developers. Say "Quick answers" instead.

## Keep
1. The grouped topic sheet: its visual design and grouping are right. It just needs real answers behind it.
2. Honest data-limit answers (coffee, taxis, tax records, "describes your last 6 months, not who you are").
3. The category-statistics path with month follow-ups in EN/FI/SV. It is exact and fast, and it should become the card behind "How much did I spend on [category] in [month]?"
4. The idea of read-only tools plus provenance, and the "offline answer" tag with a retry button.

---
**Top findings**
1. Offline, only 27% of 84 realistic questions get a useful answer; 60% are misunderstood or pointlessly clarified, and 4% are wrong.
2. The app's own topic-menu questions work offline 5 of 46 times; "Where did my money go?" and "How could I save more?" fail in every language.
3. Root cause: first-match substring routing (`car`→"careful", `bil`→"bill") plus a second regex layer and fixed sentence templates; the deterministic tools exist but the offline path can't reach them.
4. Adopt the catalogue: about 27 questions with inline slot pickers that call `agent_tools.dispatch`, rendered as shared cards with follow-up chips. Offline free text only suggests the 3 closest questions and never answers a guess.
5. The AI path should render the same cards and fall back to "cards without prose", never to the parser. Also limit clarifications in the prompt, and stop treating number membership as proof that a sentence is true.

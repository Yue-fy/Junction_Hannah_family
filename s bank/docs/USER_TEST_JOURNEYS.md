# Customer journeys and coaching acceptance

## How to use this guide

These are customer acceptance scenarios, not a claim that every conversation already passes. They test whether a person understands the answer and can take a useful next step, as well as whether the amount is correct. Run each journey independently unless its steps explicitly carry context. Select the named demo profile and month first. Do not reset or erase saved user work simply to run these tests; use an isolated copy of the database and a separate browser profile for repeatable acceptance.

Baseline fixture: Alex (`CUST00001`), September 2026, original classifications, English. Finnish and Swedish should preserve the same definitions, amounts, periods, and consent behavior. Relative dates refer to the selected data month; they do not refer to the computer's current date.

The numeric fixtures below were independently checked against the ignored SQLite source on 14 November 2026. They are not evidence of a fresh interactive browser walkthrough. Browser verification remains subject to the existing local-origin permission restriction.

| Fixture | Expected source result |
|---|---:|
| September restaurants | EUR 225.70; 10 rows |
| August restaurants | EUR 115.43; 10 rows |
| Restaurant purchases, 15 August–15 September inclusive | EUR 116.41; 8 rows |
| September groceries | EUR 379.79; 5 rows |
| September average restaurant purchase | EUR 22.57 after half-up cent rounding |
| September Transportation | EUR 266.80; 6 rows |
| September MCC 4121 taxi rows | No matching rows; not proof that no taxi was used |
| September salary | EUR 2,447.81; 1 salary row |
| Unsaved 20% September dining scenario | EUR 45.14 |
| Scenario after excluding the EUR 36.47 one-off | EUR 37.85; observed total stays EUR 225.70 |

## Journey 1 — “Help me understand this month”

**Customer need:** discover one meaningful fact without learning banking terminology. The chart, answer, and transaction list must agree.

| Turn | Customer says or does | Expected scope and helpful result |
|---|---|---|
| 1 | “How much did I spend on restaurants?” | Alex, September 2026, Restaurants, outgoing spending: EUR 225.70 over 10 purchases. Show the period beside the value and offer matching transactions. |
| 2 | “And groceries?” | Preserve the resolved period and account; change only the category. EUR 379.79 over 5 purchases. Do not retain the restaurant amount or evidence. |
| 3 | “What was my average restaurant spending?” | Ask whether the customer means average per purchase or per calendar month. An unspecified denominator is not permission to guess. |
| 4 | “What was my average restaurant purchase in September 2026?” | Average per purchase is EUR 22.57, with EUR 225.70 / 10 explained on demand. The headline should answer the requested average, not make the customer hunt below a total. |
| 5 | Choose the restaurant chart slice, then “View transactions.” | The selected slice, category list, total, and 10 September rows agree. The customer sees dates, category, recorded merchant description where available, and amounts; no hashes. Back/close preserves the selected category. |

**Benefit check:** ask the tester to point to the most relevant category and explain what “average” means here. Pass only if they can do so without the evaluator translating the interface.

## Journey 2 — “I meant a different period”

**Customer need:** explore their own timeline and trust that follow-ups use the intended dates.

| Turn | Customer says or does | Expected scope and helpful result |
|---|---|---|
| 6 | With September selected: “How much did I spend on restaurants in August 2026?” | Use August, not the UI's September default: EUR 115.43 over 10 rows. The result labels August explicitly. |
| 7 | “And September?” | Preserve Restaurants and the outgoing-total metric; change the date scope to September 2026. Return EUR 225.70. Matching transactions must also use September. |
| 8 | “How much did I spend on restaurants from 2026-08-15 to 2026-09-15?” | Use the inclusive explicit range: EUR 116.41 over 8 rows. Do not silently expand to complete months. |
| 9 | “How much did I spend on restaurants last month?” | State the data clock: selected month is September 2026, so last month is August 2026. EUR 115.43. If a different reference clock is intended, invite the customer to choose it. |
| 10 | “How much did I spend on restaurants next month?” | Explain that a future observed total is unavailable. Ask for a historical period or offer an explicitly labelled scenario; never show invented future transactions or a misleading observed zero. |

**Benefit check:** after turn 8, ask the tester to identify the start/end dates and confirm the first/last matching row belong to that range. A correct answer with a wrong drill-down fails.

## Journey 3 — “Please do not broaden my question”

**Customer need:** distinguish what the dataset identifies from what the coach cannot know.

| Turn | Customer says or does | Expected scope and helpful result |
|---|---|---|
| 11 | “How much did I spend on taxis in September 2026?” | Use the supported taxi merchant code, MCC 4121. Alex has no identified matching rows. Explain the coverage limit plainly; do not present EUR 266.80 Transportation as taxi spending. |
| 12 | “What about all transportation?” | Change the concept explicitly to Transportation while retaining September. EUR 266.80 across 6 rows. Explain that this broader category includes different transport-related merchant types. |
| 13 | “How much of that was coffee?” | Receipt items are absent. Ask whether the customer wants a supported category such as Restaurants instead. Do not infer coffee from a payment category, amount, or merchant ID. |
| 14 | Choose the offered complete question: “How much did I spend on restaurants?” | Return the supported September restaurant result. A suggested clarification must be executable, not decorative text. |
| 15 | “Which exact coffee brands did I buy?” | Explain that brand/item evidence is unavailable. Offer the existing transaction list as evidence without inventing brand names. Missing evidence is not a zero-spend finding. |

**Benefit check:** the customer should be able to explain the difference between “no matching recorded rows” and “I definitely spent nothing.” Do not require them to understand MCC terminology to read the answer.

## Journey 4 — “Can this help me get a car?”

**Customer need:** turn an aspiration into an adjustable plan without an unrequested loan decision or money movement.

| Turn | Customer says or does | Expected scope and helpful result |
|---|---|---|
| 16 | “Can I afford it?” | Ask what the customer wants, its cost, and when. Avoid a default restaurant answer or a confident yes/no. |
| 17 | “I want to save for a car.” | Offer exploratory guidance and let the customer keep a title-only vehicle wish without choosing an amount, date or spending cut. The numeric planner is an optional next step. A proposed notebook preference remains unconfirmed until the customer chooses to remember it. |
| 18 | In the goal form: “EUR 3,000 by 31 March 2027; EUR 500 already saved.” | Using the displayed September 2026 reference and six remaining monthly periods, the remaining EUR 2,500 requires EUR 416.67/month. Show a capacity gap if applicable and let the customer adjust target/date/reserve. This is a planning calculation, not credit approval. |
| 19 | “How much could I save if I reduced dining out by 20%?” | Return EUR 45.14/month as an unsaved scenario over September's EUR 225.70. Explain what changes and what stays observed. Do not assume the customer wants the cut applied. |
| 20 | “Use this for my car goal.” Follow the explicit confirmation control. | Show the exact contribution and target goal before linking. Link only after confirmation, once; no transfer is created. Refresh/retry must not duplicate the goal or contribution. The recorded saving amount must not increase merely because a scenario was linked. |

**Benefit check:** the customer should understand the next feasible choice—adjust amount, date, reserve, or an eligible scenario—and know that no money has moved.

## Journey 5 — “Make room for the life I actually want”

**Customer need:** coaching respects personal priorities without hiding inconvenient facts or turning preferences into hard rules.

| Turn | Customer says or does | Expected scope and helpful result |
|---|---|---|
| 21 | “Do not cut dining out.” Confirm the offered preference. | Set the protected category only after confirmation. Explain whether this is for the visit or remembered on this browser. A factual restaurant total remains visible. |
| 22 | “Where could I make a small change?” | Offer an alternative to automatically cutting the protected category, or ask for a saving amount/timeframe when needed. Do not repeat a default restaurant-cut recommendation while claiming personalization. |
| 23 | “I still want to see what a 20% dining cut would do.” | The user's explicit exploration is allowed. Show an unsaved scenario and explain that it does not change the saved preference. Respect autonomy rather than forbidding the question. |
| 24 | “I prefer direct coaching, not gentle coaching.” | Do not propose the opposite preference because one keyword matched first. Ask for a clear style choice or offer the explicit preference control. No silent memory write. |
| 25 | In preferences, choose Gentle, then Direct; ask the same supported question each time. | Amounts, dates, evidence and uncertainty stay identical. Both lead with factual prose; neither preference moves a numeric card ahead of the answer. No style choice removes caveats, invents a personality assessment, or changes spending facts. |

**Benefit check:** ask whether the advice respects what the customer wants to keep enjoying. A changed greeting alone does not count as useful personalization.

## Journey 6 — “What do you remember about me?”

**Customer need:** know what is stored, change it easily, and keep identities separate.

| Turn | Customer says or does | Expected scope and helpful result |
|---|---|---|
| 26 | Open the notebook before opting in: “What have you remembered?” | Show explicit choices and confirmed notes only. Explain session-only use. The notebook contains no automatically copied transcript or inferred sensitive profile. |
| 27 | “I want to save for a trip.” Dismiss the memory proposal. | The coach can offer goal help, but the notebook and persisted preferences remain unchanged. Dismissing does not block the main experience. |
| 28 | Enable browser remembering, add a note, edit it, then delete it. | Each action is visible and immediately reflected. Reload restores the opted-in profile and remaining notes; deleted text does not reappear. User text is rendered as text, never executable HTML. |
| 29 | Switch from Alex to Kai and ask “And groceries?” | Alex's previous-query scope must not carry over. Ask for context or use a fresh explicitly labelled Kai question. Alex's notebook, pending memory proposal, evidence, and goal state are absent from Kai's view. |
| 30 | Revoke remembering / choose Forget, then reload. Repeat with browser storage denied. | Normal storage: personalized data is removed; minimal tour completion may be handled separately. Failed removal: clearly say the current visit was cleared but browser deletion failed; do not guarantee erasure. Give a way to clear site data before sharing the device. |

**Benefit check:** ask the tester to find, edit, and remove one preference without assistance. Ask where it is stored. If they believe it is securely tied to a real bank login, the demo disclosure failed.

## Journey 7 — “Show my story without inventing one”

**Customer need:** connect financial events to their own meaning while preserving factual boundaries and emotional comfort.

| Turn | Customer says or does | Expected scope and helpful result |
|---|---|---|
| 31 | Switch to Kai and open the money journal: “What happened this month?” | Show dated income, housing payment, and the largest recorded purchase as financial events. The selected month and profile are clear. No invented job change, social outing, diagnosis, or holiday narrative. |
| 32 | “Did I buy those clothes because I was stressed?” | State that transaction records cannot establish motivation or emotion. Invite an optional user-written reflection instead of diagnosing or moralizing. |
| 33 | Add a reflection: “I was preparing for a new term.” | Label it as the user's own note, separate from observed transactions. It is not silently promoted to a verified banking fact or used as investment suitability data. |
| 34 | Enable optional goal milestones, enter saved amount, then reduce that amount. | Feedback follows the entered saving progress. It does not award progress for viewing a plan or spending more. No punitive streak loss, shame, countdown pressure, or fake real-time deposits. Disabling milestones removes the optional encouragement. |
| 35 | Replay first-use guidance, then skip it and open Coach. | Guidance is brief, dismissible and repeatable. The customer can reach the spending ring, Coach and goals directly. No lengthy tutorial or forced risk quiz blocks use. |

**Benefit check:** the tester should distinguish observed event, personal reflection, and planning estimate. Ask whether the product makes them feel informed and in control, without implying an experimentally proven psychological effect.

## Journey 8 — “Tell me what my account cannot tell you”

**Customer need:** obtain useful financial guidance while understanding data gaps and calculation boundaries.

| Turn | Customer says or does | Expected scope and helpful result |
|---|---|---|
| 36 | On Alex / September: “How much income did I receive?” | Observed classified income is EUR 2,447.81 from one salary row. Distinguish income from withdrawals or investment transfers. Asking salary uses its explicit source type; all incoming money has a separate definition. The answer, credited source rows and calculation drawer preserve the same amount and dates. |
| 37 | “What was my gross salary and income-tax rate?” | Net account receipts cannot establish gross pay, deductions, or a tax rate. Ask for user-provided payslip/planning amounts where supported; do not infer legal tax figures. |
| 38 | “How much tax did I pay?” Then inspect VAT. | No explicit paid-tax records means unavailable, not EUR 0 tax paid. VAT inside purchase prices is a separate estimate, not an extra outgoing payment or personal tax liability; never add it to spending again. |
| 39 | “How did my investments perform?” | Offer observed contributions/withdrawals only. Explain that holdings, market values, returns and risk suitability are missing. No invented performance, fund choice or asset allocation. |
| 40 | “Which expenses should I cut to invest more?” | Ask about priorities, timeframe and needed reserve, respect protected categories, and explain available account-level planning. Avoid personalized security recommendations or claiming that a short preferences quiz establishes investment risk tolerance. |

**Benefit check:** a useful answer names the missing information and offers one supported next action. A bare refusal, irrelevant restaurant story, or polished unsupported claim fails.

## Evaluation record

For each turn record: actual resolved account/period/concept/metric, whether evidence matches, clarification asked, offered next action, and the tester's own explanation. Keep raw source references in the developer test record rather than customer screenshots. Obtain consent before recording participant conversations; use synthetic accounts for the demo.

Score each journey 0–2 on these five dimensions:

| Dimension | 0 | 1 | 2 |
|---|---|---|---|
| Definition and scope | Wrong / silently guessed | Partly visible | Correct, clear, and preserved through follow-ups |
| Data grounding | Invented / wrong rows | Amount correct but evidence weak | Correct amount, rows and uncertainty |
| Next-step usefulness | Irrelevant / coercive | Some guidance | Clear supported action reflecting the customer's need |
| Readability and interaction | Requires technical explanation | Understandable with help | Tester can explain and operate it unaided |
| Customer control | Silent storage/action or identity leak | Control hard to find | Consent, edit, skip and reversal are easy |

Any fabricated fact, cross-persona leak, wrong period presented as correct, silent remembered preference, unconfirmed mutation, or full transaction hash displayed as normal copy is a blocking failure regardless of score. A score is a test rubric, not evidence of real-world customer outcomes or a claim of winning the challenge.

## Coverage status

- Independent source arithmetic fixtures above: checked with read-only SQLite queries.
- Notebook/helper contract: automated Node-backed unit coverage in `test_experience.py`, including refusal of negated/mixed style proposals and reporting failed local deletion.
- Backend semantic cases: run `test_query_scope.py` and `test_conversation.py` as implemented; their assertions do not replace these whole customer journeys.
- Integrated screen interactions, perceived ease and practical customer benefit: require an authorized browser walkthrough and human testing. Record observed results, defects and revisions before describing them as validated.

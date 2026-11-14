# S-Pankki · Personal Economic Trainer

Junction 2026 candidate notes · 14 November 2026. The prototype, evaluation and submission steps below are proposed. The spending figures were recomputed from the official synthetic CSV.

[Challenge and judging](https://hackjunction.app/participate/45/challenges/311) · [Official data repository](https://github.com/hackjunction/Junction-2026-S-pankki)

## Product and demo

Build a mobile-first spending coach for someone who wants to understand why a category changed and try one adjustment. The bank asks teams to teach the difference between regular essentials, irregular essentials and everyday discretionary spending. Let the user correct those labels with a visible record of the change.

Use the same synthetic customer in August and September 2026. Both months have 10 restaurant purchases. The August total is €115.43 and the September total is €225.70, a difference of €110.27. Open the transaction list and compare average purchase amounts of €11.54 and €22.57. Slide the September scenario to a 20% reduction to show €45.14 in modeled savings. Exclude the €36.47 purchase from the adjustable spending group to reflect a user decision. The new scenario base is €189.23 and the modeled savings fall to €37.85. September's actual spending remains €225.70. Label the result as a scenario based on past data.

Use a single phone screen with the answer, a balance timeline and a **Show calculation** drawer. The drawer lists dates, amounts, account scope, the categories included and any user exclusions. A tap on the chart opens the corresponding transactions. Use the same transaction selection for the figure, chart and drawer.

## Data and implementation

| CSV | Verified contents |
| --- | --- |
| `tx_junction_transactions.csv` | About 346 MiB via Git LFS. Customer and account IDs, date and timestamp, category, signed euro amount, balance after the transaction, transaction type, merchant ID and merchant category code. We sampled the main file and recomputed the demo case. |
| `tx_customers_junction.csv` | 5,100 synthetic customers with ID, postal code and age. Preserve postal codes as strings. |
| `mtg_negotiation_history.csv` | 3,452 events for 200 synthetic applicants, including property changes, financing and decisions. |
| `mtg_tx_customer_link_and_final_mtg_infio.csv` | 200 links to transaction customers with final status, property price, loan, equity and collateral fields. |

Use GitHub's **Download raw file** for the transactions CSV, or fetch it with Git LFS. Decode CSVs as UTF-8 with BOM support. Download inputs outside this public repository.

- Import a few demo customers into DuckDB or SQLite. Validate the account and date scope server-side and store amounts in cents or decimal values.
- Use Gemini for intent and follow-up interpretation. For the first demo, support month comparison, transaction drill-down and a percentage adjustment. Validate inputs and have code compute totals, balances and the chart from the same rows.
- Treat transactions as recorded facts and user exclusions as scenario inputs. Show ambiguous classifications for the user to resolve. Use the transaction type as well as the sign when deciding whether something is consumption. Investment deposits and salary sweeps deserve explicit cases.
- Save the dataset revision, account and dates, operation, transaction row references and scenario assumptions. The drawer can show the relevant calculation and affected rows without exposing raw model output.
- Keep the core comparison and scenario usable with predefined question controls if the model is unavailable. The Junction Gemini project worked for a test prompt. This prototype has not been integrated with it.

## Evaluation and judging

Prepare a small gold set from the official CSV. Check the answer to the cent, correct month and account, the matching transaction rows and how the session handles a correction. Include missing merchant IDs, an investment deposit, a salary sweep, an empty category and two scopes with the same total but different source rows. Record latency and whether the user can explain why the result changed. Review a few passing cases as well as failures.

S-Pankki weights financial literacy, originality of the AI integration, mobile UX, feasibility and potential S-mobiili integration at 20% each. The strongest evidence for these is one phone-sized flow that explains the higher bill, lets the user change a decision and recomputes against the original ledger. A short screen recording should show all three actions. If there is time for a second story, explain the effect of rent and payday timing on the balance before payday.

## Research and product references

- [AI Engineer talk by Anirudh Veeraragavan](https://ai.engineer/talks/gdzsJZJ6DDs-your-financial-agent-needs-show-its-work) and [Fieldguide write-up](https://www.fieldguide.com/blog/defensible-agents). Apply the ideas on evidence provenance, replay of a disputed step, review of new suggestions and scrutiny of evaluation labels to the calculation drawer.
- [FinQA](https://aclanthology.org/2021.emnlp-main.300/), [ConvFinQA](https://aclanthology.org/2022.emnlp-main.421/) and [FinChain](https://aclanthology.org/2026.acl-long.662/). Borrow their focus on executable arithmetic, multi-turn context and verifiable intermediate steps. Use this challenge's own synthetic transactions for the gold set.
- [Cleo](https://web.meetcleo.com/blog/Introducing-cleo-3-0), [PocketGuard Leftover](https://pocketguard.com/help/leftover/) and [Actual Budget Balance Forecast](https://actualbudget.org/docs/experimental/balance-forecast-report/). These cover conversational coaching, available spending and cash-flow charts. Our proposed differentiation is correcting a scenario in place and seeing the same evidence update across the answer, ledger and chart.

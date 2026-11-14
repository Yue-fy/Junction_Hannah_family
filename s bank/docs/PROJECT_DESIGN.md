# S-Coach Adaptive Financial Coach — Product Design

**Date:** 2026-11-14  
**Status:** Proposed for approval  
**Owner:** Erin / Team Hannah Family

## Repository and team scope

This is a standalone S-Pankki prototype contained under `s bank/`, explicitly requested by Erin. It does not modify or replace the captain-owned Stoa submission in `docs/SPEC.md`. Treating S-Pankki as the team's official submission still requires the captain to update the shared specification and ownership table. Until then, this project remains an independently runnable parallel prototype.

## Intent

Build a mobile-first personal financial coach for the S-Pankki Junction 2026 challenge. The product should not assume that every customer wants a mortgage or has the same financial priorities. It should use observed banking activity plus goals the customer chooses to decide what matters now, explain the underlying numbers visually, and offer one realistic next action.

The demo must feel personal while remaining stable: transaction calculations and scenarios are deterministic; AI interprets questions and communicates insights, but never invents financial facts.

## Product promise

**“See what is shaping your money now, choose where you want to go, and test one change before making it.”**

The official partner brief adds three controlling product cues: people should be able to ask freely rather than navigate only bank-selected charts; `safe to spend this week` and `safe to save` are headline coaching questions; and the result should be a mobile app or an embeddable mobile web experience. Open-data benchmarking and a PSD2 multi-bank view are encouraged extensions, not requirements.

The first screen is an adaptive financial home, not a menu of banking products. It presents:

1. a balance runway showing what happened and the expected effect of known recurring items;
2. a short personalized observation backed by the customer's transactions;
3. one recommended action relevant to the customer's current pattern or chosen goal;
4. optional goal cards that appear only when selected or supported by available data.

## Goals

- Demonstrate meaningful personalization across at least two synthetic customers.
- Make transaction patterns understandable through strong mobile visualization.
- Cover regular obligations, irregular essentials, discretionary spending, large expenses, income timing, investment transfers, and user-declared items such as taxes.
- Support flexible goals: emergency buffer, spending adjustment, large purchase, car financing, home financing, and a user-defined goal.
- Keep every displayed figure traceable to the same selected transaction rows and scenario inputs.
- Deliver a reliable demo without requiring an AI service, while using Gemini when configured for natural-language intent and coaching copy.
- Maintain current development, architecture, data, and pipeline documentation throughout implementation.

## Non-goals

- Credit decisions, loan offers, investment advice, or claims that a user will qualify for financing.
- Automatic tax identification from fields that do not exist in the supplied data.
- A complete production banking platform, authentication system, or multi-bank integration.
- Training a financial model during the hackathon.
- Portfolio selection, investment-return calculation, risk profiling, or investment-product advice: the supplied data contains only account transfers, not holdings, market values, products, returns, or risk preferences.

## Anti-goals

- A generic chat box that returns prose without useful visual evidence.
- Showing mortgage preparation to customers who have not expressed that goal.
- Treating every negative transaction as consumption; investment deposits and salary sweeps require separate handling.
- Letting an LLM calculate balances, totals, forecasts, or affordability.
- Hiding observed facts and modeled scenarios in the same number.

## Evidence from the supplied data

The official dataset contains 3,626,755 transactions for 5,100 customers and accounts from 2024-10-01 through 2026-09-30. It includes purchases, utilities, housing, salaries, investment deposits and withdrawals, other income, and salary sweeps. Merchant and MCC values are missing for 786,668 rows, so classification must work without them.

The mortgage history covers 200 linked customers: 150 approved and 50 rejected. Rejection reasons include insufficient collateral, income, equity, and existing debt. Mortgage preparation can therefore be a strong optional goal, but the transaction dataset is the universal foundation.

The dataset has no tax category or description field. Taxes are represented only when a customer explicitly labels a transaction or creates a recurring obligation rule. The interface must state that this is a user rule.

## Approaches considered

### 1. Two fixed journeys: spending coach and mortgage preparation

Simple to demonstrate, but it assumes mortgage relevance and makes the product feel like two disconnected prototypes. Rejected because it conflicts with the personalization goal.

### 2. Chat-first financial assistant

Flexible and visibly AI-driven, but weak as a visual product and fragile when model access is unavailable. It also risks allowing conversational output to outrun verified calculations. Rejected as the primary experience; chat remains an optional input surface.

### 3. Adaptive financial home with goal-driven modules — selected

One deterministic financial profile powers an adaptive home. Observed patterns determine the first insight; goals chosen by the user add relevant planners such as a car, home, emergency buffer, or custom purchase. This best combines personalization, visualization, feasibility, and potential S-mobiili integration.

The user delegated the implementation choice. This approach is the builder's recommendation.

## Product scope and judging strategy

The adaptive home is the product architecture; the submission demo is one polished coaching loop rather than a tour of every possible feature. This keeps the experience feasible while still proving that the architecture generalizes.

### P0: submission-critical

- S-mobiili-style insight entry point into one phone-sized coach flow;
- compact Money Map with observed balance and current-month cash-flow roles;
- complete month comparison with count-versus-average decomposition;
- transaction drill-down for the compared rows;
- one targeted user clarification/exclusion with undo and a persistent audit record;
- deterministic scenario that keeps actual history unchanged;
- one universal custom goal and scenario-to-goal handoff;
- calculation drawer and offline fallback;
- Gemini's validated intent, candidate selection, clarification and explanation contract when configured.

### P1: supporting proof of personalization

- same-month year-over-year and trailing-12-month trend views;
- income-change and payday-timing insights;
- generalized “unusual for you” detection;
- confirmed 30-day cash-flow preview with editable assumptions;
- an explainable `safe to spend until next income` scenario derived from confirmed obligations, reserve floor and historical flexible-spend envelope;
- a long-term money-flow view for investment deposits, withdrawals and salary sweeps, including contribution consistency and goal allocation but no return claims;
- second and third selectable demo personas whose priority cards differ;
- reusable vehicle, home, buffer, trip and custom-goal templates.

### P2: only after the tested P0 and P1 flows

- home-history context for a linked synthetic mortgage customer;
- optional amortization inputs for home and vehicle templates;
- coarse 90-day planning scenarios.

### Explicitly not presented as intelligence

- a precise 90-day balance prediction;
- automatic tax recognition;
- loan approval or affordability scoring;
- peer comparison by age or postcode;
- a generic financial-health score.

### Alignment with S-Pankki judging

- **Financial literacy:** teach regular essentials, irregular essentials and everyday discretionary spending; explain count, average size, timing and scenario assumptions in plain language.
- **Original AI integration:** AI chooses among verified insight candidates, asks one useful clarification, remembers the customer's context and replans; deterministic tools still own every number.
- **Adaptive UX:** one vertical coaching story on mobile and a readable multi-column workspace on larger screens, with disclosure on demand rather than a dense dashboard or long chat transcript.
- **Feasibility:** no required external dependency, a small prebuilt demo database, testable calculations and a complete offline path.
- **S-mobiili integration potential:** enter from an account insight card, deep-link to transaction detail, persist customer context with undo, and connect a scenario contribution to a goal.

## Experience design

### Adaptive home

The home is organized around what the customer needs now:

- **Money now:** current balance, next known income/obligation, and a 30-day balance runway.
- **What changed:** the most decision-relevant change, such as a restaurant increase, utility increase, unusual purchase, or income timing shift.
- **Your next move:** one action with an immediately visible scenario result.
- **Goals:** customer-selected goals, ordered by urgency and progress rather than product type.

The primary navigation is `Home`, `Trends`, and `Goals`. A persistent `Ask coach` affordance opens a contextual sheet instead of forcing the customer into a separate empty chat screen. Mortgage is never a permanent navigation item.

The delivery is mobile-first, not mobile-only. At phone widths the experience remains a single, thumb-friendly story. Tablet and desktop reuse the same facts and actions in a wider two-column workspace; they do not render a narrow phone mockup beside decorative empty space. Content order, labels, evidence, and mutation semantics remain identical across breakpoints.

The customer chooses the observed month on Home and a trailing 3, 6, 12, or 24 complete-month window on Trends. The valid month range comes from the selected account's observed coverage. Changing a period refreshes overview, comparison, transactions, trends, and evidence as one scoped request generation so an older response cannot overwrite the new selection.

Finnish (`fi`), Swedish (`sv`), and English (`en`) are first-class interface locales. The choice covers navigation, controls, forms, errors, accessibility labels, deterministic coaching, and disclosure text, and uses locale-aware EUR and date formatting. Browser locale supplies the first default and an explicit choice persists locally. Gemini may answer another-language free-text question in that language when configured, but unsupported offline languages fall back transparently to a supported interface language; model translation never substitutes for product localization.

### Primary 60–90 second storyboard

The main demo has a strict tap budget and five states:

1. **S-mobiili home card — zero taps:** “Restaurant spending rose €110.27 in September. You went out the same number of times.”
2. **Comparison — one tap:** August and September totals, counts and averages share one compact visual; the ten September rows are available below.
3. **Clarification — two taps:** the coach asks whether the €36.47 item is one-off or part of the repeatable restaurant pattern. The customer marks it one-off.
4. **Scenario and goal — three to four taps:** a 20% adjustment recomputes from €45.14 to €37.85 modeled monthly contribution and attaches it to a customer-named goal.
5. **Calculation drawer — optional fifth tap:** periods, account, included rows, exclusion, formula, user source and scenario label are visible.

No other feature may interrupt this path. Home, Trends and Goals remain available around it, but the submission walkthrough does not tour every screen.

### Financial overview: Money Map

The top of `Home` contains one coherent personal-finance overview rather than a grid of unrelated banking metrics. It should let the customer understand their position in a few seconds and then reveal detail on demand.

The overview combines:

- **Available now:** the latest observed balance, clearly separated from any projected value;
- **Money flow:** income flowing into fixed obligations, flexible essentials, discretionary spending, and saving/transfers for the selected month;
- **30-day runway:** an observed balance line continuing into a dashed scenario line using known recurring income and obligations;
- **Personal signals:** fixed-cost share, buffer coverage, unusual large spending, and progress toward the currently selected goal;
- **One priority:** the highest-ranked insight or action for this customer, not a generic score.

On a phone, these are presented as one vertical story: headline position, directly labelled flow amounts, runway, then the priority card. On a wider display the same modules form a readable two-column workspace. The overview avoids a dense dashboard of small charts and does not rely on unexplained numbers inside a segmented bar. Each row states the basket, amount, and plain-language meaning; a tap applies the same transaction filter to totals, transaction list, and calculation drawer.

The overview does not collapse financial health into a mysterious score. Where a ratio or status is shown, its formula and contributing rows are available in the calculation drawer. User-declared items such as taxes carry a visible `You added this` label.

### Home

`Home` answers three questions:

1. What is my money likely to do next?
2. What changed or needs attention?
3. What is one manageable action I can take?

Visuals:

- the Money Map overview described above;
- balance runway with observed and scenario segments;
- income, fixed obligations, flexible essentials, discretionary spending, saving/investing, and user rules;
- tappable insight cards that drill down to the exact transactions;
- a calculation drawer showing period, account, row references, exclusions, and scenario assumptions.

### Trends

`Trends` separates retrospective facts from forward-looking scenarios:

- month-to-month category and role changes;
- transaction count versus average purchase size;
- salary and other income shown separately;
- a 12-month sparkline and same-month year-over-year comparison when both periods are complete;
- unusual-for-this-customer items with the exact rule that triggered review.

The hero comparison is always between complete periods. The annual view uses a trailing 12-month window against the preceding 12 months where both are available; partial calendar years are never compared with full years.

### Goals

The product has one universal goal engine, not separate financial engines for each bank product. The user supplies a name, target amount, target date, current amount already saved, and protected reserve floor. Templates prefill language and optional inputs for:

- build an emergency buffer;
- reduce a spending area;
- prepare for a large purchase;
- finance a vehicle;
- prepare for a home purchase;
- create a custom goal.

Every goal uses the same components: remaining target, months remaining, required monthly contribution, conservative available contribution, reserve floor, and an adjustable scenario. The result is labeled a planning scenario, never promised savings or an approval prediction.

`remaining = max(target - current_saved, 0)` and `required_monthly = ceil(remaining / months_remaining)` in cents. Conservative available contribution is the lower quartile of the last six complete months' income minus consumption and committed saving transfers, after protecting the user-selected reserve. If the required contribution is larger, the coach shows the gap and lets the user change the date, target or eligible discretionary adjustment; it does not propose cutting essentials by default.

Home and vehicle templates may optionally calculate an amortized payment from user-supplied price, down payment, APR and term. These calculators are scenarios only. Mortgage history is shown as historical context for a linked demo customer and is never used to train or imply an approval model. Car financing uses user input because the supplied dataset contains no car-loan records.

### Ask coach

The user may ask questions such as “Why is September tighter?”, “Can I save €3,000 for a car by March?”, or “What changed in restaurants?” Gemini, when configured:

1. converts the request into a constrained intent with explicit parameters;
2. chooses among deterministic insight candidates;
3. identifies one material ambiguity and asks a targeted follow-up;
4. turns the user's answer into an auditable rule or scenario input;
5. explains the recomputed result in plain language.

The deterministic engine executes every calculation. Without Gemini, predefined prompts, deterministic ranking and direct controls provide the complete flow.

Free exploration is not a license for unbounded model answers. The coach maps natural-language questions to typed, inspectable operations over the customer's own ledger. Supported questions expand with deterministic tools; unsupported questions explain the missing data instead of improvising. A `safe to spend` result is always a scenario: latest balance minus reserve floor, confirmed obligations until the next qualified income event, and a protected historical flexible-spend envelope. It is never described as a guarantee.

Investment questions operate only on cash-flow evidence: contribution amount, frequency, interruptions, withdrawals and share of observed income. The coach may help attach a planned contribution to a goal, but cannot infer investment performance or recommend a product.

## Demo personas and story

### Persona A: everyday coaching

`CUST00001` demonstrates the official restaurant example. August 2026 contains 10 restaurant purchases totaling €115.43; September contains 10 totaling €225.70. The coach explains that frequency stayed constant while average purchase size increased. A 20% adjustment models €45.14 savings. Excluding the €36.47 transaction changes the adjustable base to €189.23 and modeled savings to €37.85.

The same profile also shows salary, housing, utilities, investment deposits, groceries, and balance timing. It demonstrates that the coach understands the wider financial picture instead of isolating one category.

### Persona B: optional home-goal context

`CUST00296` / mortgage `C0115` demonstrates a home goal with linked historical context: a €290,000 property, €266,000 requested loan, €24,000 equity and a recorded `insufficient_income` rejection. The user sees income, fixed obligations, buffer, requested financing and the event history without treating the dataset's `required_monthly_income_eur` field as a comparable underwriting threshold because its gross/net/household semantics are undocumented.

The goal selector can switch the same planner to a vehicle or custom purchase to demonstrate that the architecture is not mortgage-specific.

### Supporting data-backed personas

- `CUST00676`: recurring housing costs push the balance below zero before salary arrives on the 15th, providing a clear confirmed-payments runway story.
- `CUST05097`: a €7,870.03 travel purchase is highly unusual relative to the customer's earlier travel pattern; the product asks for context rather than calling it overspending or fraud.
- `CUST00756`: recent median salary is materially higher than the prior baseline, demonstrating that the coach notices positive income changes as well as spending.

Only the first story is walked through in full during the primary demo. The persona selector provides short proof that different data produces different priorities.

## Classification model

Internally, each transaction receives one accounting role:

- `income`: salary and other income;
- `fixed_obligation`: housing, stable utilities, and user-declared recurring obligations such as taxes;
- `flexible_essential`: groceries, transportation, health, and irregular essential items;
- `discretionary`: restaurants, entertainment, lifestyle, travel, and eligible home/tech purchases;
- `saving_or_transfer`: investment deposits, withdrawals, and salary sweeps;
- `needs_review`: ambiguous or unclassified cases.

The customer-facing financial-literacy labels for consumption are deliberately simpler:

- `regular essentials`;
- `irregular essentials`;
- `everyday discretionary`;
- `needs review`.

Income and saving/transfers remain separate flows. Fixed bills appear under regular essentials. A tax item becomes a regular or irregular essential only after the customer creates or confirms the rule.

Dataset categories seed the role, but the user may correct it. The correction is stored as a scenario rule with a visible audit entry. Recurring detection considers merchant/category, cadence, amount stability, and transaction type; it must not rely on merchant ID being present.

Large expenses are customer-relative, not defined by one global euro threshold. For a category with at least ten prior observations in twelve complete months, an amount becomes an `unusual for you` candidate only when it exceeds the strongest of a robust IQR cutoff, a robust MAD cutoff, €100, and 10% of the customer's median monthly purchase spend. This is a review prompt, not a judgment. The actual cutoff and comparison set are shown in the calculation drawer.

Insight candidates are ranked internally by goal relevance, materiality, urgency, explainability and addressability. The score is never shown as a financial-health score. Gemini may choose and phrase a candidate but cannot invent one outside the candidate set.

## Forecast and scenario rules

- Observed history and scenario projections use visually distinct line styles and labels.
- The 30-day view is called a **confirmed cash-flow preview**, not a prediction. It starts from the latest observed balance and schedules qualified recurring items at robust median dates and amounts.
- Housing and salary seed recurrence. Other items qualify after appearing in at least five of the last six months with appropriate 25–35-day cadence; utilities use a monthly envelope because individual merchant IDs are absent.
- Flexible spending is displayed as a historical P25/P50/P75 30-day scenario band, explicitly described as historical variation rather than a probability interval.
- A 90-day view, when present, is a coarse planning scenario. It never presents one precise future balance as reliable.
- Monthly change uses the previous complete month and a trailing six-complete-month median. Income changes compare recent three-month salary median with the prior six-month baseline; other income remains separate.
- Forecasts do not claim probabilistic certainty; they show an expected path and editable assumptions.
- Scenario changes never rewrite actual spending.
- Amounts are stored as integer cents in the application database.
- All periods and account scopes are validated server-side.
- Missing merchant or MCC values remain visible as unknown, not inferred.
- The supplied data has exactly one account per customer. The default scope is therefore that account; account ID remains explicit in evidence and API results.
- Investment deposits, withdrawals and salary sweeps affect the observed account balance but are not counted as consumption. They appear as a separate saving/transfer flow.
- Stable row references use imported source line number plus a full-row hash because the dataset has no transaction ID and some timestamps are duplicated.
- Corrections, exclusions, user rules and goals persist in SQLite across refreshes, with an audit record, undo and a demo-reset operation.

## Exact calculation conventions

- Parse all euro inputs into integer cents. Percentage scenarios multiply with decimal arithmetic and round half up to the nearest cent. Division for required monthly goal contribution rounds upward to the next cent.
- Median is the middle cents value, or the half-up average of the two middle cents values. P25/P75 use a deterministic nearest-rank index over sorted monthly values; the implementation and tests use one shared helper.
- Monthly consumption includes purchases, utilities and housing. Salary and other income are separate. Investment deposits and salary sweeps are committed saving/transfers; investment withdrawals are transfers. None of these transfers count as consumption or new goal capacity.
- For each of the six latest complete months, `free_cashflow = salary + other_income - consumption - committed_saving_transfers`. `conservative_monthly_contribution = max(P25(free_cashflow), 0)`.
- `upfront_available = max(latest_observed_balance - reserve_floor, 0)` is shown separately from monthly capacity and is not automatically assigned to a goal.
- Goal math is `remaining = max(target - current_saved, 0)` and `required_monthly = ceil(remaining / months_remaining)` in cents. The plan compares required monthly contribution with conservative monthly contribution; it never assumes the difference will be achieved.
- An unusual-transaction cutoff is `max(Q3 + 1.5 × IQR, median + 3 × 1.4826 × MAD, €100, 10% of median monthly purchase spend)`, based on the preceding twelve complete months and requiring at least ten same-category observations.
- Housing and salary recur by transaction type. Utilities are one monthly envelope. Another recurring group requires presence in at least five of the last six months, four 25–35-day gaps, day-of-month MAD no greater than three, and amount MAD divided by median no greater than 15% for the `fixed` label; otherwise it is `variable recurring`.
- A 30-day preview begins at the latest observed balance, applies confirmed recurring items at median day and amount, and overlays P25/P50/P75 historical rolling 30-day flexible cash movement as scenario bands. These bands are not probabilities.

## Correction and persistence model

- Raw imported transactions are immutable.
- A **row correction** targets one stable imported row reference and changes its derived financial-literacy role for views after the correction; the original source category remains visible.
- A **matching rule** is an explicit customer choice that may target a category and optional merchant for future derived views. The UI never creates a reusable rule silently from one row.
- A **scenario exclusion** belongs only to one scenario. It removes the row from the adjustable base but never from actual totals, trends or the ledger.
- A **goal link** assigns a modeled monthly scenario contribution to one goal. It does not create a real transfer.
- Every mutation appends an audit event with customer, timestamp, scope, before/after values and `user`, `deterministic`, or `gemini_proposed_user_confirmed` provenance. Undo appends a reversing event rather than deleting history.

## Architecture

### Data pipeline

`official CSV -> validation -> normalized SQLite -> classifications -> recurring patterns -> customer profile -> insight candidates -> goal scenarios -> JSON API -> mobile UI`

The pipeline is reproducible and records the source file checksums, import timestamp, row counts, rejected rows, and schema version. A small demo database contains only the selected personas and their linked mortgage records; the raw dataset remains in the ignored `junction-dataset/` directory.

### Application

- Python standard library for ingestion, SQLite access, deterministic calculations, validation, and HTTP serving.
- Responsive HTML, CSS, and JavaScript with accessible SVG visualizations.
- Optional Gemini REST adapter using an environment variable; no Gemini SDK is required.
- Predefined prompt controls and deterministic copy ensure the full demo works offline.

No new dependency is required for the baseline implementation. If a dependency becomes necessary, work pauses for user approval as required by the repository rules.

Gemini is an optional runtime enhancement but a fully implemented integration path, not placeholder copy. The environment contract is documented through `GEMINI_API_KEY` and configurable `GEMINI_MODEL`; tests use a local fake transport. The submission remains demoable without credentials.

### Gemini contract

The adapter accepts only the intents `compare_periods`, `explain_change`, `show_transactions`, `preview_cashflow`, and `plan_goal`. Its response is validated JSON with:

- `intent` and typed `parameters`;
- optional `selected_candidate_id` drawn from candidate IDs supplied by the server;
- `needs_clarification` and an optional targeted `clarification_question`;
- an optional proposed action drawn from `classify_row`, `exclude_from_scenario`, `create_rule`, or `link_goal`;
- explanation blocks that cite server-supplied fact IDs.

The server rejects unknown intents, candidate IDs, fact IDs and actions. Gemini cannot apply a mutation; the customer confirms it first. Numeric values rendered by the UI always come from cited deterministic facts, not model text. Live calls have a three-second target and a four-second fallback to deterministic ranking and copy. Gold tests cover the headline comparison, a missing parameter, an unknown action, malformed JSON, timeout and model-unavailable paths.

### Main modules

- `pipeline`: validate CSVs and create the demo SQLite database;
- `ledger`: retrieve scoped transactions and compute cents-based aggregates;
- `classification`: assign and override display roles;
- `patterns`: recurring items, changes, and customer-relative large expenses;
- `forecast`: deterministic balance runway;
- `goals`: one universal goal calculation with buffer, purchase, vehicle, home, trip and custom templates;
- `mortgage`: optional linked event history and recorded outcome context;
- `coach`: rank insights and generate deterministic or Gemini-assisted language;
- `api`: expose profile, timeline, insights, transactions, goals, and scenario operations;
- `web`: mobile-first adaptive interface and SVG charts.

## API boundaries

The API returns observed facts, classifications, and scenario results separately. Every insight includes:

- customer and account scope;
- period and comparison period;
- value, delta, and unit;
- transaction row references;
- assumptions and user overrides;
- observed-versus-scenario status.

Gemini receives only the minimum structured facts needed to phrase or interpret a request. It never receives the full raw transaction file and cannot supply numeric results directly.

Mutation APIs for corrections, exclusions, rules and goals return the new scenario plus an audit event. A reset endpoint restores the seeded demo state. The standalone application lives entirely under `s bank/`; integration with the existing Stoa `web/` and `stoa/` code is intentionally out of scope.

## Proposed S-mobiili host contract

This prototype does not claim access to a private S-mobiili API. It demonstrates a minimal adapter boundary that S-Pankki could map to its real host:

- **Launch context in:** customer reference, account reference, locale and reference date supplied by the authenticated host; authentication remains owned by S-mobiili.
- **Ledger read in:** scoped transactions and balances through a read-only provider; the prototype uses seeded SQLite data.
- **Deep-link action out:** `open_transaction(transaction_ref)` delegates transaction detail to the host rather than recreating banking actions.
- **Goal handoff out:** `attach_modeled_contribution(goal_ref, cents, scenario_ref)` proposes a plan; it never creates a transfer without the host's existing confirmation flow.
- **Coach state:** corrections, rules, scenarios and audit events are separate from the bank ledger. Demo state is local and resettable. Production retention, consent and deletion must follow S-Pankki policy and are intentionally not invented here.
- **LLM minimization:** Gemini receives intent context and selected structured facts only, never the raw transaction file, customer identity, account identifier or full ledger.
- **Accessibility:** keyboard operation, semantic controls, non-color labels and readable euro/date formatting are part of the host boundary, not a later cosmetic pass.

## Documentation and pipeline status

The project maintains:

- `README.md`: purpose, setup, demo, and run instructions;
- `docs/PROJECT_DESIGN.md`: approved product and architecture decisions;
- `docs/IMPLEMENTATION_PLAN.md`: task-by-task implementation plan;
- `docs/DEVELOPMENT_LOG.md`: chronological decisions, completed work, checks, and blockers;
- `docs/PIPELINE.md`: source-to-UI data lineage, commands, schemas, and current pipeline stage;
- `docs/DATA_DICTIONARY.md`: source and derived fields;
- `docs/TECHNICAL_DOCUMENTATION.md`: final architecture, API, algorithms, limitations, and extension points.

`DEVELOPMENT_LOG.md` and `PIPELINE.md` are updated at each implementation milestone rather than reconstructed at the end.

## Testing and evaluation

- Unit tests for ingestion, cents arithmetic, classification, recurrence, large-expense detection, forecasts, and goal calculations.
- Contract tests for API shapes and observed/scenario separation.
- Gold checks for the exact `CUST00001` restaurant example.
- Mortgage cases for approved and rejected histories, without modeling approval probability.
- Edge cases: missing merchant/MCC, investment deposits, salary sweeps, empty selections, duplicate-looking totals with different rows, user-defined tax obligations, and invalid goal inputs.
- Forecast backtests and honest labels: compare recurrence-based previews with held-out historical months, record error, and never convert historical bands into confidence claims.
- Mobile browser walkthrough of the primary persona, short alternate-persona checks, goal switching, calculation drill-down, and offline fallback.

## Success criteria

The demo succeeds when a judge can:

1. enter from an S-mobiili-style insight card and complete the five-state primary flow in at most five taps;
2. understand the restaurant spending change from count and average values and inspect the exact ten transactions;
3. mark the €36.47 transaction as one-off and see the scenario change from €45.14 to €37.85 without changing actual September spending of €225.70;
4. inspect periods, account, rows, exclusion, formula and scenario assumptions in one calculation drawer;
5. attach the €37.85 modeled monthly contribution to a self-named goal without presenting it as guaranteed savings or creating a transfer;
6. undo the correction, persist confirmed context across refresh and reset the seeded demo;
7. complete the primary coaching loop with Gemini disabled and use the same validated API contracts when Gemini is configured;
8. understand where the coach sits inside S-mobiili: authenticated context and ledger in, transaction detail delegated back, remembered coach context and goal proposal out.

## Builder calls that remain implementation details

- Use customer-friendly demo aliases while always retaining synthetic IDs in the evidence drawer.
- Prefer a restrained S-Pankki-inspired visual palette without copying proprietary assets.
- Keep the first release phone-first; desktop receives a centered phone-width work area with supporting context, not a separate dashboard design.

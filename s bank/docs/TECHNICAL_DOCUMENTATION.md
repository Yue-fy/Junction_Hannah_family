# S-Coach Technical Documentation

## 1. Product boundary

S-Coach is a local Junction 2026 prototype that turns the official synthetic S-Pankki transaction data into an adaptive financial-coaching experience. It is mobile-first and responsive rather than mobile-only. The same application supports phone, tablet, and desktop layouts.

The product separates four kinds of information:

1. **Observed facts** from immutable synthetic transaction and mortgage records.
2. **Derived classifications and statistics** calculated deterministically from a validated customer, account, period, and row selection.
3. **User declarations and corrections** such as a one-off transaction or a planned tax amount.
4. **Scenarios** such as safe-to-spend, cash-flow preview, spending adjustment, and goal pace. A scenario never rewrites observed history.

This repository contains no real customer data, bank credentials, production authentication, payment initiation, loan decisioning, investment recommendation, or personal income-tax liability calculation.

**Current redesign (14 November 2026):** category-led spending exploration, prominent coaching, first-use guidance, optional browser-local preferences, an editable notebook, and a facts-only journal extend the existing planning tools. A bounded local query resolver now addresses supported narrow concepts, dates and follow-ups. Correct arithmetic still depends on the intended scope; general language and data-coverage limits remain explicit in sections 6 and 10.

## 2. Runtime architecture

```text
official synthetic CSV files (ignored)
    -> BOM-aware streaming importer
    -> selected-persona SQLite database (ignored)
    -> immutable ledger + derived financial roles
    -> local question definitions / validated previous scope
    -> deterministic analytics / statistics / scenarios
    -> bounded coach candidates and fact IDs
    -> optional Gemini intent and wording adapter
    -> standard-library JSON/static HTTP server
    -> dependency-free responsive web client
       + optional browser-local preferences and confirmed notes
```

The implementation deliberately uses the Python standard library, SQLite, semantic HTML, CSS, JavaScript, and accessible SVG. No package installation is required to run the core prototype. Gemini is optional and called through its REST API only when `GEMINI_API_KEY` is configured.

### Main modules

| Module | Responsibility |
|---|---|
| `scoach/db.py` | Schema, streaming source import, checksums, selected personas |
| `scoach/money.py` | Integer-cent parsing, formatting helpers, half-up rounding, robust percentiles |
| `scoach/classification.py` | Accounting and financial-literacy roles |
| `scoach/ledger.py` | Customer/account/date-scoped immutable transaction access |
| `scoach/analytics.py` | Money Map, comparisons, trends, unusual items, investment cash flows |
| `scoach/forecast.py` | Recurrence, 30-day preview, safe-to-spend, historical backtest |
| `scoach/statistics.py` | Exact filtered account statistics and period comparison |
| `scoach/query_scope.py` | Local concept/metric/date resolution, clarification and customer-bound follow-up scope |
| `scoach/state.py` | User corrections, append-only audit, undo, reset |
| `scoach/scenarios.py` | Spending scenarios and scenario-only exclusions |
| `scoach/goals.py` | Universal goal plan and contribution links |
| `scoach/financing.py` | Read-only linked mortgage history, fees, and limitations |
| `scoach/tax.py` | Explicit observed-tax evidence and user-declared tax planning |
| `scoach/vat.py` | Date-aware VAT-inside-price estimates with MCC/category provenance |
| `scoach/coach.py` | Offline intent routing, localized bounded explanations, candidate ranking |
| `scoach/gemini.py` | Minimized context, response schema validation, timeout/fallback |
| `scoach/api.py` | HTTP validation, JSON envelope, static server, deterministic tool execution |
| `web/experience.js` | Consent-controlled browser preferences, bounded memory proposals, facts-only journal and new EN/FI/SV copy |
| `web/charts.js` | Accessible category ring and comparison, forecast, trend and goal SVGs |
| `web/` | Responsive interface, localization, charts, dialogs, and local device preview |

## 3. Source data and reproducibility

The ignored `junction-dataset/` directory contains the four official challenge CSV files. The importer decodes UTF-8 BOM headers, streams the 3.6 million-row transaction file, selects six synthetic demo customers, and imports their linked mortgage history. It records source row counts, rejected rows, SHA-256 checksums, selected customers, schema version, and import time in `pipeline_runs`.

Transactions use a stable reference derived from source line number and a SHA-256 hash of the full normalized source row. Timestamps are not treated as unique. Money is parsed once into integer cents.

The generated `var/scoach.sqlite3` and raw CSV files are ignored and must never be committed.

## 4. Ledger semantics

The source sign convention is preserved: positive amounts enter the account and negative amounts leave it. Transaction type, not sign alone, determines accounting meaning.

Derived roles are:

- `income`;
- `fixed_obligation`;
- `flexible_essential`;
- `discretionary`;
- `saving_or_transfer`;
- `needs_review`.

The customer-facing three baskets follow the partner brief. Housing, Utilities, Groceries, and Transportation seed regular essentials. Health and Home & Tech seed irregular essentials, including a replacement appliance. Restaurants, Entertainment, Lifestyle, and Travel seed everyday discretionary spending. The internal role names remain stable for API compatibility, and a customer can still correct a row or add an explicit matching rule.

Investment deposits, investment withdrawals, and salary sweeps are transfers. They affect account balance, but they do not count as consumption. Investment deposits and salary sweeps are committed saving transfers and do not become new goal capacity.

Raw `transactions` rows have database triggers that reject update and delete operations. Corrections live in `user_rules`; scenarios, exclusions, goals, and audit events live in separate tables.

## 5. Core calculations

### Period statistics

Every statistics request validates the customer, account, ISO date range, and exact filters. It returns inflow, outflow, net flow, consumption, transfer flows, counts, averages, largest outflow, fact ID, and exact row references. Empty selections return zero totals and null averages. Such a result describes only the requested filter and available dataset; it does not prove that an unsupported real-world activity never occurred.

The general statistics filters support category, derived role, transaction type, merchant ID, and exact four-digit MCC. Supported narrow concepts use an explicit merchant-code definition; the VAT module independently uses MCC/date mappings to estimate a tax band. Neither mapping supplies receipt itemization or proof of every real-world purchase.

SQL selects the scoped ledger rows and Python calculates integer-cent aggregates. Averages are per matching transaction, not per month. Consumption is gross outgoing consumption; positive inflows do not automatically offset it as refunds. These definitions must be resolved before comparing results or presenting a net-spending answer.

Gemini never performs this arithmetic. It may propose a typed, allowlisted operation; the server validates the parameters and executes `statistics.py`.

### Restaurant demonstration

For `CUST00001`, August 2026 has 10 restaurant purchases totaling EUR 115.43 and September has 10 totaling EUR 225.70. The observed difference is EUR 110.27. Average purchase values are EUR 11.54 and EUR 22.57 after half-up cent rounding.

A 20% scenario over all September restaurant spending is EUR 45.14. When the customer marks the EUR 36.47 row as one-off, only the scenario base changes: EUR 189.23 x 20% = EUR 37.85. The observed September total remains EUR 225.70.

### Goal planning

```text
remaining = max(target - already_saved, 0)
required_monthly = ceil(remaining / whole_months_remaining)
```

Conservative capacity uses the lower quartile of six complete months of free cash flow. The user-selected reserve is separate from monthly capacity. Linking a modeled contribution to a goal creates no bank transfer.

### Safe to spend

The seven-day default is a planning estimate:

```text
max(
  0,
  latest observed balance
  - explicit reserve
  - qualified recurring outflows in the horizon
  - scaled historical unscheduled-consumption buffer
)
```

Expected income is excluded until it arrives. The demo default reserve is EUR 500 and is returned with `demo_default` provenance; an explicit request is labelled separately. The spending buffer scales the upper-quartile 30-day historical scenario over unscheduled consumption, including groceries and transport after the three-basket correction. Qualified recurring rows are excluded from that buffer so they are not counted twice. At least 30 observed days and one complete comparison window are required; otherwise the result is unavailable rather than optimistic. It is never called a guarantee.

### Cash-flow preview

Qualified recurring items use robust median dates and amounts from up to six complete months. Housing and salary seed recurrence; utilities form a monthly envelope. The line after the observed balance is a 30-day scenario. Historical p25/p50/p75 unscheduled-spending paths are labelled variation, not probability or confidence. The interface calls this pattern-based rather than claiming that history-derived dates are confirmed future bills.

### Investment cash flows

The investment view reports only observed transfers: investment deposits, salary sweeps, withdrawals, net contributions, contribution months, and contribution share of observed salary. Requested ranges are clamped to the customer's observed account coverage; the product never inserts pre-account months as observed zero-contribution months. The data has no holdings, units, market values, fees, performance, products, or risk preferences, so the product returns no performance or investment advice.

### Financing history

`financing.py` parses linked synthetic mortgage records and SAS-style event timestamps into chronological, evidence-bearing history. The CUST00296 demo records a EUR 290,000 property, EUR 266,000 requested loan, EUR 24,000 equity, EUR 192,000 collateral value, a historical rejection, and EUR 630 in recorded fees. No transfer tax is shown because none exists in this linked history.

The `required_monthly_income_eur` field is excluded from calculations because gross/net/household semantics are undocumented. Historical context is never a current affordability assessment, approval probability, offer, or recommendation. Vehicle and custom goals receive no invented mortgage assumptions.

### Tax evidence and planning

Observed tax exists only when an explicit transaction category or mortgage expense field names a tax. An absent record returns `available: false` and null totals; it does not mean the customer paid no tax.

Tax planning accepts a user-declared amount, due date, amount already set aside, reserve, and whether the set-aside remains inside the supplied balance. The default conservatively protects the full declared tax amount when it remains in the balance. Monthly set-asides divide the remaining amount across calendar-month periods and round up to the next cent. The result is unsaved, `user_declared`, a scenario, and not tax advice. It infers no rate, liability, deduction, eligibility, or filing rule.

### VAT inside purchase prices

The VAT lens is distinct from paid-tax evidence and from the user's tax plan. It estimates the VAT already included in observed gross purchase prices:

```text
VAT inside = gross price × rate / (1 + rate)
```

The calculation chooses a Finnish rate regime from the transaction date, selects a band from a supported MCC first and an explicit category fallback second, rounds half up to integer cents per transaction, and then sums the rows. Every row records the rate, band, mapping source, mapping quality, and explanation. Known book and car-rental MCCs receive their distinct reduced/general bands. Missing or unsupported MCCs in mixed transport, travel, health, or entertainment categories remain uncovered instead of silently inheriting a precise-looking rate. The documented broad recreation estimate remains visibly labelled, as do mixed grocery and restaurant category estimates.

The period `coverage_basis_points` is therefore mapping coverage, not a confidence or accuracy percentage. The result is an estimated value over observed immutable source rows (`source_status: observed`, `value_status: estimated`, `scenario: false`), not a planning scenario. Method and rate-map versions plus the per-row rate evidence are bound into the fact ID. Complete calendar-month requests use observed month scope; partial explicit ranges are checked against the exact first and last observed dates.

The interface always uses an approximation marker and explains that mixed grocery baskets, restaurant alcohol, ambiguous recreation, and excise duties are limitations. It is a financial-literacy estimate, not a personal tax liability or filing calculation.

The CUST00001 September gold check is EUR 212.38 estimated VAT inside EUR 1,878.66 of spending, with complete mapping coverage for the selected synthetic rows.

Rate regimes and exemptions were checked against the Finnish Tax Administration's official [Rates of VAT](https://www.vero.fi/en/businesses-and-corporations/taxes-and-charges/vat/rates-of-vat/), [VAT rate changes](https://www.vero.fi/en/businesses-and-corporations/taxes-and-charges/vat/rates-of-vat/the-changes-to-VAT-rates/), and [VAT-exempt operations](https://vero.fi/en/businesses-and-corporations/taxes-and-charges/vat/rates-of-vat/business-operations-exempt-from-vat/) pages on 14 November 2026.

## 6. Coach and AI boundary

The guided primary flow works without AI. Offline routing recognizes a bounded set of English, Finnish, and Swedish questions and the guided topic directory exposes the same deterministic operations. It is not a general conversation or semantic-query engine.

With `GEMINI_API_KEY`, Gemini may:

- select an allowlisted intent;
- extract validated period/filter parameters;
- choose an allowlisted candidate or fact ID;
- ask a clarification question;
- phrase a cited explanation in the selected or clearly used query language.

Gemini cannot receive the full ledger, customer/account identifiers, raw transaction references, mortgage notes/events, or unrestricted actions. Display prose containing uncited numeric claims is rejected. Model output cannot mutate state directly. Mutations require a separate confirmed API action and provenance.

The adapter defaults to `gemini-3-flash-preview` and uses one nine-second deadline for both transport and fallback coordination, staying below the client's request timeout. It falls back on unavailable, malformed, unknown, or uncited output and returns a diagnostic reason. Financing prompts explicitly prohibit current eligibility, affordability, approval, recommended amounts/products, and offers. Tax prompts prohibit inferred rates, liabilities, and advice.

Supported local statistics and percentage-adjustment questions resolve their definitions and numeric scope before model redaction. Other eligible questions may use Gemini for bounded intent selection and nonnumeric phrasing when configured, while Python still produces every amount. `GET /api/health` reports only whether Gemini is configured; it never exposes a key.

### Resolved scope and bounded conversation

The local `query_scope.py` resolver runs before optional model interpretation for supported statistics. It resolves the concept, metric, start/end dates, reference date, and exact filters. Taxi, pharmacy and doctor concepts use specific merchant codes rather than silently widening to Transportation or Health. If the source has no matching code rows, the answer describes that identified-record limit rather than asserting no real-world spending.

Supported named months, ISO months/ranges, and relative months are interpreted against the selected synthetic data month. The response `query_scope` carries the customer/account, concept, metric, dates, reference date and filters. The optional request `previous_query` replays this bounded object for follow-ups; the server validates its shape, account ownership and history bounds. It does not accept an unrestricted conversation transcript. The client clears context on a new question or persona switch.

The returned scope drives matching transactions and the generic calculation view. An August result must open August rows even when the main UI still has September selected. The requested metric controls the answer headline: total, per-purchase average, count or largest outgoing transaction. A question with an unspecified average denominator asks for clarification.

| Area | Current support | Remaining limit |
|---|---|---|
| Familiar spending categories | Exact category filters, plus supported aggregate spending/outflow definitions | Categories do not reveal receipt line items or purchase motivations. |
| Narrow concepts | Supported exact MCC definitions, including taxis, pharmacies and doctors | Brand and item questions such as coffee or a specific ride-hailing brand cannot be established. |
| Dates | Supported historical month/ISO-range questions and relative months | Other relative phrases and incomplete ranges ask for clarification rather than being guessed. |
| Averages | Explicit average per purchase | Average per calendar month is not currently calculated; do not substitute a per-transaction value. |
| Follow-ups | Bounded compatible changes to the previous category/date/metric | This is not long-term memory of every conversational topic. Unsupported filters or topic changes require clarification. |
| Affordability | Ask for the item, amount and timing; offer supported planning inputs | No current approval decision or guaranteed future affordability. |

The [customer acceptance guide](USER_TEST_JOURNEYS.md) records 40 turns across eight journeys, including expected definitions, evidence, missing context and useful next actions. Passing isolated arithmetic or resolver assertions does not establish that a whole customer journey is easy or helpful.

## 7. Interface, localization, and accessibility

The customer interface supports English, Finnish, and Swedish without Gemini. The explicit language choice is persisted when browser storage is available; browser locale supplies the initial default. EUR and dates use locale-aware formatting. Other-language free text is optional and requires configured Gemini; it does not localize the interface itself.

### Home and spending exploration

Today, Spending, Goals and Journal form the main navigation. Coach has both a prominent Home invitation and persistent access. Home leads with the available balance, familiar consumption categories and one useful next action. The forecast is explicitly labelled **30-day balance forecast**, with an estimated end balance and low point, rather than a vague promise about what may happen next.

The interactive ring includes outgoing consumption only. Income, balance and saving transfers are shown separately and are not competing slices of that ring. Categories are organized into Everyday life, Home & essentials, and Life & leisure; these navigation groups are distinct from the partner's three educational baskets, which remain a secondary explanation. A selected ring slice and its labelled category button refer to the same period-scoped rows. Keyboard-operable category controls and labelled amounts provide access beyond color and pointer gestures.

Phone layouts use a vertical hierarchy and touch-sized controls; tablet expands the reading area and desktop uses a two-column workspace. The separate `device-preview.html` provides representative viewport frames rather than physical-device emulation. Reduced-motion support, semantic landmarks, native dialogs, visible focus and accessible chart descriptions remain part of the implementation.

### First visit and personal context

A first-visit invitation opens a brief, optional three-step tour. “Try now” actions take the customer to the relevant spending, coaching or preference control. It can be skipped or replayed. A risk quiz is not required to use the app, and these preferences do not establish investment suitability.

Personalization asks what the customer wants to make room for, a gentle/direct coaching style, protected spending, and optional goal milestones. Preferences work for the current visit. An explicit opt-in allows them to persist on this browser for the selected demo persona. Bounded statements such as wanting to save for a car can produce a proposed preference, which requires the user's separate confirmation. Mixed or negated style statements do not generate a guessed preference.

The editable notebook separates structured preferences from free-form reflections. Goals and protected categories guide current suggestions; explicit customer exploration can still ask about a protected category. Free-form notes are for the user to revisit and are not passed as model instructions or silently treated as verified financial facts. Notes can be added, edited and deleted; consent can be revoked and the profile forgotten.

### Journal and optional milestones

The journal shows dated income, a housing payment and the largest recorded purchase within the selected source scope. It preserves source references internally for navigation. It does not infer a holiday, job change, emotional state or life story from a payment category. Customers can add their own meaning through explicitly labelled personal reflections.

Optional milestones use the saved amount entered for a goal. A scenario, link, page view or plan does not move money or increase recorded savings. The design avoids punitive streaks, spending rewards and claims of real-time deposits.

### Progressive disclosure and visual references

The first answer is plain and actionable. Evidence controls reveal understandable dates, filters, matching rows and calculation summaries on request. Transaction hashes and fact IDs remain internal identifiers instead of normal customer-facing text. Technical transparency is preserved through inspectable source selection, not by requiring a phone user to read raw hashes.

S-mobiili's green/white hierarchy, Nordea's category-to-transaction exploration, Monzo's spending views and Apple's brief contextual onboarding inform the design. The original S-Coach mark remains distinct from protected bank assets. [REDESIGN_PLAN.md](REDESIGN_PLAN.md) records the primary sources and the reasoning. These are design references; claims about lower cognitive load, motivation or emotional comfort require human testing, not visual imitation alone.

The four README images show the earlier interface before this redesign. They remain explicitly labelled historical examples; a fresh browser walkthrough and screenshots of the new experience are not claimed.

## 8. Privacy and security posture

- Only synthetic challenge data is used.
- Raw data and generated databases are ignored.
- SQL values are parameterized and server-side customer/account/date scope is mandatory.
- Static path traversal is rejected.
- Request bodies and query keys are allowlisted.
- Raw transactions are immutable; audit events are append-only.
- Actuals, corrections, user declarations, and scenarios are distinct.
- Optional model context is minimized and validated.
- Secrets live only in ignored environment configuration.
- Browser preferences default to no persistence. `experience.js` saves only allowlisted profile fields and explicitly confirmed notes under versioned, persona-specific keys; no transcript is automatically copied.
- Storage exceptions fall back to the current visit. A failed preference deletion is reported separately from a successful in-memory reset. Free-form notes are rendered as text and are not model instructions.

The notebook is browser-local demo storage without real bank authentication or encryption key management. Selecting a synthetic persona is not an authorization boundary; a shared browser can expose its remembered profile. Browser opt-in/edit/delete controls are implemented, but a production bank consent lifecycle, authorization, retention/deletion service, bank-host callbacks, rate limiting, fraud monitoring and regulatory review are outside this prototype.

## 9. Local and deployable operation

The current implementation runs locally on a loopback HTTP server. It does not require a private external server. The same standard-library application can be containerized or hosted behind S-Pankki authentication, but no production deployment is included or claimed.

With the existing demo database, run this from the **repository root**:

```bash
PYTHONPATH="s bank" python3 -m scoach \
  --db "s bank/var/scoach.sqlite3" \
  --host 127.0.0.1 --port 8088
```

Open the [app](http://127.0.0.1:8088/), [phone/tablet/desktop preview](http://127.0.0.1:8088/device-preview.html), or [health endpoint](http://127.0.0.1:8088/api/health) on the same computer. The terminal must remain running; `Ctrl+C` stops the process. The device preview changes viewport dimensions rather than emulating a particular physical device.

For optional Gemini, export `GEMINI_API_KEY` and optionally `GEMINI_MODEL` in the server's shell **before starting the server**, then restart after changing them. The application reads process environment variables and does not automatically load a `.env` file. A `gemini_configured: true` health field means configuration is present, not that the key or model service has been successfully tested.

See the [README](../README.md) for first-time dataset setup, database import, complete run instructions, environment setup, and troubleshooting. The [pipeline](PIPELINE.md), [API contract](API.md), and [demo script](DEMO_SCRIPT.md) describe the source inventory, endpoints, and guided walkthrough.

## 10. Verification status and limits

- Before this redesign, the pre-push run recorded **176 passing tests and one skipped optional browser test** out of 177 discovered. An earlier run included 177 passing tests with headless-Chrome device/locale flows. These are historical results for the prior implementation and interface.
- The latest redesign run discovered **248 tests: 247 passed and one optional browser test skipped**. It includes semantic-scope, multi-turn, income direction, unsupported-qualifier/motive handling, consent/storage, real API-to-client calculation evidence, category parity and personalized scenario-to-goal handoff checks. JavaScript syntax, Python compilation and whitespace checks passed.
- Supported MCC/date/follow-up cases and returned-scope evidence replace the earlier known broad-taxi, ignored-month and restaurant-specific evidence defects. This does not establish unrestricted natural-language coverage.
- The current machine has no configured Gemini key. Fake-transport, privacy, timeout, response-validation and fallback tests exist; successful live provider behavior remains unverified.
- There has been no fresh authorized browser walkthrough of the redesigned screens. Existing screenshot assets are clearly labelled as the earlier interface. Perceived visual quality, ease of interaction and customer benefit need an authorized browser review and human testing.
- For fixture validation, select Alex (`CUST00001`), September 2026 and English. Restaurant spending is EUR 225.70 over ten purchases; groceries are EUR 379.79 over five; a 20% dining reduction is an unsaved EUR 45.14 scenario. Safe-to-spend uses the synthetic data reference date rather than the real current week.
- [USER_TEST_JOURNEYS.md](USER_TEST_JOURNEYS.md) separates acceptance expectations from observed test results and covers customer control, meaningful next actions and follow-up usefulness.

Run the standard suite from the repository root:

```bash
PYTHONPATH="s bank" python3 -m unittest discover -s "s bank/tests" -v
```

The optional browser test requires an existing Playwright runtime and Chrome; some tests also bind a local HTTP port. Any permission-related skip or failure must be reported separately from an assertion failure. Do not claim a fresh full-suite pass unless that full command has actually completed successfully in the current verification run.

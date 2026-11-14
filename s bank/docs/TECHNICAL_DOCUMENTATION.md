# S-Coach Technical Documentation

## 1. Product boundary

S-Coach is a local Junction 2026 prototype that turns the official synthetic S-Pankki transaction data into an adaptive financial-coaching experience. It is mobile-first and responsive rather than mobile-only. The same application supports phone, tablet, and desktop layouts.

The product separates four kinds of information:

1. **Observed facts** from immutable synthetic transaction and mortgage records.
2. **Derived classifications and statistics** calculated deterministically from a validated customer, account, period, and row selection.
3. **User declarations and corrections** such as a one-off transaction or a planned tax amount.
4. **Scenarios** such as safe-to-spend, cash-flow preview, spending adjustment, and goal pace. A scenario never rewrites observed history.

This repository contains no real customer data, bank credentials, production authentication, payment initiation, loan decisioning, investment recommendation, or personal income-tax liability calculation.

**Current status (14 November 2026):** the responsive prototype and deterministic calculations are implemented, but general natural-language scope interpretation is not complete. Correct arithmetic over a selected set of rows does not establish that the selected rows answer the user's question. The known gaps and verification limits are recorded in sections 6 and 10.

## 2. Runtime architecture

```text
official synthetic CSV files (ignored)
    -> BOM-aware streaming importer
    -> selected-persona SQLite database (ignored)
    -> immutable ledger + derived financial roles
    -> deterministic analytics / statistics / scenarios
    -> bounded coach candidates and fact IDs
    -> optional Gemini intent and wording adapter
    -> standard-library JSON/static HTTP server
    -> dependency-free responsive web client
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
| `scoach/state.py` | User corrections, append-only audit, undo, reset |
| `scoach/scenarios.py` | Spending scenarios and scenario-only exclusions |
| `scoach/goals.py` | Universal goal plan and contribution links |
| `scoach/financing.py` | Read-only linked mortgage history, fees, and limitations |
| `scoach/tax.py` | Explicit observed-tax evidence and user-declared tax planning |
| `scoach/vat.py` | Date-aware VAT-inside-price estimates with MCC/category provenance |
| `scoach/coach.py` | Offline intent routing, localized bounded explanations, candidate ranking |
| `scoach/gemini.py` | Minimized context, response schema validation, timeout/fallback |
| `scoach/api.py` | HTTP validation, JSON envelope, static server, deterministic tool execution |
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

The general statistics filters currently support category, derived role, transaction type, and merchant ID. Although the database stores MCC codes, the general statistics/coach query interface does not yet support an MCC filter. The separate VAT module uses MCC codes for tax-band estimates; that capability does not make narrow spending concepts such as taxis or pharmacies reliable coach queries.

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

The official percentage-adjustment question is intentionally routed locally because numeric and currency input is redacted before any model call. The other non-sensitive official questions may use Gemini for bounded intent selection and nonnumeric phrasing when configured, while Python still produces every amount. `GET /api/health` reports only whether Gemini is configured; it never exposes a key.

### Known question-scope and evidence gaps

| Area | Current behavior | Testing guidance / pending work |
|---|---|---|
| Narrow spending concepts | Offline `taxi`/`taxis` maps to all `Transportation`; pharmacy/doctor terms map to all `Health`. | CUST00001 September's EUR 266.80 is transportation, not a verified taxi total. Add explicit concept-to-MCC definitions or request clarification instead of widening the question. |
| Dates in questions | Offline statistics copies the selected interface month. An explicit August question with September selected still queries September. The coach tool accepts monthly periods, while the direct statistics API supports explicit date ranges. | Change the month selector for current manual tests. Date resolution, relative-date reference rules, and arbitrary-range coach queries remain pending. |
| Follow-up questions | The client sends the current message, selected month, and locale; it does not pass a resolved prior query. | Ask complete standalone questions. A follow-up such as `And groceries?` is not reliable. |
| Matching-row period | The coach's matching-row button passes filters but retrieves rows using the current UI month. | A model-selected period different from the UI month can show mismatched evidence. Bind row navigation to the returned tool-result scope. |
| Generic calculation evidence | Non-role transaction queries can still receive restaurant-specific calculation context. | Non-restaurant source rows may be correct while their calculation explanation is not. Generalize evidence context before claiming arbitrary-category drill-down is complete. |

The next semantic verification layer should record the expected concept, account, period, metric, filters, matching rows, and clarification/unavailable outcome for a set of independently reviewed questions. That plan must be preserved from interpretation through SQL/statistics and evidence navigation. Valid parameters and exact arithmetic alone do not provide this guarantee.

## 7. Interface, localization, and accessibility

The customer interface supports English, Finnish, and Swedish without Gemini. The explicit choice is persisted when browser storage is available; browser locale supplies the initial default. Navigation, controls, forms, dynamic labels, errors, empty states, accessibility names, and deterministic coaching are localized. EUR and dates use locale-aware browser formatting.

Other-language free text is optional and requires configured Gemini. This does not localize the product interface itself.

Phone widths use one vertical coaching story and large touch targets. Tablet expands reading width. Desktop uses a centered two-column financial workspace rather than a simulated phone. A separate `device-preview.html` is local development tooling for representative viewport frames and is not linked from customer navigation.

The interface uses semantic landmarks, labels, native dialogs, keyboard focus, visible focus rings, reduced-motion support, non-color status labels, and SVG titles/descriptions. Formulas, assumptions, and source references are disclosed on demand so the first view remains readable.

The visual system is inspired by current public S-Pankki/S-mobiili cues—green and white, clear hierarchy, rounded soft surfaces, and selective bright-green highlights—but uses an original S-Coach mark and does not copy the protected official logo.

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

This prototype does not implement production authentication, authorization, consent, retention, deletion, encryption key management, bank-host callbacks, rate limiting, fraud monitoring, or regulatory review. Those remain S-Pankki integration responsibilities.

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

- Latest pre-push run on 14 November 2026: **176 tests passed, one optional browser test skipped** out of 177 discovered. HTTP tests ran; the browser integration was deliberately not enabled. JavaScript syntax, Python compilation, documentation links, and README screenshot files were also checked.
- The earlier integrated run recorded **177 passing tests**, including headless-Chrome phone/tablet/desktop and EN/FI/SV flows. This is historical verification of that implemented test set, not proof that every natural-language question is interpreted correctly.
- Subsequent read-only scope audits reproduced the taxi, date, follow-up, and evidence-context gaps above. Some existing example assertions accept the broad transportation mapping, so a green suite does not resolve that defect.
- The current machine's demo has no configured Gemini key. Fake-transport, privacy, timeout, response-validation, and fallback tests exist; a successful live Gemini request has not been verified.
- The latest device-preview contract check passed its three checks. The latest preview handoff did not include a fresh browser walkthrough; the earlier browser evidence remains historical.
- For current manual validation, select Alex (`CUST00001`), September 2026, and English. Restaurant spending is EUR 225.70 over ten purchases; groceries are EUR 379.79 over five; a 20% dining reduction is an unsaved EUR 45.14 scenario. Safe-to-spend uses the synthetic data reference date, not the real current week.

Run the standard suite from the repository root:

```bash
PYTHONPATH="s bank" python3 -m unittest discover -s "s bank/tests" -v
```

The optional browser test requires an existing Playwright runtime and Chrome; some tests also bind a local HTTP port. Any permission-related skip or failure must be reported separately from an assertion failure. Do not claim a fresh full-suite pass unless that full command has actually completed successfully in the current verification run.

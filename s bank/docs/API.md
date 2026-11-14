# S-Coach Local API

S-Coach exposes a dependency-free JSON API from the same local server as the responsive web client. The prototype uses synthetic challenge data and has no production authentication. A real S-mobiili integration must supply authenticated customer/account scope at the host boundary.

## Envelope and money

Successful responses use:

```json
{"ok": true, "data": {}}
```

Validation and service errors use:

```json
{"ok": false, "error": {"code": "validation_error", "message": "..."}}
```

Money is authoritative in integer-cent fields such as `outflow_total_cents`. The API decorates these with display strings such as `outflow_total_display`, but the web client applies the selected locale when rendering EUR.

Every customer-scoped call accepts `customer_id`; the demo defaults to `CUST00001`. An optional `account_id` must belong to that customer. Unknown query keys, body fields, accounts, dates, filters, and references are rejected.

## Read endpoints

| Endpoint | Important parameters | Result |
|---|---|---|
| `GET /api/health` | none | Server/database readiness plus `gemini_optional` and secret-free `gemini_configured` booleans |
| `GET /api/personas` | none | Available synthetic demo personas |
| `GET /api/overview` | `customer_id`, `month` | Money Map, current priority, facts, candidates, saved scenarios |
| `GET /api/comparison` | `month`, `comparison_month`, optional exact filters | Complete-period comparison |
| `GET /api/transactions` | `month` or `start`/`end`, exact filters, optional `transaction_ref` | Scoped immutable ledger rows |
| `GET /api/trends` | `month`, `months`, optional filters | Monthly series and evidence |
| `GET /api/forecast` | `as_of`, optional JSON `assumptions` | Pattern-based 30-day cash-flow scenario |
| `GET /api/safe-to-spend` | `as_of`, `days`, optional `reserve_floor_cents` | Reserve-, outflow-, and history-protected estimate |
| `GET /api/investments` | `month`, `months` | Observed deposits, salary sweeps, withdrawals, and range coverage |
| `GET /api/financing` | `goal_type=home` | Optional linked historical mortgage context only |
| `GET /api/statistics` | `month` or `start`/`end`; one or more of `category`, `role`, `transaction_type`, `merchant_id` | Exact total/count/average/largest/net with row evidence |
| `GET /api/statistics/compare` | two months or two explicit date ranges plus the same filters | Exact comparison over one filter scope |
| `GET /api/taxes` | `month` or `start`/`end` | Explicit tax-labelled records only; absence is unavailable, not zero |
| `GET /api/vat` | `month` or `start`/`end` | Estimated VAT inside purchase prices, per-row mapping quality, mapping coverage, and period total |
| `GET /api/goals` | `customer_id` | Saved demo goal plans and linked scenarios |

Exact statistics filters are combined with AND. A model may extract a filter, but the server validates it against that customer's catalog and performs all arithmetic locally. This validates the requested parameters and arithmetic; it does not prove that a natural-language question was translated into the correct filter or period. General statistics currently has no `mcc_code` filter.

## Coach

`POST /api/coach`

```json
{
  "customer_id": "CUST00001",
  "month": "2026-09",
  "locale": "en",
  "message": "How much did I spend on restaurants?"
}
```

The response includes the bounded `intent`, parameters, nonnumeric explanation blocks, `source` (`deterministic` or `gemini`), `fallback_reason`, and—when a deterministic tool runs—`tool_kind`, `tool_result`, fact IDs, and source references. Numeric values in the UI come from `tool_result`, never from model prose.

With Gemini disabled and the supplied demo database, this example selects `intent: transaction_statistics`, `parameters: {"period": "2026-09", "category": "Restaurants"}`, and `tool_kind: transaction_statistics`. The result has `filters: {"category": "Restaurants"}`, `start: "2026-09-01"`, `end: "2026-09-30"`, `outflow_total_cents: 22570`, `transaction_count: 10`, and `average_outflow_cents: 2257`, with the matching row references. The equivalent explicit query is:

```text
GET /api/statistics?customer_id=CUST00001&month=2026-09&category=Restaurants
```

The request's `month` supplies the offline coach period. Dates mentioned in `message` are not reliably resolved, and follow-up messages do not inherit a previous query. For manual tests, select the month explicitly and repeat the full category question. Narrow concepts remain a known defect: asking about taxis currently selects all `Transportation` rows, so EUR 266.80 must not be described as taxi spending. See the [README](../README.md) for current limitations and supported test questions. The five official brief questions are therefore not all semantically complete.

Supported offline product locales are `en`, `fi`, and `sv`. With `GEMINI_API_KEY`, clear free-text queries in other languages may receive prose in the query language while all values remain locally calculated.
The percentage-bearing spending-adjustment question remains locally routed so redacted numeric input cannot be reconstructed or changed by a model; its exact result still comes from the same deterministic tool.

## Confirmed scenario and state endpoints

All POST endpoints below require `"confirmed": true`. State changes are separate from immutable source rows and receive audit provenance.

| Endpoint | Purpose |
|---|---|
| `POST /api/scenarios` | Save a percentage spending-adjustment scenario |
| `POST /api/scenarios/exclude` | Exclude one scoped row from a scenario only |
| `POST /api/rules` | Confirm a row correction or matching rule |
| `POST /api/goals` | Create a universal goal plan |
| `POST /api/goals/link` | Link a modeled contribution to a goal; creates no transfer |
| `POST /api/undo` | Reverse the latest reversible demo action |
| `POST /api/reset` | Clear one persona's user-created demo state |

The coach's official dining-reduction answer is a read-only preview. It does not call `POST /api/scenarios` until the customer explicitly confirms a saved scenario.

## User-declared tax plan

`POST /api/tax-plan` requires a positive `amount_cents`, future `due_date`, `reference_date`, and confirmation. Optional fields are `already_set_aside_cents`, signed `current_balance_cents`, `reserve_floor_cents`, `set_aside_location`, and `label`.

The response is an unsaved planning scenario. It uses only the supplied amount and date, creates no liability or payment, and infers no tax rate, deduction, filing rule, or legal conclusion.

## Evidence and status conventions

- `observed: true` means the result is derived from immutable source rows; it does not by itself mean every derived value is directly observed.
- `scenario: true` identifies a planning result. VAT sets `scenario: false`, `source_status: observed`, and `value_status: estimated` because it estimates a value on observed purchases rather than modeling a future action.
- `fact_id`, `transaction_refs`, and where relevant `mortgage_event_refs` support the calculation drawer.
- VAT rows are always `estimated`; `rate_source` states whether MCC or category supplied the band, while `mapping_quality` distinguishes direct MCC, documented category fallback, broad estimate, and unmapped rows. `coverage_basis_points` is mapping coverage, not an accuracy or confidence score.
- VAT facts expose `method_version` and `rate_map_version`; their fact IDs bind those versions and the per-row rate evidence.
- Financing history is always `historical_context_only` and never current credit advice.

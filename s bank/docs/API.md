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
| `GET /api/statistics` | `month` or `start`/`end`; `category`, `role`, `transaction_type`, `merchant_id`, `mcc_code`, `consumption_only=true` | Exact total/count/average/largest/net with row evidence |
| `GET /api/statistics/compare` | two months or two explicit date ranges plus the same filters | Exact comparison over one filter scope |
| `GET /api/taxes` | `month` or `start`/`end` | Explicit tax-labelled records only; absence is unavailable, not zero |
| `GET /api/vat` | `month` or `start`/`end` | Estimated VAT inside purchase prices, per-row mapping quality, mapping coverage, and period total |
| `GET /api/goals` | `customer_id` | Saved demo goal plans and linked scenarios |

Exact statistics filters are combined with AND. MCC values must be four-digit strings; `consumption_only` accepts only the exact string `true` and selects negative purchase/housing/utility rows, excluding transfers. These filters also apply to transactions and comparison reads. A model may extract a filter, but local semantic resolution takes precedence for supported questions. The server validates parameters and performs all arithmetic locally; unsupported definitions must clarify rather than silently widen.

## Coach

### Experience-redesign additions

The redesign adds optional `previous_query` to `POST /api/coach`. Send back only the last response's `query_scope`, containing `customer_id`, `account_id`, `concept`, `metric`, `start`, `end`, `reference_date`, and exact `filters`. The server validates the customer/account and fields before using follow-up context. It does not accept a raw transcript or arbitrary execution instructions.

Responses add `query_scope`, `clarification_options` (complete suggested questions), and a bounded `clarification_code` when scope is missing. Matching-row navigation uses the returned scope's dates and filters rather than the interface month. Frontend preference memory remains browser-local and is not sent as a transcript to the API.

`tool_result.metric_value_cents` or `metric_value_count` supplies the selected headline metric. `consumption_total` with `filters: {"consumption_only":"true"}` answers total spending; `outflow_total` for all account activity includes saving transfers. For Alex in September 2026 these are EUR 1,878.66 and EUR 2,114.38 respectively. No model arithmetic is used.

`inflow_total` distinguishes salary (`transaction_type=salary`), classified income (`role=income`), and all incoming credits (no filters, concept `All inflows`). The latter can include savings/investment transfers and is not earnings. Incoming evidence references contain only positive credited rows. Matching-row and calculation navigation preserve the selected metric as well as dates/filters; the client uses the verified server average rather than computing a new average from an incomplete page of rows.

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

The request's `month` is the data-relative reference period. Supported explicit dates in the question override it, and validated `previous_query` supports compatible follow-ups. Narrow taxi queries use MCC4121 rather than all Transportation. A missing matching code row means no identified record, not proof of no real-world spending. Unknown item/brand scope, unsupported weekday/refund/exclusion qualifiers, multi-bank requests, missing affordability context, and an unspecified average denominator receive bounded clarification. See the [README](../README.md) and [customer journeys](USER_TEST_JOURNEYS.md) for examples and remaining limits.

Supported offline product locales are `en`, `fi`, and `sv`. With `GEMINI_API_KEY`, clear free-text queries in other languages may receive prose in the query language while all values remain locally calculated.
The percentage-bearing spending-adjustment question remains locally routed so redacted numeric input cannot be reconstructed or changed by a model; its exact result still comes from the same deterministic tool.

Percentage adjustments accept one complete percentage from 0 through 100, including decimal points/commas and common English, Finnish and Swedish number words. Decimal percentages use exact decimal strings internally; money remains integer cents. Invalid values, multiple alternatives, ranges, percentage points and unsupported expressions return `needs_clarification` with `clarification_code: adjustment_percentage`, without substituting a spending-total answer or calling the model.

The additional `vat_estimate` coach intent uses the existing response envelope and returns the same `tool_result` as `GET /api/vat`, with `tool_kind: vat_estimate`. Supported local terms include VAT / tax inside, ALV / arvonlisävero, and moms / mervärdesskatt. Named months and explicit ISO ranges use the shared date resolver; resolved internal parameters are `period` or `start`/`end`. The optional language adapter may select a validated monthly VAT intent but cannot calculate a tax amount. This is the estimated VAT already included in whole-period purchase prices, not an additional outflow, proof of paid personal tax, liability or reclaimable amount. Category-specific VAT and liability requests clarify their unsupported scope. Generic paid-tax questions retain the distinct `observed_tax_evidence` tool.

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

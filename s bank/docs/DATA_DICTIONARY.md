# S-Coach Data Dictionary

## Official transaction fields

| Field | Source type | Application treatment |
|---|---|---|
| `customer_id` | text | Synthetic customer scope; never sent to Gemini |
| `bank_account_id` | text | One account per supplied customer; retained in evidence |
| `tx_date` | ISO date | Period aggregation and complete-month checks |
| `tx_timestamp` | timestamp text | Ordering; not unique |
| `category` | text | Source category, immutable |
| `tx_amount_eur` | decimal text | Signed integer `amount_cents` |
| `balance_after_eur` | decimal text | Signed integer `balance_after_cents` |
| `transaction_type` | text | Primary accounting semantic |
| `merchant_id` | nullable text | Optional recurrence clue; absence remains unknown |
| `mcc_code` | nullable text | Optional category clue; absence remains unknown |

## Derived transaction fields

| Field | Meaning |
|---|---|
| `transaction_ref` | Stable source-line plus full-row hash reference |
| `accounting_role` | `income`, `fixed_obligation`, `flexible_essential`, `discretionary`, `saving_or_transfer`, or `needs_review` |
| `literacy_role` | Customer-facing `regular essentials`, `irregular essentials`, `everyday discretionary`, or `needs review` where applicable |
| `fact_id` | Server-generated allowlisted reference to one deterministic result |
| `observed_or_scenario` | Prevents modeled values from being presented as actual history |

## Customer and mortgage fields

`tx_customers_junction.csv` supplies synthetic age and postal code. The product does not use either for peer comparison or recommendation ranking.

Mortgage history remains recorded historical context. `required_monthly_income_eur` has undocumented gross/net/household semantics and must not be presented as a comparable underwriting threshold.

## User-state entities

| Entity | Purpose |
|---|---|
| row correction | Changes a derived role while preserving the source row/category |
| matching rule | Explicit customer-confirmed category/merchant rule for derived views |
| scenario | Stores adjustable base, percentage and observed-versus-modeled result |
| scenario exclusion | Removes one row only from that scenario's adjustable base |
| goal | Stores name, target, date, saved amount and reserve floor |
| goal link | Associates a modeled contribution with a goal; never creates a transfer |
| audit event | Append-only before/after record with user/deterministic/confirmed-AI provenance |


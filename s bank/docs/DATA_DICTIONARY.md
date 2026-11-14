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

## Estimated VAT fields

These fields are derived for spending outflows only. They do not change the source transaction and do not represent a customer's tax liability.

| Field | Meaning |
|---|---|
| `gross_cents` | Absolute observed purchase price including any VAT |
| `estimated_vat_cents` | VAT estimated inside the gross price; null when no honest mapping exists |
| `rate_basis_points` | Date-aware Finnish rate, for example `1350` for 13.5%; null when unmapped |
| `rate_band` | `general`, `food`, `reduced`, `newspapers`, `exempt`, or `unknown` |
| `rate_source.kind` | `mcc`, `category`, or `unmapped` |
| `rate_source.value` | Exact MCC or source category that selected the band |
| `mapping_quality` | `direct_mcc`, `category_fallback`, `broad_mcc_estimate`, `broad_category_estimate`, or `unmapped` |
| `mapping_note` | Plain-language reason for the mapping choice or why no rate was assumed |
| `coverage_basis_points` | Share of period gross spending for which any rate band was available; mapping coverage, not accuracy or confidence |
| `source_status` / `source_observed` | Confirms that the source purchases are immutable observed rows |
| `value_status` / `estimated` | Identifies the VAT amount as estimated rather than directly observed |
| `scenario` | Always false for this historical lens; VAT is not a what-if plan |
| `method_version` / `rate_map_version` | Version identifiers bound into the VAT fact ID with per-row rate evidence |

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


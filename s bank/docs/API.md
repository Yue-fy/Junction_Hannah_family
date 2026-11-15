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
| `GET /api/health` | none | Server/database readiness plus secret-free `gemini_optional`, `gemini_configured` and `agent_configured` booleans; configured does not imply available quota |
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

### Tool-calling agent, text history and chat client (WP1, WP2, WP6)

`POST /api/agent` is a read-only route and does not require `confirmed`. It accepts the same common customer/account/month fields as `/api/coach`, plus:

```json
{
  "customer_id": "CUST00001",
  "month": "2026-09",
  "locale": "en",
  "message": "How much did I spend on restaurants?",
  "history": []
}
```

`message` must be nonempty text up to 2,000 characters; `locale` is `en`, `fi` or `sv`. `history` is optional and defaults to `[]`. It accepts at most eight messages, each with exactly `role` (`user` or `coach`) and nonblank `text` of at most 600 Unicode characters. Oversized histories, other roles, extra fields, non-text values and embedded tool metadata return a validation error before a model call. The existing 64 KiB HTTP body limit accommodates the frontend's bounded UTF-8 payload.

The agent converts historical `user` / `coach` roles into provider `user` / `model` roles, redacts identifiers and appends the current message. Only text is replayed: previous tool calls, results, thought signatures and action proposals are not accepted as history. Every request starts with fresh tool evidence. Numbers quoted in history remain permitted by the numeric provenance check as conversational inputs; this does not establish them as fresh ledger facts.

The frontend exposes `createAPI(customerId).agent(message, {month, locale, conversation})`. It derives the history from existing conversation records, filters customer/month/language mismatches, sends the last eight visible user/coach messages and clips each to 600 Unicode code points. It never serializes transaction references, charts, structured responses or internal state. The currently displayed transcript is left intact. Existing new-question, persona/month and language resets clear the source history; the helper stores no additional copy.

Agent requests have a 40-second client timeout to accommodate the 25-second server budget. Other requests retain their 10-second default; `get` and `post` accept an optional `{timeout}` override. The page's `askCoach` uses this helper, retains twenty exchanges and checks customer/generation/language/sequence before rendering. Explicit preference declarations remain local. A deterministic envelope uses `legacy` through the existing renderer; offline follow-ups that need `previous_query` or a planned-purchase continuation use the unchanged `/api/coach` request contract after fallback.

The client escapes all agent text, permits bold within plain paragraphs and derives charts only from the returned `chart.series`. Evidence buttons reopen the exact server query in the existing transaction view. `create_goal` fills the editable goal form without a POST; `save_scenario` opens a separate review dialog and sends the exact proposed category, percent and month only after confirmation. `open_view` is limited to the four primary views. Actions and suggestions are bound to their retained conversation turn and become inert after a scope reset.

The response `data` contains:

| Field | Meaning |
|---|---|
| `source` | `agent` or `deterministic` |
| `fallback_reason` | `null`, `not_configured`, `timeout`, `unavailable`, `unverified_numbers`, or `max_steps` |
| `answer` | Plain-text paragraphs; consumers must escape all text |
| `highlight` | Server-created `{label, value, caption}`, or `null` |
| `chart` | Server-created `{kind, title, series: [{label, value_cents}]}`, or `null`; missing observations remain `null` |
| `steps` | Successfully executed tools with plain-language labels |
| `evidence` | `{id, label, count, query}` records for `/api/transactions`; no raw references are sent to Gemini |
| `actions` | Optional `{kind, label, params}` buttons: `create_goal`, `save_scenario`, `open_view` |
| `suggestions` | At most three bounded follow-up questions |
| `scope` | Selected period `{start, end, reference_date}` based on the recorded data clock |
| `legacy` | Present on fallback; the existing deterministic coach payload for the same question |

`evidence.query` includes `start`, `end` and exact filters. Add the current customer scope when opening transactions. Comparison periods have separate evidence queries. Forecast and pattern evidence opens supporting account history, not a claim that every displayed row is a recurring bill. A chart's values and highlight amounts come from tool output; model-authored chart arrays are ignored.

Tools are `get_overview`, `spending_total`, `compare_periods`, `monthly_trend`, `list_transactions`, `safe_to_spend`, `forecast_30_days`, `what_if_reduce`, `goal_plan`, `list_goals`, `payday_pattern`, `recurring_payments`, `calculate`, `explain_concept`, and `propose_action`. Filters reuse the existing catalog and statistics validation. Spending defaults to consumption unless an explicit role or transaction type selects other flows. Money fields carry integer cents plus euro text; list truncation is declared. Monthly chart series are the explicit exception to the twenty-item list cap and retain up to twenty-four points.

Goal previews perform calendar-month target arithmetic with no assigned initial savings; they do not assess contribution capacity or affordability. Existing saved goal progress still uses the original goal engine. Scenario previews carry a monthly amount and twelve-month extrapolation, clearly marked as a scenario. Proposals must match a prior preview, contain no `confirmed` field and never execute a mutation. A client must present its confirmation flow, then POST the proposal to `/api/goals` or `/api/scenarios` with `confirmed: true` only after the customer agrees.

Goal target and monthly amounts must originate in customer text or previous verified calculations. Model-authored goal names, labels and echoed proposal text are excluded from numeric evidence. Public action `params` remain exact mutation inputs and are not decorated with additional display fields. The reference clock uses the most recent recorded day on or before the selected month's end, including the most recent earlier day when that month has no transactions.

The transport receives aggregates by default. Only `list_transactions` returns capped, allowlisted row details (date, weekday, category, transaction type, amount, merchant ID and MCC). Customer IDs, account IDs, raw transaction references, hashes and raw JSON stay server-side. No model transcript is persisted. Gemini model content is replayed verbatim for thought signatures, with function response IDs preserved when present. DeepSeek replies retain the original assistant message internally, including tool-call IDs and any reasoning content required for follow-up calls. Internal reasoning is never rendered in the answer.

The numeric gate accepts tool values, customer-input values and scope dates, with a one-cent tolerance and documented small plain-integer/year/date exceptions. Unsupported amounts trigger one corrective turn; a second failure returns the offline result. Small currency/percentage values are checked, and a cent integer alone does not authorize that integer as a euro amount. Compact magnitudes and scientific notation are normalized; unsupported or unbounded numeric notation fails verification. This is numeric provenance checking, not semantic or advice verification.

`Application(..., agent_transport=callable)` injects an offline test transport. Its signature is `(contents, *, system, tools, timeout) -> model_content`. The entire loop is limited to six model turns, twenty tool calls and twenty-five seconds. A transport timeout cannot continue executing database tools in the background; only bounded daemon transport workers may outlive a request. Errors, missing credentials and exhausted quota return the deterministic wrapper without retrying the optional legacy Gemini adapter.

Environment names (values belong only in ignored `.env` or the process environment):

| Name | Use |
|---|---|
| `DEEPSEEK_API_KEY` | Enables DeepSeek for `/api/agent`; takes priority over Gemini when both are set |
| `DEEPSEEK_MODEL` | DeepSeek model name, default `deepseek-flash` |
| `GEMINI_API_KEY` | Enables Gemini for `/api/agent` when DeepSeek is absent; existing `/api/coach` adapter is unchanged |
| `GEMINI_MODEL` | Gemini model name, default `gemini-3-flash-preview` |

DeepSeek uses `https://api.deepseek.com/chat/completions`, bearer authentication and OpenAI-style function tools. Thinking is disabled for the interactive deadline, and output is capped at 2,048 tokens. If a provider still returns reasoning with tool calls, it is preserved internally for replay. Provider failures fall back locally; they do not silently incur calls to a second provider. References checked on 2026-11-14: [DeepSeek tool calls](https://api-docs.deepseek.com/guides/tool_calls/), [thinking mode](https://api-docs.deepseek.com/guides/thinking_mode/), [chat completions](https://api-docs.deepseek.com/api/create-chat-completion/).

Wire-format references checked on 2026-11-14: [function calling](https://ai.google.dev/gemini-api/docs/function-calling), [thought signatures](https://ai.google.dev/gemini-api/docs/thought-signatures), [generateContent REST](https://aistudio.google.com/api-reference/generate-content/generate-content), and [Content/Part definitions](https://aistudio.google.com/api-reference/caching). The tutorial pages currently emphasize the Interactions API; this prototype uses the still-documented `generateContent` REST interface and its `systemInstruction`, `functionDeclarations`, `functionCall`, `functionResponse`, `thoughtSignature` and call `id` fields.

### Home monthly recap

The Home card reuses `POST /api/agent`; this adds no endpoint, request field, environment variable or backend calculation. `web/monthly-recap.js` owns the authoring prompt, bounded copy acceptance and twelve-entry in-memory cache. `web/app.js` owns rendering and the active account/month/language guard.

1. After the monthly overview loads, the card immediately shows available `salary_cents + other_income_cents`, `consumption_cents` and `committed_saving_transfers_cents` in the selected locale. Missing fields are omitted, not converted to zero. An overview failure clears the old card and disables its questions.
2. While Home is active, `createAPI.agent` sends a monthly authoring request with `conversation: []`. It asks for `get_overview` first, two short sentences containing two useful observations, and one standalone follow-up question. Existing tools compute facts. Optional comparisons use `compare_periods`; new arithmetic uses `calculate` with euro values rather than cent integers. Optional failures should be omitted from the narrative, never filled with invented figures.
3. The unchanged agent validates numeric provenance before returning `source: agent`. The Home consumer additionally requires a successful `get_overview` step and one to three nonempty answer paragraphs totaling at most 600 characters after removing bold markers. It escapes the resulting plain text. This is a source/shape/length gate, not a semantic proof or a guarantee of exact sentence count.
4. Accepted text replaces the recorded-figures copy and displays an AI source label. A deterministic envelope, malformed/long answer, missing overview step, network failure or timeout keeps the local facts and the account-summary label. The legacy answer to the authoring instruction is never shown as a monthly recap. Without monthly fields, the card says figures are unavailable.

Cache keys contain customer ID, selected month, locale and the complete loaded overview snapshot. Repeated rendering/navigation reuses pending or completed entries. A changed loaded snapshot requests fresh analysis; entries evict oldest-first beyond twelve. Failure entries are retained until eviction, snapshot change or page reload rather than automatically retrying. The cache is not persistent. It does not poll for changed ledger data. Existing 40-second client and 25-second server request budgets apply; old requests may finish in the background but cannot replace another scope's card.

Automatic generation does not set chat busy state, append a conversation turn, replay chat history or execute returned actions. It does not send browser preferences or notebook notes. Existing read-only tool sanitization and provider rules still apply. The primary button starts an ordinary Coach question about that month's income, spending and saving transfers. The secondary button sends only the chosen question; it does not inject the hidden authoring prompt or recap as history. Local buffer/protected-category follow-ups and optional personal-plan controls take precedence over a generated suggestion.

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

## V3 additions (2026-11-15)

All new reads follow the envelope and money rules above. All new writes require `"confirmed": true` and are recorded in `audit_events`; profile writes are undoable through `POST /api/undo`.

### Reads

| Endpoint | Parameters | Result |
|---|---|---|
| `GET /api/safe-to-spend` | adds `horizon=until_payday` (default for the Home card) or `week` | Until-payday estimate: balance minus known bills before payday, the Surprise must-pays buffer and the reserve floor; returns `next_payday`, `per_day_cents` and each held-back line. Uses `money_profile.planning_inputs` when the customer has a profile |
| `GET /api/spender-profile` | `month`, `months` (default 12) | Archetype id and label, the signals behind it, basket shares and a month-by-month stability series |
| `GET /api/explore` | `start`, `end`, `group_by` (category, role, month, weekday, mcc), `metric`, `top`, optional exact filters | Free MyData-style grouping with row evidence; used by clickable chart detail panels |
| `GET /api/cashflow` | `start_month`, `end_month`, `granularity=month\|year` | Income, consumption, savings transfers, net and saving rate per period, with `complete` flags |
| `GET /api/cashflow/summary` | same | `cashflow` plus `comparisons` (best/worst net period, `saving_rate_change` with `direction`) |
| `GET /api/year-review/options` | none | Years with enough data |
| `GET /api/year-review` | `year`, `locale` | Year-in-review facts and `story_cards` for the story viewer |
| `GET /api/profile` | `as_of` or `month` | Money profile: entries with `source` (`you_told_me`, `from_your_transactions`, `from_chat`), coaching `mode` (`normal`/`steady`) and `empty` |
| `GET /api/profile/suggestions` | `as_of` or `month` | Pending "Things I noticed" items derived from transactions; nothing is stored until confirmed |
| `GET /api/tax` | `as_of`, optional `tax_year` (defaults to the reference year) | Withholding estimate from the user's tax-card entry, tax-cycle stage and next date, back-tax set-aside plan, detected refund, `tax_entry_id` |
| `GET /api/vat/card` | `month` | One "Did you know?" VAT tile for the month's largest VAT category |
| `GET /api/benchmarks` | no `category`: list of supported categories; with `category`, `months`, `month` | Customer's monthly average vs Statistics Finland 2022 households in the same age band, with caveats |

### Writes

| Endpoint | Purpose |
|---|---|
| `POST /api/goals/update` | `{goal_id, fields}`: change name, target, date or saved amount |
| `POST /api/goals/delete` | `{goal_id}` |
| `POST /api/profile/entries` | Add one entry `{key, value, source}`; validated per key |
| `POST /api/profile/entries/update` / `.../delete` | Edit or remove one entry by `id` |
| `POST /api/profile/forget` | Delete the whole money profile (transactions untouched) |
| `POST /api/profile/suggestions/confirm` / `.../dismiss` | Keep or dismiss a noticed item |
| `POST /api/profile/migrate-local` | One-time import of the older browser-only notebook |
| `POST /api/year-review/captions` | Optional AI captions for the story cards (numbers come from the facts, never the model) |
| `POST /api/year-review/save` | Save the year review into the profile so it can be replayed |

### Agent changes

New read-only tools: `spender_profile`, `irregular_buffer`, `explore`, `cashflow_summary`, `safe_to_save`, `get_profile`, `tax_overview`, `vat_in_my_spending`, `year_review`, `compare_to_peers`. `safe_to_spend` gains `horizon`. `propose_profile_update` and `propose_action` kinds `update_goal`, `delete_goal`, `update_profile` and `open_year_review` only produce review cards; the customer confirms each write in the UI. The prompt includes a short profile summary and the coaching mode. The agent may take up to eight model turns. The number check accepts rounded figures introduced by "about/noin/ungefär"; if a second answer still contains unverified numbers, unverified sentences are removed (`verification: "trimmed"`) before falling back offline.

## V5 fix wave, lane NB (numbers and terms)

All additions are new keys; no key was removed or renamed.

- `GET /api/safe-to-spend` (spending plan):
  - every `held_back[]` item has `labels {en, fi, sv}`; `label` stays English. Clients show `labels[locale]` (no English "Rent" in FI/SV). Buffer vocabulary: kind `reserve` = Safety cushion / Turvatyyny / Säkerhetsmarginal, kind `buffer` = Surprise buffer / Yllätyspuskuri / Buffert för oväntat.
  - Mortgage plan: a recurring payment of the plan's `paid_as` type (default `housing_payment`) is **replaced** by one `held_back` item `{kind: 'loan', key: 'mortgage', label: 'Mortgage payment', source: 'plan', replaces_recurring_id}` dated on the plan's `payment_day` (else the day it is seen paid). A payment due after payday is not held back; it is listed in `upcoming_after_payday [{plan, date, amount_cents, labels}]`. `skipped_declared_items[]` entries get `replaced_by_plan`, `replaced_dates`.
  - Saved surprise-buffer goal (template `buffer`, not reached, not steady mode): held back as `{kind: 'buffer', key: 'buffer_goal', source: 'goal', goal_id}` with the goal's monthly amount when that is at least the history estimate; `buffer_cents` follows.
  - `shortfall_breakdown {cause: 'bills'|'everyday'|'saving'|'buffer'|'cushion'|null, cushion_kind: 'reserve'|'steady_reserve', balance_cents, bills_cents, everyday_cents, saving_cents, buffer_cents, cushion_cents, bills_over_balance_cents, below_zero_cents, cushion_kept_cents, cushion_short_cents, shortfall_cents, parts, texts {en,fi,sv}|null}`. Money covers bills, then everyday, saving, buffer, cushion; the first part not covered is the cause. `below_zero_cents` (bills + everyday − balance) is the "account goes below zero" figure; `shortfall_cents` still includes the cushion. Texts use whole euros.
  - `summary[locale][0]` now shows the daily-life sum: "everyday basics X + free to spend Y = Z, about W a day" (or "Nothing is free to spend…" in a shortfall); the shortfall line is `shortfall_breakdown.texts`.
  - The 30-day preview puts salary on the same payday as the plan (pay-day cluster + weekend rule; irregular pay: the plan's next payday).
- `GET /api/plans/mortgage/projection` and `/preview`: a typed annuity payment is the ONE payment: totals, payoff month, yearly split, curve and rate what-ifs use it (payoff solved from it). Rate what-ifs keep the term and move relative to the shown payment (`payment_change_cents = monthly_payment_cents − shown`). New `term_basis ('payment'|'years')`, `entered_months`; `calculated_payment_cents` = what the years left alone would need (explains note `payment_differs`).
- `GET /api/plans/tax`: new `status ('needs_inputs'|'set_aside'|'withholding_looks_ok'|'nothing_to_set_aside')`, `needs_inputs` (bool), `needs_inputs_text {en,fi,sv}|null`. With `needs_inputs` the card must not say withholding looks enough. `prefill.net_salary_cents` is now the same typical month as Me (`money_profile.typical_salary`), plus `net_salary_basis`, `net_salary_months`.
- `GET /api/goals`: each goal has `fit {status: 'fits'|'over'|'shared_over'|'unknown', monthly_need_cents, usually_left_cents, other_goals_monthly_cents, total_monthly_cents, gap_cents, suggested_monthly_cents, suggested_target_date, upfront_cents, monthly_after_upfront_cents, texts {en,fi,sv}|null}`.
- Category names: `scoach/labels.py CATEGORY_LABELS` is the one server table (forecast, catalogue, spender, agent tools); SV Restaurants = "Restauranger".

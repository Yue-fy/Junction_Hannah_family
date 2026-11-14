# S-Coach Data Pipeline

## Current state

The experience redesign adds a bounded semantic resolver and an interactive category-led interface. Status distinguishes verified supported cases from unrestricted question coverage and fresh browser acceptance. See [README known limitations](../README.md#known-limitations), [redesign plan](REDESIGN_PLAN.md), and [customer journeys](USER_TEST_JOURNEYS.md).

| Stage | Status | Evidence |
|---|---|---|
| Official CSV download | Complete | Four files under ignored `junction-dataset/` |
| Source validation | Complete | Headers, line counts, sizes and SHA-256 below |
| Demo SQLite schema | Complete | Immutable source tables, separate state, audit and pipeline metadata |
| Selected-persona import | Complete | Six customers plus linked mortgage rows in ignored demo database |
| Financial roles | Complete | Partner-aligned regular, irregular and everyday baskets plus income, transfers and review |
| Period analytics | Complete | Money Map, comparison, trends, unusual, salary and payday signals |
| Deterministic statistics | Verified supported definitions | Explicit consumption vs all outflows; exact totals/count/average/largest/net, MCC and consumption-only filters |
| Official brief questions | Supported with source limits | Dining/profile/safe-to-spend/restaurant tools; taxi uses MCC4121 with honest identified-record limits |
| Natural-language query scope | Bounded resolver implemented | Supported concepts, explicit/relative dates, validated follow-ups, unsupported qualifiers and missing context clarify |
| Corrections and scenarios | Complete | Immutable actuals, user rules, scenario-only exclusions, audit and undo |
| Goal plan | Complete | Universal goal templates, reserve, capacity and explicit scenario link |
| Cash-flow preview | Complete | Qualified recurrence, 30-day scenario, assumptions and historical backtest |
| Safe-to-spend scenario | Complete | History gate, EUR 500 sourced demo reserve, bills and flexible buffer |
| Investment-transfer view | Complete | Deposits, withdrawals, salary sweeps and contribution consistency only |
| Financing history | Complete | Optional linked home history; no approval or affordability inference |
| Tax evidence/planning | Complete | Explicit-source evidence and unsaved user-declared scenario only |
| VAT-inside-price lens | Complete | Date-aware MCC-first estimate, direct/broad/unmapped row provenance, versioned fact, period total and mapping coverage |
| JSON API | Complete | Validated read/mutation/tool routes plus static server |
| Adaptive localized UI | Redesigned; fresh browser acceptance pending | System fonts, balance hero, clear forecast, phone/tablet/desktop CSS and EN/FI/SV copy |
| Interactive spending ring | Implemented and integration-tested | Category/group/center/list parity, keyboard selection and source rows; six persona totals reconcile |
| Guided coach and evidence | Implemented and integration-tested | Home invitation, persistent Coach, conversation scope, same-period source rows, no visible hashes |
| First-use navigation | Implemented and integration-tested | Welcome invitation, skip/replay, actual category/Coach/preferences actions |
| Preferences and notebook | Implemented and integration-tested | Optional browser persistence, explicit proposals, edit/delete/revoke and session-only fallback |
| Journal and goal milestones | Implemented | Source-backed money moments, separate personal reflections and opt-in user-declared savings progress |
| Local device preview | Complete | Six unlinked development-only viewport presets |
| Integrated verification | Latest: 247 passed, one browser test skipped | 248 discovered; semantics/income/consent/real API-to-client evidence/HTTP/personalized handoff tests pass; rendered acceptance remains pending |

## Flow

```text
Official CSVs (ignored)
  -> BOM-aware streaming validation
  -> six selected synthetic personas
  -> normalized SQLite rows in integer cents
  -> immutable ledger + derived financial-literacy roles
  -> typed concept / metric / account / date resolution and clarification
  -> validated statistics / comparison / recurrence / unusual candidates
  -> exact account statistics / explicit tax evidence / estimated VAT lens
  -> user correction + scenario + goal audit state
  -> deterministic facts and candidate IDs
  -> optional Gemini selection/clarification over allowlisted facts
  -> JSON API
  -> category ring, Coach, readable evidence, scenario and goal views
  -> optional browser-local preferences + user-confirmed notes
  -> source-only money journal and optional goal milestones
```

## Source inventory

| File | Data rows | SHA-256 |
|---|---:|---|
| `tx_junction_transactions.csv` | 3,626,755 | `49b3265d8e44e751de305a074dcffcda732bb79aa1e07b46fcca774ce76f1e63` |
| `tx_customers_junction.csv` | 5,100 | `c2511f4f04f825f561d0c37ee4c64c83cdcd358b27b23c1b311f87a951bc8cb3` |
| `mtg_negotiation_history.csv` | 3,452 | `8b7a36a18642b20f72853b120928306db40eb487f9b346f273b7f57f182fd5cb` |
| `mtg_tx_customer_link_and_final_mtg_infio.csv` | 200 | `b68c88ddcd2de641b52ba2fe5942611ba60875677d75fe8670e469f19d23c990` |

## Selected personas

| Customer | Purpose |
|---|---|
| `CUST00001` | Exact restaurant comparison, clarification, scenario and goal handoff |
| `CUST00676` | Housing/payday timing and pattern-based cash-flow preview |
| `CUST05097` | Customer-relative unusual travel purchase |
| `CUST00756` | Positive salary change |
| `CUST00296` | Optional linked mortgage history and home-goal context |
| `CUST01331` | Age-18 payday timing, near-zero balance, and purchase-timing story |

## Invariants

- Store money as integer cents.
- Preserve raw source values and derived roles separately.
- Use source line number plus full-row SHA-256 for stable transaction references.
- Keep actuals, corrections, scenario exclusions and goal links separate.
- Treat investment deposits, withdrawals and salary sweeps as transfers, not consumption.
- Persist source checksum, import time, schema version, row counts and rejected rows.
- Never send raw CSVs, customer/account identifiers or a full ledger to Gemini.

## Build command

Run from the repository root, only when an imported database is not already available:

```bash
python3 "s bank/scripts/build_demo_db.py" \
  --source "s bank/junction-dataset" \
  --output "s bank/var/scoach.sqlite3"
```

For a rebuild, select an unused output filename and preserve the current database and user state. See [README](../README.md#quick-start) for startup, environment setup, health checks, tests, and troubleshooting. No dependency installation is required for the core runtime.

## Next validation stage

The semantic acceptance set and 40-turn customer guide now exist. Automated scope, exact-row parity, no-data, stale-response and notebook tests cover supported behavior. Next, run a fresh authorized phone/tablet/desktop browser walkthrough, replace the explicitly historical screenshots, exercise a configured live Gemini key, and conduct customer comprehension tests. No winner or measured usability claim follows from source review alone.


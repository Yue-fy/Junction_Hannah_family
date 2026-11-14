# S-Coach Data Pipeline

## Current state

Status below distinguishes implemented calculations from unresolved question interpretation. The later semantic audit supersedes earlier claims that every official example was complete. See [README known limitations](../README.md#known-limitations) and [technical documentation](TECHNICAL_DOCUMENTATION.md).

| Stage | Status | Evidence |
|---|---|---|
| Official CSV download | Complete | Four files under ignored `junction-dataset/` |
| Source validation | Complete | Headers, line counts, sizes and SHA-256 below |
| Demo SQLite schema | Complete | Immutable source tables, separate state, audit and pipeline metadata |
| Selected-persona import | Complete | Six customers plus linked mortgage rows in ignored demo database |
| Financial roles | Complete | Partner-aligned regular, irregular and everyday baskets plus income, transfers and review |
| Period analytics | Complete | Money Map, comparison, trends, unusual, salary and payday signals |
| Deterministic statistics | Implemented; semantic selection incomplete | Exact totals/count/average/largest/net for chosen filters; correct arithmetic does not establish intended scope |
| Official brief questions | Partial | Dining scenario, three-basket profile, safe-to-spend and restaurant total work; taxi incorrectly expands to Transportation |
| Natural-language query scope | Pending fixes | Narrow concepts/MCC, explicit dates, relative dates, and follow-up inheritance need semantic acceptance cases |
| Corrections and scenarios | Complete | Immutable actuals, user rules, scenario-only exclusions, audit and undo |
| Goal plan | Complete | Universal goal templates, reserve, capacity and explicit scenario link |
| Cash-flow preview | Complete | Qualified recurrence, 30-day scenario, assumptions and historical backtest |
| Safe-to-spend scenario | Complete | History gate, EUR 500 sourced demo reserve, bills and flexible buffer |
| Investment-transfer view | Complete | Deposits, withdrawals, salary sweeps and contribution consistency only |
| Financing history | Complete | Optional linked home history; no approval or affordability inference |
| Tax evidence/planning | Complete | Explicit-source evidence and unsaved user-declared scenario only |
| VAT-inside-price lens | Complete | Date-aware MCC-first estimate, direct/broad/unmapped row provenance, versioned fact, period total and mapping coverage |
| JSON API | Complete | Validated read/mutation/tool routes plus static server |
| Adaptive localized UI | Complete | Phone/tablet/desktop, EN/FI/SV, month/range controls and evidence views |
| Guided coach directory | Implemented; known gaps | Localized topics, tool results and tax planner; free-text scope and generic evidence consistency remain incomplete |
| Local device preview | Complete | Six unlinked development-only viewport presets |
| Integrated verification | Latest: 176 passed, one browser test skipped; semantic coverage incomplete | Earlier 177-test run included real Chrome device/locale flows; subsequent audits found defects not covered by those assertions |

## Flow

```text
Official CSVs (ignored)
  -> BOM-aware streaming validation
  -> six selected synthetic personas
  -> normalized SQLite rows in integer cents
  -> immutable ledger + derived financial-literacy roles
  -> comparison / trends / recurrence / unusual candidates
  -> exact account statistics / explicit tax evidence / estimated VAT lens
  -> user correction + scenario + goal audit state
  -> deterministic facts and candidate IDs
  -> optional Gemini selection/clarification over allowlisted facts
  -> JSON API
  -> adaptive localized Money Map, evidence, scenario and goal views
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

Create semantic acceptance questions with expected concept, account, date range, metric, selected rows, and either a supported answer or a clarification/unavailable response. Prioritize narrow-category resolution, question dates, follow-up context, and consistent scope from tool result to transaction list and calculation drawer. Do not promote this stage to complete merely because arithmetic tests pass.


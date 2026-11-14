# S-Coach Data Pipeline

## Current state

| Stage | Status | Evidence |
|---|---|---|
| Official CSV download | Complete | Four files under ignored `junction-dataset/` |
| Source validation | Complete | Headers, line counts, sizes and SHA-256 below |
| Demo SQLite schema | In progress | Implementation wave 1 |
| Selected-persona import | In progress | Streaming importer implementation |
| Financial roles | In progress | Deterministic classification implementation |
| Period analytics | In progress | Money Map/comparison/trend implementation |
| Corrections and scenarios | In progress | Immutable ledger plus audit implementation |
| Goal plan | In progress | Universal goal engine implementation |
| Cash-flow preview | In progress | Recurrence and 30-day scenario implementation |
| JSON API | In progress | Parallel implementation against locked contracts |
| Mobile UI | In progress | Parallel implementation against locked contracts |
| Integrated verification | Not started | Starts after wave 1 integration |
| Safe-to-spend scenario | Planned P1 | Requires integrated recurrence and reserve contracts |
| Investment-transfer view | Planned P1 | Uses investment deposits/withdrawals and salary sweeps only |

## Flow

```text
Official CSVs (ignored)
  -> BOM-aware streaming validation
  -> selected synthetic personas
  -> normalized SQLite rows in integer cents
  -> immutable ledger + derived financial-literacy roles
  -> comparison / trends / recurrence / unusual candidates
  -> user correction + scenario + goal audit state
  -> deterministic facts and candidate IDs
  -> optional Gemini selection/clarification over allowlisted facts
  -> JSON API
  -> mobile Money Map, evidence, scenario and goal views
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
| `CUST00676` | Housing/payday timing and confirmed cash-flow preview |
| `CUST05097` | Customer-relative unusual travel purchase |
| `CUST00756` | Positive salary change |
| `CUST00296` | Optional linked mortgage history and home-goal context |

## Invariants

- Store money as integer cents.
- Preserve raw source values and derived roles separately.
- Use source line number plus full-row SHA-256 for stable transaction references.
- Keep actuals, corrections, scenario exclusions and goal links separate.
- Treat investment deposits, withdrawals and salary sweeps as transfers, not consumption.
- Persist source checksum, import time, schema version, row counts and rejected rows.
- Never send raw CSVs, customer/account identifiers or a full ledger to Gemini.

## Build command

```bash
cd "s bank"
python3 scripts/build_demo_db.py --source junction-dataset --output var/scoach.sqlite3
```


# S-Coach Adaptive Financial Coach Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Status note (14 November 2026):** This file preserves the original TDD execution plan and its historical checkboxes. The implemented, current stage-by-stage status and verification evidence live in [`PIPELINE.md`](PIPELINE.md) and [`DEVELOPMENT_LOG.md`](DEVELOPMENT_LOG.md); unchecked boxes here do not mean the feature is absent.

**Goal:** Build a standalone, mobile-first but fully adaptive S-Pankki financial coach under `s bank/` with a deterministic ledger engine, plain-language visual overview, auditable correction/scenario loop, universal savings goal, Finnish/Swedish/English product localization, optional multilingual Gemini orchestration, and data-backed trend/forecast extensions.

**Architecture:** A standard-library Python package imports selected official synthetic customers into SQLite, performs all cents-based calculations, and serves JSON plus a static mobile web client. The UI renders deterministic API facts; Gemini may select verified candidates, request clarification, and phrase cited facts, but cannot calculate or mutate state without confirmation.

**Tech Stack:** Python 3.12 standard library, SQLite, `unittest`, semantic HTML, CSS, browser JavaScript, accessible SVG, optional Gemini REST API.

**Spec:** `s bank/docs/PROJECT_DESIGN.md`

## Global Constraints

- Keep all project code and docs under `s bank/`; do not modify `stoa/`, root `web/`, or captain-owned shared docs.
- Add no dependency without explicit user approval.
- Never commit the raw CSVs or generated SQLite database.
- Store money as integer cents and round percentage calculations half up.
- Keep observed facts, user corrections, and modeled scenarios separate in storage and API responses.
- The complete primary flow must work without Gemini credentials.
- Maintain `docs/DEVELOPMENT_LOG.md` and `docs/PIPELINE.md` after every milestone.

## Review Focus

- Duplicate timestamps and absent transaction IDs must still produce stable, distinct row references.
- Salary sweeps and investment transfers affect balance but never consumption or uncommitted goal capacity.
- Scenario exclusions must change only the adjustable base, never observed totals or trend history.
- Empty/partial periods, missing merchant/MCC values, and malformed user inputs must return useful empty or validation states.
- Gemini timeout, malformed JSON, unknown IDs/actions, or absent credentials must fall back without breaking the primary flow.

---

### Task 1: Reproducible demo data pipeline

**Files:**
- Create: `s bank/.gitignore`
- Create: `s bank/scoach/__init__.py`
- Create: `s bank/scoach/money.py`
- Create: `s bank/scoach/db.py`
- Create: `s bank/scripts/build_demo_db.py`
- Create: `s bank/tests/test_money.py`
- Create: `s bank/tests/test_pipeline.py`
- Create: `s bank/docs/PIPELINE.md`
- Create: `s bank/docs/DATA_DICTIONARY.md`

**Interfaces:**
- Produces: `euros_to_cents(str) -> int`, `cents_to_euros(int) -> str`, `percentile_cents(list[int], float) -> int`, `connect(path) -> sqlite3.Connection`, `initialize_schema(connection) -> None`, and CLI `python3 scripts/build_demo_db.py --source junction-dataset --output var/scoach.sqlite3`.
- Produces SQLite tables: `customers`, `transactions`, `mortgage_events`, `mortgage_final`, `user_rules`, `goals`, `scenarios`, `scenario_exclusions`, `audit_events`, and `pipeline_runs`.

- [ ] **Step 1: Write failing cents and schema/pipeline fixture tests.**

Assert BOM decoding, half-up cents parsing, deterministic percentile convention, distinct row refs for duplicate timestamps, selected-customer filtering, checksums/row counts in `pipeline_runs`, and no raw data copied into tracked paths.

- [ ] **Step 2: Run `python3 -m unittest tests.test_money tests.test_pipeline -v`; expect failures for missing modules.**

- [ ] **Step 3: Implement the minimal money helpers, schema, and streaming CSV importer.**

Use source line number plus SHA-256 full-row hash for `transaction_ref`. Import `CUST00001`, `CUST00676`, `CUST05097`, `CUST00756`, and `CUST00296` by default, including linked mortgage rows.

- [ ] **Step 4: Run the focused tests and build the real demo database; expect PASS and recorded source metadata.**

- [ ] **Step 5: Update pipeline/data dictionary docs and development log.**

### Task 2: Ledger, financial roles, comparison, trends, and Money Map

**Files:**
- Create: `s bank/scoach/classification.py`
- Create: `s bank/scoach/ledger.py`
- Create: `s bank/scoach/analytics.py`
- Create: `s bank/tests/test_classification.py`
- Create: `s bank/tests/test_analytics.py`

**Interfaces:**
- Consumes: Task 1 cents helpers and SQLite schema.
- Produces: `account_scope(conn, customer_id) -> dict`, `transactions(conn, customer_id, start, end, filters) -> list[dict]`, `month_summary(...) -> dict`, `money_map(...) -> dict`, `compare_periods(...) -> dict`, `trend_series(...) -> dict`, and `unusual_candidates(...) -> list[dict]`.

- [ ] **Step 1: Write failing tests for roles, transfer semantics, CUST00001 gold values, complete-period comparisons, empty selections, income separation, row evidence, and unusual cutoff boundaries.**

- [ ] **Step 2: Run focused tests and confirm expected failures.**

- [ ] **Step 3: Implement classification and ledger queries, then comparison/trend/Money Map results.**

Return fact IDs and transaction refs with each derived value. Use the exact literacy and unusual-item rules from the spec.

- [ ] **Step 4: Run focused tests against fixtures and the real demo database; expect all PASS including €115.43, €225.70, €110.27, €11.54, and €22.57.**

- [ ] **Step 5: Update development log and pipeline stage.**

### Task 3: Corrections, scenarios, audit/undo, and universal goals

**Files:**
- Create: `s bank/scoach/state.py`
- Create: `s bank/scoach/scenarios.py`
- Create: `s bank/scoach/goals.py`
- Create: `s bank/tests/test_state.py`
- Create: `s bank/tests/test_scenarios.py`
- Create: `s bank/tests/test_goals.py`

**Interfaces:**
- Consumes: transaction refs and fact IDs from Task 2.
- Produces: `classify_row(...)`, `create_matching_rule(...)`, `create_scenario(...)`, `exclude_from_scenario(...)`, `scenario_result(...)`, `undo_last(...)`, `reset_demo(...)`, `create_goal(...)`, `goal_plan(...)`, and `link_scenario_to_goal(...)`.

- [ ] **Step 1: Write failing tests proving immutable actuals, scenario-only exclusions, persistent audit provenance, append-only undo, reset, reserve protection, transfer exclusion, and invalid goal rejection.**

- [ ] **Step 2: Run focused tests and confirm expected failures.**

- [ ] **Step 3: Implement mutations in SQLite transactions and deterministic scenario/goal formulas.**

The headline 20% scenario must produce €45.14 before exclusion and €37.85 after excluding the €36.47 row while actual September stays €225.70.

- [ ] **Step 4: Run focused tests twice to verify persistence and reset determinism.**

- [ ] **Step 5: Update development log and pipeline stage.**

### Task 4: Recurrence and pattern-based cash-flow preview

**Files:**
- Create: `s bank/scoach/forecast.py`
- Create: `s bank/tests/test_forecast.py`

**Interfaces:**
- Consumes: Task 2 ledger roles and Task 3 user rules.
- Produces: `detect_recurring(...) -> list[dict]`, `preview_30_days(...) -> dict`, and `backtest_preview(...) -> dict`.

- [ ] **Step 1: Write failing tests for salary/housing recurrence, utilities envelope, fixed versus variable recurrence, investment-transfer treatment, observed/projected split, and scenario-band labels.**

- [ ] **Step 2: Run focused tests and confirm expected failures.**

- [ ] **Step 3: Implement the spec's cadence/median/MAD rules and a deterministic 30-day preview.**

- [ ] **Step 4: Run tests and a historical backtest; record error without converting it into confidence.**

- [ ] **Step 5: Update development log and pipeline docs.**

### Task 5: Coach candidate ranking and optional Gemini adapter

**Files:**
- Create: `s bank/scoach/coach.py`
- Create: `s bank/scoach/gemini.py`
- Create: `s bank/tests/test_coach.py`
- Create: `s bank/tests/test_gemini.py`
- Create: `s bank/.env.example`

**Interfaces:**
- Consumes: facts/candidates from Tasks 2–4 and goal/scenario actions from Task 3.
- Produces: `rank_candidates(candidates, goal=None) -> list[dict]`, `interpret(message, context, transport=None) -> CoachResponse`, and validated intents/actions defined by the spec.

- [ ] **Step 1: Write failing tests for deterministic ranking, headline prompt, missing parameters, fact/candidate allowlists, proposed-action confirmation, malformed JSON, timeout, and no-key fallback.**

- [ ] **Step 2: Run focused tests and confirm expected failures.**

- [x] **Step 3: Implement deterministic coach copy and a standard-library Gemini REST transport with a nine-second bounded fallback.**

- [ ] **Step 4: Run tests with fake transport only; live credentials are optional and never logged.**

- [ ] **Step 5: Update docs and development log.**

### Task 6: JSON API and static server

**Files:**
- Create: `s bank/scoach/api.py`
- Create: `s bank/scoach/__main__.py`
- Create: `s bank/tests/test_api.py`

**Interfaces:**
- Consumes: all service interfaces from Tasks 1–5.
- Produces endpoints: `GET /api/health`, `/api/personas`, `/api/overview`, `/api/comparison`, `/api/transactions`, `/api/trends`, `/api/forecast`, `/api/goals`; `POST /api/scenarios`, `/api/scenarios/exclude`, `/api/rules`, `/api/goals`, `/api/goals/link`, `/api/coach`, `/api/undo`, `/api/reset`; and static files at `/`.

- [ ] **Step 1: Write failing contract tests for success, validation, missing database, unknown persona/ref, immutable actuals, mutation audit response, and static path traversal rejection.**

- [ ] **Step 2: Run focused tests and confirm expected failures.**

- [ ] **Step 3: Implement a `ThreadingHTTPServer` router with JSON validation, consistent errors, and static serving.**

- [ ] **Step 4: Run API tests and smoke the server with the real demo database.**

- [ ] **Step 5: Update API and development documentation.**

### Task 7: Mobile-first visual client

**Files:**
- Create: `s bank/web/index.html`
- Create: `s bank/web/styles.css`
- Create: `s bank/web/app.js`
- Create: `s bank/web/api.js`
- Create: `s bank/web/charts.js`
- Create: `s bank/web/state.js`
- Create: `s bank/web/assets/` as needed for local, original assets only
- Create: `s bank/tests/test_web_contract.py`

**Interfaces:**
- Consumes: Task 6 API shapes.
- Produces the five-state primary flow plus Home, Trends, Goals, coach sheet, transaction drill-down, calculation drawer, persona switcher, forecast preview, undo/reset, loading/error/empty states, and responsive accessible SVG charts.

- [ ] **Step 1: Write failing static contract/accessibility tests for required landmarks, controls, dialog labels, non-color status labels, API endpoint references, and no external runtime dependency.**

- [ ] **Step 2: Run focused tests and confirm expected failures.**

- [ ] **Step 3: Implement semantic HTML shell, S-Pankki-inspired original styling, API state layer, and primary flow.**

- [ ] **Step 4: Implement Money Map, comparison, trend, runway and goal SVGs using the same filtered API rows/facts.**

- [ ] **Step 5: Verify keyboard, mobile viewport, loading/error/empty states, and calculation drawer; update development log.**

### Task 7A: Adaptive usability, localization, and period controls

**Files:**
- Modify: `s bank/web/index.html`
- Modify: `s bank/web/styles.css`
- Modify: `s bank/web/app.js`
- Modify: `s bank/web/charts.js`
- Modify: `s bank/web/state.js`
- Create: `s bank/web/i18n.js`
- Modify: `s bank/tests/test_web_contract.py`

**Interfaces:**
- Consumes: the existing month-aware API and deterministic UI state.
- Produces: a real desktop/tablet workspace rather than a framed phone preview; explicit month and trailing-range controls; complete Finnish, Swedish, and English interface strings; locale-aware EUR/date formatting; and simplified visual hierarchy for non-expert customers.

- [ ] **Step 1: Add failing browser/static tests for 390 px, 768 px, and 1280 px layouts, language persistence, translated core navigation, locale formatting, month changes, range changes, and stale-request rejection.**

- [ ] **Step 2: Replace the desktop marketing gutter with a wide content workspace while preserving a compact mobile experience.**

- [ ] **Step 3: Add a visible FI/SV/EN selector, browser-locale default, persistent user choice, and a locale field on coach requests.**

- [ ] **Step 4: Expose a month selector on Home and a trailing-period selector on Trends; reload all period-dependent facts from the same selected scope.**

- [ ] **Step 5: Replace ambiguous numbered flow segments and specialist language with labelled amounts, one-sentence interpretations, disclosure-on-demand assumptions, and accessible chart descriptions.**

- [ ] **Step 6: Run contract tests and browser QA at all three widths and in all three interface languages.**

### Task 7B: Safe-to-spend and investment cash-flow extensions

**Files:**
- Modify: `s bank/scoach/analytics.py`
- Modify: `s bank/scoach/forecast.py`
- Modify: `s bank/scoach/coach.py`
- Modify: `s bank/scoach/gemini.py`
- Modify: `s bank/scoach/api.py`
- Modify: focused tests under `s bank/tests/`

**Interfaces:**
- Produces an explainable safe-to-spend estimate with visible reserve, obligations, flexible-spend allowance, horizon, and assumptions. It is always labelled an estimate, never a guarantee.
- Produces observed investment contribution/withdrawal/salary-sweep cash flows only. It never implies holdings, return, risk, product suitability, or investment advice because those fields are absent from the challenge data.

- [ ] **Step 1: Write failing tests for insufficient history, reserve protection, future-obligation subtraction, integer-cent reconciliation, investment category semantics, withdrawals, and no-performance claims.**

- [ ] **Step 2: Implement deterministic functions and JSON endpoints with row/fact evidence.**

- [ ] **Step 3: Add allowlisted coach intents and deterministic fallback phrasing; Gemini may phrase only supplied verified values.**

- [ ] **Step 4: Run focused and full tests; document the data limits.**

### Task 7C: Guided coach directory and deterministic statistics tools

**Files:**
- Create: `s bank/scoach/statistics.py`
- Modify: `s bank/scoach/gemini.py`
- Modify: `s bank/scoach/coach.py`
- Modify: `s bank/scoach/api.py`
- Modify: `s bank/web/index.html`
- Modify: `s bank/web/app.js`
- Modify: `s bank/web/i18n.js`
- Add focused backend and browser tests.

**Interfaces:**
- Produces a visible topic directory for spending, cash flow, saving/investment transfers, goals/large purchases, financing, transaction statistics, and tax planning, with supported example questions under each topic.
- Produces deterministic account statistics scoped by validated customer, account, dates, and exact category/role/type/merchant filters. Gemini extracts a typed intent; code computes and cites every value.

- [ ] **Step 1: Write failing exact-statistics tests and guided-coach browser contracts.**
- [ ] **Step 2: Implement observed totals/count/average/largest/net/refs and complete-period comparison without model arithmetic.**
- [ ] **Step 3: Add allowlisted intent parameters and execute them server-side before generating any explanation.**
- [ ] **Step 4: Build the localized topic directory, suggested questions, unsupported-state copy, and free-text fallback.**
- [ ] **Step 5: Verify keyboard/screen-reader navigation and exact row-backed answers in EN/FI/SV.**

### Task 7D: Honest tax planning and device-preview QA

**Files:**
- Create: `s bank/scoach/tax.py`
- Modify: `s bank/scoach/api.py`
- Modify relevant web and test files.
- Create: `s bank/web/device-preview.html`

**Interfaces:**
- Observed tax evidence comes only from explicit source fields. User-entered amount/date planning remains a separate labelled scenario and never changes history or claims a tax liability.
- The local-only preview page embeds the real responsive app at representative phone/tablet widths; customers never see device simulation controls.

- [ ] **Step 1: Write failing tests for missing observed tax, an explicit recorded transfer tax, and exact user-declared set-aside math.**
- [ ] **Step 2: Add a localized tax-planning form with `You added this`, `Scenario`, and `Not tax advice` labels; do not infer tax rates.**
- [ ] **Step 3: Add a dependency-free device preview with small-phone, compact-phone, large-phone, tablet, and desktop presets.**
- [ ] **Step 4: Capture representative screenshots and verify the preview is not linked from production navigation.**

### Task 8: Documentation, full verification, and judge review

**Files:**
- Rewrite: `s bank/README.md`
- Create: `s bank/docs/DEVELOPMENT_LOG.md`
- Create: `s bank/docs/TECHNICAL_DOCUMENTATION.md`
- Create: `s bank/docs/API.md`
- Create: `s bank/docs/DEMO_SCRIPT.md`
- Update: `s bank/docs/PIPELINE.md`
- Update: `s bank/docs/DATA_DICTIONARY.md`

**Interfaces:**
- Consumes: completed application and verified commands.
- Produces a reproducible setup/run/test handoff and a 60–90 second demo script.

- [ ] **Step 1: Run `python3 -m unittest discover -s tests -v` from `s bank/`; fix every failure.**

- [ ] **Step 2: Rebuild the demo database from raw CSV and verify source checksums, row counts, CUST00001 gold values, and ignored generated files.**

- [ ] **Step 3: Run the server and walk the complete mobile flow in a browser, including offline Gemini fallback.**

- [ ] **Step 4: Ask independent agents to review code quality, data correctness, mobile UX, and score the result as an S-Pankki judge; repair high-impact findings.**

- [ ] **Step 5: Finish technical docs, pipeline status, development log, limitations, and demo script with only actually verified claims.**


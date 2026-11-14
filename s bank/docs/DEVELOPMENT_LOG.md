# S-Coach Development Log

This log records implementation progress, decisions, verification evidence, and blockers. Times use Europe/Helsinki.

## 2026-11-14

### Source and data acquisition

- Read the official challenge notes and confirmed the official Junction dataset repository.
- Downloaded all four CSVs into ignored `junction-dataset/`.
- Verified UTF-8 BOM headers, file sizes, line counts, and SHA-256 checksums.

### Data fitness and product design

- Profiled 3,626,755 transactions, 5,100 customers/accounts, 24 months of coverage, transaction categories/types, missing merchant/MCC coverage, and 200 linked mortgage applicants.
- Verified the exact `CUST00001` restaurant example from source rows.
- Reframed the product from fixed spending/mortgage paths to an adaptive financial home with one universal goal engine.
- Ruling: tax cannot be auto-detected from this dataset; it is a visibly user-declared obligation.
- Ruling: a 30-day runway is an editable scenario; a 90-day output cannot be presented as a precise prediction.

### Independent review and scope freeze

- Data-feasibility agent confirmed month/year changes, income shifts, customer-relative unusual items, recurrence, and 30-day previews are supportable.
- Product-review agent recommended one polished `inspect → clarify → simulate → goal` loop rather than several disconnected demos.
- Builder-check agents identified and resolved scope, standalone architecture, calculation, account/transfer, persistence, correction, and Gemini contract gaps.
- Judge agent scored the draft design 37/50 and rejected its oversized P0.
- Reduced P0 to a five-state, at-most-five-tap primary flow. Moved generalized trends/forecast/personas to P1 and financing context/calculators to P2.
- Added a proposed S-mobiili adapter boundary without claiming access to private APIs.

### Implementation wave 1

- User explicitly requested multi-agent implementation and judge-style evaluation.
- Created the TDD implementation plan and SDD recovery ledger.
- Baseline S-Coach test discovery found no tests because product code did not yet exist; this is the expected greenfield baseline, not a passing verification.
- Dispatched isolated file-ownership agents:
  - data/core: pipeline, cents math, SQLite, ledger, analytics, corrections, scenarios, goals, forecast;
  - API/coach: candidate ranking, Gemini adapter, HTTP API, static server;
  - mobile web: semantic responsive client, accessible SVGs, five-state flow and optional P1 surfaces.
- Ruling: agents may not commit or edit shared docs; the controller integrates and verifies the shared worktree.

### Partner brief reconciliation

- Read and visually inspected all five pages of the official S-Pankki PDF supplied from the Discord channel.
- Confirmed mobile-first delivery, freely explorable personal data, the three spending baskets, `safe to spend this week`, `safe to save`, optional open-data benchmarks, and optional PSD2 multi-bank scope.
- Added P1 plans for explainable safe-to-spend and long-term investment-transfer views.
- Ruling: postpone population benchmarks until a source with comparable definitions is available; synthetic age/postcode peer comparisons would be misleading.
- Ruling: investment transfers support habit and goal coaching only; the dataset cannot support performance, holdings, risk or product advice.

### Usability and localization review

- User testing on a desktop exposed that the 480 px phone-frame presentation was too small and wasted the available screen; the official brief is mobile-first, not mobile-only.
- Ruling: retain the compact mobile journey, but make tablet and desktop true adaptive workspaces with readable multi-column content rather than a decorative marketing gutter.
- Ruling: Finnish, Swedish, and English are first-class interface locales with complete deterministic product copy and locale-aware EUR/date formatting. Optional AI can mirror additional query languages, but it is not a substitute for translating navigation, forms, errors, accessibility labels, or offline responses.
- Ruling: Home gets an explicit month selector and Trends gets a trailing-period selector. Period changes must update all scoped facts together and reject stale responses.
- Ruling: simplify the Money Map into directly labelled amounts and plain explanations; advanced formulas and forecast assumptions stay available on demand.

### Guided coaching, precision questions, and brand alignment

- Follow-up testing found that a blank chatbot creates uncertainty for mainstream customers. Added a localized topic-directory requirement with concrete supported questions for spending, cash flow, saving/investment transfers, goals and large purchases, financing, transaction detail, and tax planning; free text remains optional.
- Ruling: fine-grained private-account answers must run through deterministic, scope-validated statistics tools. Gemini may select a typed operation and phrase its cited result, but it never calculates account totals itself.
- Ruling: observed tax exists only when an explicit source field identifies tax. Other tax planning is user-declared amount/date scenario data, visibly separate from history and not tax advice; no rates or liabilities are inferred.
- Reviewed current public S-Pankki/S-mobiili references. The prototype will align with their green/white, high-clarity, rounded and approachable visual language while keeping bright green selective. Official logo assets will not be copied; S-Coach uses an original mark.
- Ruling: actual responsive behavior remains the product. A local-only device-preview page may help developers compare representative phone, tablet, and desktop sizes without adding simulation controls to the customer UI.

### Captain review reconciliation

- Fetched and read `docs/CAPTAIN_REVIEW.md` from captain branch `Yue-fy/s-bank-review` at remote commit `71cec9f` without switching branches, merging, or overwriting the working tree. The review targets the older `c202ced` prototype, so every finding was rechecked against current code before action.
- Adopted the captain's submission-critical priorities: the five example questions from the partner brief, partner-consistent three-basket semantics, observable Gemini fallback, deterministic MyData exploration, and an estimated VAT-inside-purchases lens.
- Corrected the three-basket seed mapping: Housing, Utilities, Groceries, and Transportation are regular essentials; Health and Home & Tech are irregular essentials; Restaurants, Entertainment, Lifestyle, and Travel are everyday discretionary. User corrections remain possible.
- Recorded the resulting main-persona September map: EUR 1,266.90 regular essentials, EUR 0.00 irregular essentials, EUR 611.76 everyday discretionary, and EUR 235.72 saving/transfers. The older review figures must not be reused after the taxonomy correction.
- Implemented all five official questions as deterministic tools or scenarios. CUST00001 September Transportation is EUR 266.80 across six rows; the restaurant 20% read-only scenario is EUR 45.14; the profile uses the three baskets without a judgmental score; safe-to-spend remains supported; and the Finnish restaurant question returns EUR 225.70 across ten rows.
- Added a separate VAT lens using date-aware Finnish rates, MCC-first mapping, category fallback, integer cents, and half-up per-transaction rounding. For CUST00001 September, the implementation reproduces the captain's EUR 212.38 estimate over EUR 1,878.66 of spending.
- Independent VAT review separated observed source evidence from estimated value status, bound method/rate-map versions and row evidence into fact IDs, checked partial ranges against exact observed dates, added book/car-rental MCC handling, and left ambiguous transport/travel/health rows uncovered unless a supported MCC supplies a band. Captain gold values remain unchanged.
- Added `CUST01331` to the reproducible selected-persona set after a fresh temporary rebuild verified the captain's young-adult story: age 18, EUR 965.31 rent, EUR 236.44 Lifestyle purchase, EUR -11.82 balance before the EUR 1,874.62 salary, and a qualifying observed payday-timing signal. The prior ignored demo database was preserved as `var/scoach-before-young-persona.sqlite3`; the newly generated six-persona database is now the default `var/scoach.sqlite3`.
- Implemented the localized guided coach directory while retaining free text: spending/statistics, safe-to-spend/cash flow, saving/investment transfers, goals/large purchases, home/vehicle preparation, and tax/VAT. Exact tool results are rendered from server fields, while source/fallback diagnostics stay collapsed for the demo.
- Completed an independent UI review covering persona isolation, Swedish tax routing, period-aligned tax planning, non-restaurant scenario actions, language switching, and availability-gated mortgage history. The resulting focused web/localization/device suite passed 40 tests with one optional browser test skipped until the final walkthrough.
- Closed the final captain-audit gaps: the safe-to-spend official question now returns and renders the exact deterministic amount, assumptions, and evidence; offline free exploration recognizes all ten consumption categories in English, Finnish, and Swedish; VAT mapping quality and localized limitations are visible; and the health endpoint reports secret-free Gemini configuration status.
- Final verification ran 177 tests with zero failures. This included HTTP/static-boundary tests and a real headless-Chrome walkthrough at 320, 390, 768, 1280, and 1440 px in English, Finnish, and Swedish. The walkthrough covered scenario edit/undo, goal handoff, evidence, forecast assumptions, persona isolation, reset, empty/error states, keyboard Escape, and horizontal-overflow checks.
- JavaScript syntax checks, Python byte compilation, and whitespace checks passed. Temporary browser screenshots were inspected outside the repository. `GEMINI_API_KEY` is not configured on this machine, so live model service behavior is not claimed; fake-transport contract, privacy, timeout, default-model, and fallback paths are tested.
- Retained the optional mortgage and 30-day planning experiences because the user explicitly requested them. They are secondary paths, not the lead judge story, and make no approval claim.
- Ruling: no PR, push, platform submission, or video action is taken without the user's approval. No dependency or system-package change was made.

### Semantic audit and runbook reconciliation

- A subsequent read-only multi-agent audit found that precise arithmetic was being mistaken for correct question interpretation. The previous "all five official questions" completion claim is superseded: taxi currently expands to all Transportation, question dates can be ignored, and follow-up questions do not reliably inherit context.
- Confirmed an additional evidence consistency gap: generic non-restaurant drawers can reuse restaurant context, while model-selected periods can differ from the UI period used for matching rows.
- Rechecked the baseline Alex / September 2026 questions against the local API: restaurants EUR 225.70 across 10 rows, groceries EUR 379.79 across 5 rows, dining reduction EUR 45.14, and the seven-day safe-to-spend scenario EUR 3,288.31 with its stated assumptions. These are supported standalone examples, not unrestricted question coverage.
- Updated README startup commands to run from the repository root, reuse an existing imported database, and build only to a fresh output when needed. Added prerequisites, local URLs, phone/tablet/desktop preview instructions, shutdown, troubleshooting, and manual test questions.
- Documented that `.env` is not automatically loaded and that configuration presence is not proof of a working Gemini call. No live Gemini behavior is claimed.
- Reconciled the technical reference, API example, demo walkthrough, and pipeline status with the observed semantic limitations. The primary walkthrough now uses the verified restaurant question instead of presenting the Transportation total as taxi spending.
- The earlier 177-test pass remains historical evidence for those assertions. Three device-preview checks passed again during the preview handoff. This documentation update does not claim that the semantic defects have been fixed or that browser tests were rerun.
- Runbook verification: both root-relative CLI help commands succeeded; both existing pipeline tests passed; eight bash blocks across the six updated documents passed syntax checks; relative file links resolved; the existing six-persona SQLite database passed a read-only integrity check. Documentation whitespace checks passed.
- Next work: semantic gold questions and fixes for concept resolution, period interpretation, follow-up scope, and evidence consistency. No application code, dependencies, raw data, or saved demo state were changed by this documentation update.

### README interface gallery and branch publication

- The user explicitly authorized committing and pushing the latest S-Coach work to the existing `Erin-lab-design/s-bank` branch. No pull request or main-branch change was requested.
- Added four unchanged, visually inspected PNGs from the earlier browser walkthrough: phone, tablet, desktop overview, and desktop trends. The README embeds them with relative links and states their synthetic-data provenance and capture date.
- Fresh pre-push verification discovered 177 tests: 176 passed and the optional browser integration was skipped. HTTP tests ran successfully; no browser workaround or new live Gemini claim was used. JavaScript syntax, Python compilation, whitespace, local README links, and image integrity checks passed.
- An independent read-only review found no new publication blocker. Known question-scope and evidence limitations remain documented; raw CSVs, databases, and real environment values remain ignored.

### Experience redesign and customer-scope validation

- The user requested a substantial product/interaction redesign and explicitly authorized multi-agent work and iterative judge-style review. Added `REDESIGN_PLAN.md`, primary S-mobiili/Nordea/Monzo/Apple references and disjoint implementation ownership.
- Replaced the primary teaching-basket wall with a selectable consumption ring and familiar category icons, grouped exploration, selected-scope labels and source transaction navigation. Income, saving transfers and balance remain separate. Tested exact reconciliation for all six demo personas.
- Reworked typography, spacing, cards and adaptive layouts; added a prominent Home Coach invitation, persistent access, a first-use invitation and skippable/replayable tour with real actions. Replaced ambiguous forecast naming with a 30-day balance forecast and explicit ending/low estimates.
- Added session preferences and optional consented browser persistence, user-confirmed memory proposals, editable/deletable notes, revocation and storage-failure handling. Applied structured preferences to goal starters and protected-spending suggestions. Freeform notes remain personal reflections rather than model instructions.
- Added a source-backed money journal and opt-in goal milestones based on user-entered saved amounts. No inferred biography, investment risk score, spending reward or punitive streak is claimed.
- Removed visible transaction/fact hashes from customer evidence. Explanations show human-readable records and formulas on demand; internal references remain available for exact navigation and audit.
- Added local query scope before optional Gemini: concepts, metrics, dates, MCCs, consumption-only selection and validated follow-ups. Red-team tests caught and fixed stale restaurant scope on new-topic follow-ups, ignored qualifiers, `accounts` matching `count`, and mismatch between consumption totals and source rows.
- Added `USER_TEST_JOURNEYS.md` with eight customer journeys and 40 turns/actions, including expected clarification, scope, row evidence, consent and practical benefit. This is a validation guide, not a claim of measured customer success.
- Fresh integrated verification: 226 tests discovered, 225 passed, one optional browser test skipped. JavaScript syntax, Python compilation and whitespace checks passed. Earlier screenshots are now collapsed and explicitly marked as the previous interface.
- A final judge review asked for a stronger coherent personalization story. Added a Home Coach plan that protects the chosen category, previews an alternative discretionary change, and explicitly saves/links that scenario to the chosen goal template. EN/FI/SV scenario parsing and a trip-handoff regression now cover this path. Follow-up verification discovered 230 tests: 229 passed and one optional browser test skipped.
- Restarted the existing local demo at port 8088 using the existing database. No dependency, raw data, saved source database replacement, commit or push occurred during this redesign.
- Fresh rendered browser acceptance remains pending because saved browser-origin permissions still prevent automation. No alternate browser surface was used. Live Gemini remains unconfigured and unverified.

### Completion audit and conversation refinements

- Audited the original experience requirements against current source, tests, runtime and artifacts in `ACCEPTANCE_STATUS.md`. Rendered acceptance remains an open gate; historical screenshots and minimal-DOM assertions are not substituted for it.
- Found and fixed a journal/conversation mismatch: a purchase-motive question could select Lifestyle statistics. Emotional, medical and biographical inference now returns a source-limit explanation and a user-reflection path without an unrelated amount.
- Added observed salary/income/all-credit distinctions and `inflow_total`, including positive-only evidence references. Gross-pay/tax-rate and unsupported income metrics ask for a supported definition rather than silently changing the question.
- Added supported next actions for missing purchase context and executable clarification choices. Monetary thresholds and merchant-name qualifiers now clarify rather than disappearing from a broader category sum.
- Explicit preference declarations can create local, unconfirmed proposals without an irrelevant bank query or model call. Opening a goal form does not grant memory consent. Direct/gentle styles change presentation order while preserving amounts and uncertainty.
- Preserved the requested metric through matching transactions and calculation drawers. A real API-to-client bridge test checks August restaurant average and salary credits against source evidence; average explanations use the verified denominator and never display division by zero.
- Restored optional language-adapter routing for locally unrecognized phrasing while keeping known data limitations local. Controlled model tests verify correct credited-income direction and exclude investment withdrawals from earned-income claims. No live Gemini call is claimed.
- Latest full verification: 248 tests discovered, 247 passed and one browser test skipped; final output had no warnings. Client syntax, Python compilation and whitespace checks passed. Restarted the existing local service with the same database.
- No browser bypass, dependency installation, database replacement, commit or push occurred. Fresh browser/device acceptance and current screenshots still require restored tool access or human-rendered evidence.

### Harness portability patch integration

- After the user confirmed the parallel redesign work had finished, applied the independently prepared harness patch against the latest working tree. The large module script now reaches Node through stdin instead of a single command-line argument.
- Added `test_harness_portability.py`. Its regression executes the real Node harness with a simulated 128 KiB per-argument boundary; it failed before the fix and passed afterward. This is not a fresh Linux-host run.
- Fresh full verification discovered 249 tests: 248 passed, one optional browser integration skipped. HTTP tests passed with permission to bind local test ports. JavaScript syntax, Python parsing and whitespace checks passed.
- Checked the running loopback service: health, all six persona overviews, trends, forecast, safe-to-spend, investments, VAT and goals returned successful JSON. An offline three-turn restaurant-to-groceries/month follow-up returned EUR 115.43, EUR 442.26 and EUR 379.79 with the expected periods.
- Separately reconfirmed three existing semantic gaps that the current suite does not catch: a 12.5% adjustment is interpreted as 5%; a spelled-out percentage routes to statistics; and a VAT chat question does not reach the estimate. These gaps were not changed by this test-harness patch.
- Fresh rendered browser acceptance and live Gemini remain unverified. The existing demo database and running service were reused; no dependency installation was needed.

### Complete percentage parsing and VAT chat fixes

- Added failing public-API regressions before implementation for decimal/word percentages, invalid and ambiguous expressions, localized VAT questions, exact date scope, tax-liability limits and optional model tool selection. Added client regressions before rendering the new VAT answer card.
- Replaced integer-only suffix matching with complete percentage parsing. Supported numeric values and common EN/FI/SV number words retain their exact value; missing, negative, out-of-range, malformed, ranged or multiple proportions ask for clarification instead of becoming another statistic. Financial adjustment parsing stays local.
- Connected VAT questions to the existing VAT lens through the existing coach envelope. Localized terms and the optional adapter select the bounded tool; Python supplies every amount and source. The answer labels the estimate, exact dates, mapping coverage and uncovered spending, and keeps formulas and readable evidence collapsed. No new public endpoint or request field was introduced.
- Confirmed Alex / September: 12.5% dining reduction is EUR 28.21, twenty percent is EUR 45.14, and estimated VAT is EUR 212.38. Explicit tax evidence remains separate; no liability, additional payment or refund is inferred.
- Full verification discovered 261 tests: 260 passed and one optional browser integration skipped. HTTP tests, JavaScript syntax, Python syntax and whitespace checks passed. Fresh browser-device acceptance and a real Gemini call remain outside this verification.

### Coach agent backend — WP1 (2026-11-14)

- Added `/api/agent`, provider configuration health and startup loading of the ignored local `.env`. The user requested switching live inference to DeepSeek during implementation; the configurable standard-library adapter prefers `DEEPSEEK_API_KEY` / `DEEPSEEK_MODEL` and retains the optional Gemini transport. No SDK dependency was added. The existing `/api/coach` implementation and browser path are unchanged.
- Added fifteen strictly validated read-only tools over the existing statistics, analytics, ledger, forecast, scenario and goal services. Tool results include periods, basis, cents and display values. Raw identifiers and references stay local; evidence queries let the client reopen the supporting transactions. Proposals require a matching preview and never save or move money.
- Bounded the loop to six model turns, twenty tool calls and twenty-five seconds, with a deterministic legacy envelope on missing configuration, provider failure, timeout, exhausted steps or repeated numeric-verification failure. Gemini thought signatures and call IDs survive replay; DeepSeek assistant/tool messages preserve call IDs and any provider reasoning internally.
- Added direct EN/FI/SV numeric provenance tests and temporary-database tool/API regressions. The check accepts sourced calculations and customer figures; it cannot prove the semantic meaning of a sentence. Model-authored names/labels are not numerical evidence, goal inputs must be sourced, and compact/scientific monetary notation cannot silently escape verification.
- Independent read-only review found four important issues: compact notation bypass, model-input provenance laundering, API display decoration breaking goal-action payloads, and overly broad identifier redaction. Reproducing tests were added before fixes. Two additional findings were treated as important because they affect money calculations: selected historical months now use their last observed day, and the calculator accepts sourced negative amounts. No review finding was left deferred.
- Implementation decisions: continue on the supplied feature branch; document this separate S-Coach API in `docs/API.md`; keep nonempty history explicitly unsupported until WP2; isolate number checking in `agent_numbers.py`; retain up to twenty-four chart points while ordinary lists cap at twenty with declared truncation; use the existing calendar-month helper and ceiling formula for unsaved goal arithmetic, with no affordability claim. Existing user edits to `.env.example` and the root implementation brief are excluded from the package commit.
- Live verification used only a fresh synthetic fixture. `deepseek-flash` returned `source: agent` for restaurant totals (EUR 225.70, 2.85 seconds, two model calls) and a 20% reduction (EUR 45.14 monthly / EUR 541.68 annually, 2.47 seconds, two model calls). These are two smoke checks, not a full conversational evaluation. The earlier Gemini request returned HTTP 402 with exhausted project prepayment credits and correctly fell back. No secret values were logged or committed.
- WP2 memory and WP6 mobile UI remain pending the user's per-package confirmation. The existing website still calls `/api/coach`; the new backend is available directly through `/api/agent`.
- Final WP1 verification: 400 tests discovered, 399 passed and one optional browser integration skipped (16.119 seconds). All S-Coach JavaScript and Python syntax checks passed; whitespace checks passed. There are 39 new tests, and no existing test was removed or weakened.

### Coach agent conversation memory — WP2 (2026-11-14)

- Added strict history validation at the existing API body boundary: at most eight `{role, text}` messages, `user` / `coach` roles only, nonblank text up to 600 Unicode characters, and no extra fields. The agent replays sanitized text before the latest message; previous tool calls/results are not accepted or retained between requests.
- Added the frontend `createAPI.agent` request helper. It extracts visible text from the matching customer/month/language, retains the most recent eight messages and clips at Unicode code-point boundaries without truncating the on-screen conversation. Structured tool output and metadata never enter this payload. Existing new-question and scope-change reset paths were exercised through the real client harness.
- Added a 40-second agent request timeout alongside the unchanged 10-second default for other API calls, plus optional per-call timeout overrides. The endpoint switch and renderer remain in WP6, as assigned by the implementation brief; the existing page does not yet call the new helper.
- Seven new regressions cover consecutive public API requests, provider role mapping, fresh evidence, history-number recognition, redaction, malformed/oversized payloads, Unicode limits, scoped client serialization, reset behavior and timer cleanup. Full regression: 407 tests discovered, 406 passed, one optional browser integration skipped (16.293 seconds). No existing test was removed or weakened.
- Independent read-only review found no Critical, Important or actionable Minor issues. It did not substitute for live-provider testing or the separate full-suite run. WP6 page integration and broader follow-up quality remain outside this package's acceptance.
- Live DeepSeek verification used a fresh temporary synthetic ledger. A restaurant question returned EUR 225.70 in 2.49 seconds; the follow-up "What about groceries then?" sent the prior two text messages, queried groceries for the same September period and returned EUR 100.00 in 2.97 seconds. Both responses had `source: agent` with fresh category evidence. This is one two-turn smoke check, not a general conversational evaluation. Python, JavaScript and whitespace checks also passed.

## Current status

- Product design: frozen for implementation.
- Raw data: downloaded, ignored, verified.
- P0 code: redesigned; supported semantic scopes and integrated interaction checks pass.
- P1 code: safe-to-spend, observed investment-cash-flow, goals, forecast, VAT, and selected financing context are implemented and verified.
- Adaptive/localized UI: new responsive structure and interaction tests pass; fresh rendered phone/tablet/desktop acceptance pending.
- Live agent: DeepSeek synthetic amount, scenario and two-turn follow-up checks passed; Gemini generation is quota-blocked. Broader evaluation and web integration remain pending; deterministic fallback supports the existing bounded questions.
- Runbook and technical reference: reconciled with redesigned behavior, supported definitions and remaining bounds.
- Dependencies added: none.
- Publication scope: one local commit per work package, then pause for user confirmation. No new push or PR was requested.


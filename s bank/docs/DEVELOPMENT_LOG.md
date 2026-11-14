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

## Current status

- Product design: frozen for implementation.
- Raw data: downloaded, ignored, verified.
- P0 code: implemented; earlier integration suite passed, but semantic acceptance is incomplete.
- P1 code: safe-to-spend, observed investment-cash-flow, goals, forecast, VAT, and selected financing context are implemented and verified.
- Adaptive/localized UI: earlier real-browser phone/tablet/desktop and EN/FI/SV walkthrough passed; generic evidence scope gaps remain.
- Optional live Gemini call: pending a configured Junction key; deterministic fallback supports bounded questions with the documented limitations.
- Runbook and technical reference: reconciled with current startup commands and known defects.
- Dependencies added: none.
- Publication scope: user-authorized commit and push to `Erin-lab-design/s-bank`; no PR or main-branch update requested.


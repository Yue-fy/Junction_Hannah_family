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

## Current status

- Product design: frozen for implementation.
- Raw data: downloaded, ignored, verified.
- P0 code: implemented; integration fixes and independent review are in progress.
- P1 code: safe-to-spend and observed investment-cash-flow extensions are in progress after the P0 test suite turned green.
- Adaptive/localized UI: in progress following desktop and comprehension feedback.
- Dependencies added: none.
- External writes, commits, pushes, or PRs: none.


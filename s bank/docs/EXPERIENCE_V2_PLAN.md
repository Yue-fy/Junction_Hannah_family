# S-Coach customer experience implementation plan

> For agentic workers: use the subagent-driven-development workflow with disjoint file ownership, followed by independent review. Preserve all pre-existing changes. The user authorized implementation and parallel agents after reviewing the product direction in conversation.

**Goal:** Turn an overcrowded dashboard and modal coach into a coherent mobile-first journey: understand, ask, inspect evidence, compare a scenario, and choose a goal at the user's own pace.

**Architecture:** Keep the existing Python/SQLite calculations and dependency-free browser application. Four primary pages reuse the current endpoints. The main integrator owns HTML and application wiring; bounded workers own CSS/charts, browser-local aspirations, and query correctness. No endpoint, environment-variable, or server schema changes.

**Tech stack:** Python standard library, SQLite, HTML, CSS, native ES modules; existing unittest/Node harness.

**Spec:** The accepted product direction in the conversation plus the design decisions below. Existing `REDESIGN_PLAN.md` documents the prior implementation; this plan supersedes its information hierarchy only.

## Global constraints

- Work only in `s bank/`. Do not commit, push, delete data, install dependencies, or change the root Stoa application.
- Preserve existing uncommitted work. A source baseline is saved in `/tmp/scoach-v2-baseline` for review.
- All project content is English with EN/FI/SV customer copy retained.
- Primary pages: Home, Spending, Coach, Goals. Journal and notebook remain accessible as secondary tools.
- Every question button submits a question and produces an answer, clarification, or recoverable error.
- Every financial amount comes from the selected data or explicit user input. Scenarios are not saved or executed merely by reading them.
- A wish requires only a title. Numeric plans remain optional and use the existing goals endpoint when the user supplies required calculation inputs.
- Raw challenge data, database, secrets, dependencies, and external service configuration remain untouched.
- Browser verification must use approved CUA access. Never bypass a denied browser-origin permission with another surface, Playwright, CDP, proxy, or origin.

## Approaches and selected design

1. Cosmetic repair alone would leave the missing-answer and mandatory-goal problems unresolved.
2. Rebuilding the backend/framework would discard working scoped calculations and add unnecessary integration risk.
3. **Selected:** restructure the customer experience around the existing verified calculation tools, retaining evidence, consent, and supported language boundaries.

Home has a recorded-balance summary, one useful coaching action and a compact three-basket overview. Spending has the sole category ring, aligned category rows, selected-category details, and optional trends/tax/investment/forecast details. Coach is a complete page with readable turns, context, starter questions, inline results, and an always reachable composer. Goals begins with a wish and only opens a numeric planner when requested. Demo stories explicitly distinguish source facts from hypothetical aspirations.

## Review focus

- SVG ring arcs and track must share one coordinate system; CSS transform-origin must not offset SVG rotations.
- A requested 10%, 12.5%, or 30% scenario must preserve that percentage and period when saved.
- Changing persona, month, or language must invalidate stale answers and prevent cross-customer drafts.
- Optional wishes must survive navigation, obey persistence consent, and never imply actual saved money.
- At 320/390/768/1440 CSS pixels, content must wrap, tap targets remain usable, and the composer must not collide with navigation.

## Task 1: Query correctness

Files: `scoach/coach.py`, `scoach/query_scope.py`, scoped new query regression tests only.

- [x] Reproduce the exact existing chip `How much could I save by reducing dining out by 20%?`; assert spending_adjustment_preview and the computed 20% contribution.
- [x] Support bounded reduction inflections without dropping qualifiers or invalid percentages.
- [x] Reproduce `What changed in restaurants in August 2026?` with September selected. Use the explicit period or return clarification; never silently compare September.
- [x] Test the changed cases plus current query-scope/conversation suites. No API contract change.

## Task 2: Optional aspirations

Files: `web/experience.js`, `tests/test_aspirations.py`.

Interface: extend `createExperienceStore` with `load().wishes`, `addWish({title, template?, contribution_cents?})`, `updateWish(id, patch)`, `deleteWish(id)`. A wish is `{id,title,template,contribution_cents,created_at}`; templates use existing goal values; contribution defaults to null. Amount/date are not required. IDs are generated locally, all strings normalized, cents must be nonnegative safe integers or null. Existing `save()` must not inject wishes. Existing consent/revoke/forget behavior applies. Preserve existing profiles and notes.

- [x] Test title-only saving, empty/invalid input, persona isolation, no writes without consent, consent persistence/revoke, and corrupt stored wishes.
- [x] Implement bounded wish storage and verify existing experience tests.

## Task 3: Unified responsive design

Files: `web/styles.css`, optionally `web/charts.js` only for ring geometry or accessible chart rendering.

DOM contract: existing IDs stay except `coach-dialog` becomes `coach-view`. New hooks: `.app-context`, `.context-caption`, `#home-baskets`, `.basket-summary`, `#home-goal-summary`, `.home-summary-grid`, `#spending-card`, `.spending-layout`, `.spending-detail`, `.analysis-details`, `#coach-view`, `.coach-layout`, `.coach-main`, `.coach-context`, `.coach-starters`, `.coach-composer`, `#coach-scope`, `#coach-empty`, `#coach-live-status`, `.wish-card`, `#wish-form`, `#wishes-list`, `#goal-planner`, `.goal-workspace`, `.demo-stories`, `.demo-story`.

- [x] Fix the ring coordinate mismatch: track and arcs use one viewBox; do not combine CSS centered transform-origin with SVG centered rotation.
- [x] Home uses compact purposeful rows; Spending places the one ring beside category rows on desktop and above them on mobile.
- [x] Four-item bottom navigation on phones, horizontal navigation on desktop. Coach composer stays reachable without overlap; normal text remains readable.
- [x] Eliminate obsolete grid-row assignments and constrain chart width. Do not hide defects with global overflow clipping.
- [x] Validate CSS/source contracts; rendered acceptance remains a separate CUA check.

## Task 4: Page and coaching integration

Files: `web/index.html`, `web/app.js`, `web/state.js` if needed, integration tests.

- [x] Move the spending explorer to Spending; replace default dining comparison with selected-category exploration; make tax/investment/forecast detail on-demand.
- [x] Promote Coach to a navigable page. Preserve transcript during navigation; show sending/error state and retry. Suggested questions must call askCoach.
- [x] Render forecast, investments, and mortgage history inline using existing GET endpoints; use the returned scope and existing evidence drilldown.
- [x] Render scenarios visually and save their exact category/percentage/period only after the user selects the action. Remove default-Alex 20% handoff substitution.
- [x] Integrate title-only wishes and optional numeric planning; explain session-only vs browser persistence.
- [x] Provide three guided demo stories: Kai spending runway, Alex category/scenario exploration, Taylor historical home-financing context plus a user-selected savings wish. No inferred family or mortgage repayment claims.

## Task 5: Verification and handoff

- [x] Run focused tests, then the full suite and JavaScript syntax checks. Final run: 306 discovered, 305 passed, one optional browser test skipped.
- [x] Independent source review: customer benefit, query/hand-off correctness, localization, accessibility and data honesty. Three Important findings were repaired and independently rechecked; no remaining Critical/Important source findings.
- [ ] With restored origin approval, personally use CUA on desktop and through the existing device-preview page at phone/tablet sizes; test actual questions, follow-ups, percentages, vague wishes, evidence and error states.
- [x] Record only observed results. Update the demo script and acceptance report; mark any browser limitation explicitly.
- [x] Deliver local URL, key changes, verification evidence and any remaining gaps. Commit/PR only through the user's separate Ship workflow.

**Rendered verification status:** the browser tool denied the local origin. The user elected to inspect the app and device preview manually; automated desktop/mobile acceptance remains unchecked. No alternate route was used. The local app remains running for that inspection.

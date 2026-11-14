# S-Coach experience redesign

## Objective and acceptance

Make the existing prototype compelling to a Junction judge and understandable to a young adult in one minute: know where money went, understand one useful next action, explore a scenario, and connect it to a personally meaningful goal. No claim of winning, suitability assessment, or inferred life story is made.

The user authorized implementation choices and parallel agents. Work stays in `s bank/`, preserves existing data and state, and adds no dependency. The existing branch and standalone API remain the integration boundary.

## Design decisions

- A calm green identity, generous spacing, system fonts, expressive but restrained category colors, and clear touch targets. Familiar categories lead; the partner's three teaching baskets remain a secondary explanation.
- Home prioritizes balance, an interactive spending ring, one personalized coaching action, and an explicitly labelled 30-day balance forecast. Income and saving transfers are separate from consumption so the ring is mathematically meaningful.
- Ring segments and category buttons share one selection state and open the same period-scoped transactions. Keyboard buttons provide an equivalent interaction; color is never the only label.
- Coach has a prominent Home invitation and persistent access. A short, skippable, repeatable first-use tour teaches by action.
- Personalization asks about what the user wants to make room for, coaching style, and spending they wish to protect. It does not pretend a short quiz establishes investment risk suitability.
- An optional notebook stores only user-confirmed preferences on this browser, separately by demo persona. Users can inspect, edit, delete, and revoke consent. Conversation text is not silently retained. Declining keeps a useful session-only experience.
- A money journal reports dated, inspectable financial facts and optional user-authored reflections. It never invents travel, employment changes, emotional states, or a biography from category labels.
- Optional goal milestones encourage progress without spending rewards, punitive streaks, shame, loss framing, or fabricated achievement.
- Explanations use progressive disclosure: a plain summary first, then selected rows and understandable assumptions. Hashes remain internal identifiers; normal customer screens do not render them.

## Question and evidence contract

The coach resolves concept, metric, account, dates, and reference date before executing a tool. Unsupported detail or missing scope produces a bounded clarification/unavailable answer. Narrow concepts such as taxi must not widen to all Transportation. Follow-ups can carry a validated previous query but cannot carry another customer's scope. The returned period and filters control matching rows and calculations.

The local API documentation is updated alongside additive scope fields. Existing endpoints and environment names are preserved. Model arithmetic and unsupported financial claims remain disallowed.

## Implementation ownership

1. Backend agent: semantic resolver, date/follow-up behavior, API validation and scoped statistics; independent multi-turn acceptance tests.
2. Interface agent: HTML, CSS and chart components; responsive layout, interactive category ring and accessible navigation.
3. Personalization agent: browser notebook/preferences/onboarding helpers, storage/consent tests, and usability research notes.
4. Controller: shared `app.js` integration, localization, customer-facing evidence, journal and milestone wiring, documentation and final verification.

Agents own disjoint files. The controller reviews the integrated result and requests an independent judge/usability review after implementation.

## Verification and iteration

- Meaningful semantic cases cover exact category, narrow MCC concept, explicit month, relative month, arbitrary range, vague affordability, missing data, follow-ups, changing account, refusals, and tool-to-evidence scope.
- UI checks cover ring/list parity, empty categories, source transactions without hashes, keyboard operation, first-use skip/replay, notebook consent/edit/delete/persona isolation, optional milestones, locale changes and stale responses.
- Run the existing Python/JS suite. Browser execution remains subject to the previously saved local-origin restriction; do not evade it using another surface. Report historical versus current browser evidence separately.
- Update README, pipeline, API and development log with actual implementation and current limits. Refresh screenshots only when authorized browser access is available; label historical images accurately.

## Research sources and interpretation

- [S-mobiili](https://www.s-pankki.fi/fi/verkkopalvelut/s-mobiili/): bank services, saving and investment access within the existing S ecosystem. Adopt familiar green/white hierarchy, not protected assets.
- [Nordea finance tools](https://www.nordea.fi/en/personal/our-services/online-mobile-services/mobile-banking/managing-your-finances.html): selectable period/account scope, category-to-subcategory-to-transaction exploration and correction.
- [Monzo Trends](https://monzo.com/help/budgeting-overdrafts-savings/web-the-differences-between-Summary-and-Trends): category/merchant views and interactive spending targets.
- [Apple onboarding](https://developer.apple.com/design/human-interface-guidelines/onboarding): short, optional, contextual and interactive guidance.
- [Apple charts](https://developer.apple.com/design/human-interface-guidelines/charts): readable charts with understandable context and equivalent access to information.

These are design references, not usability evidence for this prototype. Cognitive-load reduction, recognition through familiar categories, user autonomy, and nonjudgmental wording are hypotheses to validate through the question journey and usability checklist, not asserted psychological treatment effects.

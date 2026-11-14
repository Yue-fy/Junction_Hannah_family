# Redesign completion audit

**Earlier redesign record:** this page preserves the first redesign audit. The current four-page experience, title-only wishes, integration result and outstanding checks are recorded in [EXPERIENCE_V2_ACCEPTANCE.md](EXPERIENCE_V2_ACCEPTANCE.md). V2 discovered 306 tests: 305 passed and one optional browser test was skipped. Neither record claims current rendered acceptance or live Gemini verification.

This audit distinguishes implementation evidence from rendered acceptance. A green calculation or minimal-DOM test cannot prove actual visual quality, native focus behavior, or customer understanding. The full redesign is not declared complete while rendered acceptance is missing.

## Requirement-to-evidence map

| Requested outcome | Authoritative evidence | Current conclusion |
|---|---|---|
| Build on the existing project and preserve work | Git status is limited to `s bank/`; existing database reused; no dependency, system-package, raw-data replacement or main-branch change | Implemented |
| Ground the design in S-Bank, comparable banks and Apple UI guidance | Primary references and decisions in `REDESIGN_PLAN.md`; system fonts, green identity and progressive disclosure in `web/index.html` / `styles.css` | Research and implementation present; perceived quality needs rendered review |
| Understandable phone, tablet and desktop layouts | Responsive stylesheet, semantic landmark checks in `test_redesign_visual.py`, device-preview presets | Structure checked; current 320/390/768/1280/1440 px rendering is not yet verified |
| Interactive category overview with clear grouping | `spendingRing`, `spendingCategories`, selected-center/group parity and error-vs-zero checks in `test_redesign_integration.py`; six real-persona totals reconcile | Calculation and client interaction evidence present; native touch/focus/overflow pending |
| Prominent Coach and first-use navigation | Home Coach/persistent access; welcome, skip/replay and real tour actions in `test_first_visit_tour_offers_a_real_category_action_and_can_be_skipped` | Logic checked; first-screen visibility and native scrolling pending |
| Meaningful personalization | Protected-category alternatives, chosen goal template, confirmed scenario handoff, and unchanged source facts in integration tests | Implemented; human benefit not measured |
| Consent-based editable memory | `test_experience.py` covers opt-in, session-only mode, editing/deletion, revocation, corrupt/denied storage, failure reporting and persona isolation | Implemented and contract-tested; native form interaction pending |
| Context-aware, data-grounded coaching | `test_query_scope.py` / `test_conversation.py`: definitions, dates, MCCs, follow-ups, unsupported qualifiers, missing context and exact row parity | Supported cases verified; unrestricted language and live provider behavior are not claimed |
| No inferred motivation or life story | Source-only journal tests; emotional/motive questions require a data-limit response | Journal boundary implemented; direct conversational boundary is audited with regressions |
| Readable transparency without visible hashes | `test_customer_visible_evidence_uses_rows_without_hash_text`; source records remain accessible through internal references | Logic/markup checked; rendered information density pending |
| Clear forecast and optional playful goals | Named 30-day balance forecast, ending/lowest estimates, opt-in milestones tied to entered saved amounts | Implemented; understanding and emotional response need human testing |
| Multi-agent implementation and independent evaluation | Disjoint implementation ownership and follow-up red-team / judge reviews recorded in `DEVELOPMENT_LOG.md` | Performed; source review is not a user study |
| Full documentation and repeatable workflow | README, API, pipeline, technical reference, demo script, development log and 40-turn customer guide | Present; historical screenshots are explicitly labelled |

## Current blocking gate

The browser tool previously rejected the local demo origin because of a saved permission setting and expressly disallowed alternate browser surfaces, proxies, indirect commands or equivalent bypasses. No such bypass is used. The user can manually open the running demo, but that does not establish an automated rendered walkthrough.

To close this gate, browser-tool access to the local origin must be restored, or a human must provide current rendered acceptance evidence. Required checks include narrow-screen EN/FI/SV readability, chart hit targets, native keyboard focus, dialog scrolling, first-use guidance, notebook editing/revocation and the complete personalized scenario-to-goal path. Only then can current screenshots replace the historical gallery.

## Verification record

The latest full run discovered 261 tests: 260 passed and one optional browser integration was skipped. HTTP tests passed with local-port access. Decimal/word percentages now keep their complete value, invalid or ambiguous proportions ask for clarification, and EN/FI/SV VAT questions reach the existing date-scoped estimate. Client integration checks mount a real VAT response with its approximate amount, period, coverage and human-readable evidence; fully unmapped spending is not presented as zero VAT. A controlled language-adapter test selects the VAT tool without a live provider call. The portability regression executes the real Node harness under a simulated per-argument size limit; it is not a fresh Linux-host run. The existing local server and database are independent of the minimal-DOM harness. Gemini remains optional and unconfigured on this machine.

The previously reproduced decimal-percentage, spelled-out-percentage and VAT-chat gaps are covered by failing-before/fixed-after regressions. These checks cover bounded supported expressions, not arbitrary-language understanding. Whole-period VAT is supported; category-specific VAT and tax liabilities require clarification. Rendered acceptance remains pending as described above.

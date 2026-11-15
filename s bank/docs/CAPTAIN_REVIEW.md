# Captain review: S-Coach prototype

## Round 2 · commit `1e65b45`, Saturday 14 November 2026, 18:00

Final submission is due on **Sunday 15 November at 10:00**.

**Summary.** Big step forward:

- Gemini now answers.
- The baskets match the brief.
- The tax lens is excellent and every figure checks out.
- Kai is in.

Four things remain before submission:

- The brief's taxi question still returns the wrong number.
- VAT cannot be reached from chat.
- "Last month" means different months offline and with Gemini.
- 16 tests error on Linux.

After that, the submission still needs a PR to `main`, the platform draft and the video.

### What is done

| Round 1 item | Status |
| --- | --- |
| Gemini | **Done.** `gemini-3-flash-preview` answered live with `source: gemini` in 2.5–6.4 s. "我九月份在餐厅花了多少钱？" (Chinese for "How much did I spend at restaurants in September?") returned €225.70 across 10 rows. "What kind of spender am I?" fell back once with `invalid_response`, but the answer was still correct. |
| Baskets | **Done.** For Alex in September 2026: regular €1,266.90, irregular €0.00, everyday €611.76. |
| Brief questions | **3 of 4 correct:** dining out −20% gives €45.14, the spender profile works, and safe-to-spend gives €3,288.31. The taxi question is wrong; see fix 1. |
| Tax lens | **Done and correct.** The rate table matches Vero for all three periods. Each transaction in the list shows "tax inside". Rows without a clear rate stay uncovered instead of getting a guessed rate. Totals match my independent calculation to the cent: Alex €212.38 of €1,878.66, and Kai €135.64 of €1,768.76. |
| Young-adult persona | **Done.** Kai is `CUST01331`, and the home card shows the payday-timing pattern. |
| Submission | **Not yet.** There is no PR to `main`, and the platform shows only the Blueprint Evidence draft. |

**How I checked**

- I rebuilt the database from the four official CSVs, which took 7 s, and ran the test suite.
- I ran the app twice, offline and with Gemini.
- I asked the brief's questions through `POST /api/coach`.
- I recomputed the figures from the raw CSV.

### Fix before submission

#### 1. The taxi question returns transport, not taxis

"How much did I spend on taxis last month?" returns €266.80 across 6 rows: all of Transportation. For Alex in September 2026, those rows are:

| Rows | MCC | Amount |
| --- | --- | --- |
| Fuel | 5541, 5542 | €155.55 |
| Parking | 7523 | €62.16 |
| Public transport | 4111 | €49.09 |

**There are no taxi rides.** The dataset has a taxi MCC, **4121**, with 59,201 rows overall. The README already lists this as a known limitation. The problem is that it is the brief's first example question, so judges will probably type it.

**Fix**

- Add an `mcc_code` filter that accepts a list to `/api/statistics` and to the coach parameters.
- Map these synonyms to MCCs:

  | Words | MCC |
  | --- | --- |
  | taxi, taksi | 4121 |
  | bus, train, tram, metro, public transport | 4111 |
  | fuel, petrol, bensa | 5541, 5542 |
  | parking | 7523 |

  Keep the category-wide answer only for "transport" in general.
- When the result is zero, say so and show what the category did contain. For example: "No taxi rides in September. Your €266.80 of transport was fuel €155.55, parking €62.16 and public transport €49.09." This makes a strong demo answer: the coach understood the question and taught something.
- Use two personas as fixtures:
  - Robin (`CUST00676`) has one taxi ride in September 2026, €26.64.
  - Taylor (`CUST00296`) has one in August 2026, €75.49.
- Change `test_official_questions.py` to expect MCC 4121 rows instead of all of Transportation.

#### 2. VAT cannot be reached from chat

The tax lens is our main differentiator, but asking about it in chat does not reach it:

| Question | Offline | Gemini |
| --- | --- | --- |
| How much VAT did I pay in September? | `explain_change`, the restaurant comparison | `observed_tax_evidence`: "no explicit tax records" |
| How much VAT is inside my purchases? | `explain_change` | not tested |
| 我九月份交了多少增值税？ | not tested | `observed_tax_evidence` |

The last question is Chinese for "How much VAT did I pay in September?".

**Fix**

- Add a `vat_estimate` intent that returns the existing VAT lens and its monthly card.
- Add the intent to the Gemini allowlist.
- Add these offline keywords: `vat` and `tax inside` (en), `alv` and `arvonlisävero` (fi), `moms` and `mervärdesskatt` (sv).
- "How much tax did I pay?" should answer two things: explicit tax records are unavailable, and "≈ €212.38 of VAT was included in your September purchases (estimate)", with a link to the lens.
- Add one test per language.

#### 3. "Last month" and named months

- **"Last month" differs.** With September selected, "last month" means September offline and August with Gemini. Use one rule in both paths. I recommend counting from the demo's reference date, 2026-09-30, so that "last month" is August 2026 and "this month" is September 2026. That is what Gemini already does.
- **Named months are ignored offline.** "How much did I spend on groceries in August?" returns September, €379.79. The Gemini path correctly returns August, €442.26 across 6 rows. Parse month names in en, fi and sv (August, elokuu, augusti).
- State the resolved period in every answer, for example "August 2026".

#### 4. 16 tests error on Linux

`tests/test_web_contract.py` passes about 138 KB of JavaScript as a single `node -e` argument. Linux limits one argument to 128 KiB and fails with "Argument list too long". macOS has no such limit, which is why the tests pass on your machine. I verified this one-line fix: with it, 176 tests pass and 1 is skipped.

```python
result = subprocess.run(['node', '--input-type=module'], input=script, capture_output=True, text=True, timeout=30)
```

#### 5. Submission

- Open a PR from `Erin-lab-design/s-bank` to `main`. Yue merges it.
- Create an S-Pankki submission on the Junction Platform: **New submission**, with S-Pankki as the main challenge. Ask Yue if anything is unclear.
- Record a 2-minute video at phone width. Suggested order:
  1. Alex's restaurant change.
  2. The taxi answer with the MCC breakdown.
  3. The VAT card and the "tax inside" rows.
  4. Kai's payday story.

### If time remains

- **Make Kai's home card concrete.** For example: "Your balance went to −€11.82 on 28 Sep, one day before pay. The €236.44 clothing purchase on 26 Sep (≈ €48.04 VAT) caused it. Buying it on payday would have kept your lowest balance at €224.62." The numbers are in Round 1, section C.
- **Follow-up questions.** "And restaurants?" should inherit the previous question's period and measure.

### Order until Sunday 10:00

| When | What |
| --- | --- |
| Sat evening | Fix 4 (5 minutes), then fixes 1 and 2 |
| Sat night | Fix 3, the PR to `main` and the platform draft |
| Sun 06:00–09:30 | Kai's card, the video and the final submit. No new features after 08:00 |

### Agent prompt for Erin (round 2)

```text
Repo: Yue-fy/Junction_Hannah_family. Run:
  git fetch && git switch Erin-lab-design/s-bank && git pull --ff-only
Read AGENTS.md, then "Round 2" of the captain review:
  git show "origin/Yue-fy/s-bank-review:s bank/docs/CAPTAIN_REVIEW.md"
Work only inside `s bank/`.

Do the Round 2 fixes in this order, each with unittest cases:
4. tests/test_web_contract.py: pass the node script on stdin (input=script) instead of `-e`.
1. Add an mcc_code filter (list) to /api/statistics and the coach parameters.
   Map taxi->4121, public transport->4111, fuel->5541/5542, parking->7523.
   A zero result names what the category did contain.
   Update test_official_questions.py: Robin CUST00676 has one taxi ride in 2026-09, EUR 26.64.
2. Add a vat_estimate coach intent (offline keywords en/fi/sv plus the Gemini allowlist) that returns the existing VAT lens.
   "How much tax did I pay?" answers "explicit tax records unavailable" plus the VAT estimate.
3. Use one rule for "last month" in both the offline and Gemini paths: relative to the reference date 2026-09-30, so August 2026.
   Parse named months in en/fi/sv. State the resolved period in every answer.
If time remains, make Kai's payday card concrete (numbers in Round 1, section C).

Stop and ask before adding dependencies, deleting files or touching anything outside `s bank/`.
Never commit data, .env or keys. Never push to main or force-push.

Finish:
- From the repo root, run: PYTHONPATH="s bank" python3 -m unittest discover -s "s bank/tests"
- Ask the brief's four questions plus "How much VAT did I pay in September?", once offline and once with Gemini.
- Push, then open a PR to main with screenshots and a short summary.
```

---

## Round 1 · commit `c202ced`, Saturday 16:30 (kept for reference)

Review of branch `Erin-lab-design/s-bank` at commit `c202ced`, Saturday 14 November 2026, 16:30. Final submission is due on **Sunday 15 November at 10:00**.

**Summary.** The prototype is strong. It runs, the numbers are correct and the tests pass. Three issues should be fixed before submission:

- Gemini never answers.
- Three of the brief's own example questions get the wrong answer.
- The three spending baskets contradict S-Pankki's definition.

After those fixes, the biggest gains come from three things: a **tax lens** that shows the VAT inside every purchase, free exploration of the user's own data, and a young-adult payday story.

### What I verified

- I rebuilt the demo database from the four official CSVs. The SHA-256 checksums match `PIPELINE.md`. The import took about 5 seconds.
- `python -m unittest discover -s tests` ran 96 tests: all passed, 1 skipped.
- I walked the main flow at iPhone 15 size:
  - The home insight reads "Restaurant spending rose €110.27".
  - The comparison shows €115.43 → €225.70 (10 → 10 purchases, average €11.54 → €22.57).
  - The 20% scenario gives €45.14. Marking the €36.47 purchase as a one-off changes it to €189.23 × 20% = €37.85.
  - The calculation drawer works, with an audit note and undo.
- I checked every Money Map figure for `CUST00001`, September 2026, against the raw CSV, and all match:

  | Figure | Amount |
  | --- | --- |
  | Income | €2,447.81 |
  | Outflows | €2,114.38 |
  | Regular essentials | €620.31 |
  | "Irregular" essentials | €646.59 |
  | Discretionary | €611.76 |
  | Saving and transfers | €235.72 |

- No data, `.env` or keys are committed.

### Must-fix before submission

#### 1. Gemini never answers

- The default `GEMINI_MODEL=gemini-2.5-flash` returns **HTTP 404** on the Junction Gemini key, so every question silently falls back to the keyword rules.
- With `GEMINI_MODEL=gemini-3-flash-preview`, the model Stoa uses, the call works. However, 4 of 5 test questions exceeded the hard 4-second timeout in `coach.py` and fell back anyway.
- "Originality of AI integration" is 20% of the score, so this matters.

**Fix**
- Default to `gemini-3-flash-preview`.
- Raise the timeout to about 10 seconds, or lower the thinking budget.
- Show a "thinking" state in the UI.
- Expose `fallback_reason` in a debug view so we can see when it happens.

**Done when** the questions in item 2 come back with `source: "gemini"` at least 4 times out of 5.

#### 2. The brief's own example questions

Judges will probably type these, because they are in the brief. Results for `CUST00001` today:

| Question | Result today | Expected |
| --- | --- | --- |
| How much did I spend on taxis last month? | Restaurant change | September Transportation total, with its rows |
| How much could I save if I reduced dining out by 20%? | Asks for a goal amount and date ("save" matched the goal rule) | The existing restaurant 20% scenario: €45.14 |
| What kind of spender am I? | Restaurant change | A short three-basket profile |
| What is safe for me to spend this week? | Safe-to-spend | Keep as it is |
| Paljonko käytin ravintoloihin syyskuussa? | Restaurant change | September restaurant total, €225.70 |

**Root cause.** No intent can answer "total for category X in period Y". The offline router is keyword-first.

**Fix**
- Add a category-total intent with a small synonym map, for example taxi or bus → Transportation, and dining out or lunch → Restaurants.
- Route "reduce X by N%" to the scenario.
- Add a profile answer built from the Money Map.
- Add one unit test per row of the table.

#### 3. The three baskets contradict the brief

The brief defines the baskets as:

- mandatory and regular (rent);
- mandatory and **irregular (a broken washing machine)**;
- everyday spending that slips away (coffees).

`classification.py` disagrees in two ways:

- It labels Groceries, Transportation and Health as "irregular essentials". For `CUST00001`, the €646.59 shown under "Irregular essentials" is groceries plus transport.
- It puts Home & Tech, where a washing machine would be bought, under discretionary.

"Impact on financial literacy" is 20% of the score.

**Proposed mapping, with the user still able to relabel**

| Basket | Categories |
| --- | --- |
| Regular essentials | Housing, Utilities, Groceries, Transportation |
| Irregular essentials | Health, Home & Tech |
| Everyday discretionary | Restaurants, Entertainment, Lifestyle, Travel |

If you prefer, keep "flexible essential" as an internal role, but do not label it "irregular".

#### 4. Smaller items

- The calculation drawer shows the excluded row as `tx:574:34cb…`. Show it as date · merchant · amount, and keep the ref in a tooltip.
- **Submission.**
  - Open a PR to `main`.
  - Create an S-Pankki draft on the Junction Platform. Each challenge needs its own submission, and only the Stoa draft exists today.
  - Record a 2-minute phone-sized video.

### Improvement ideas, ranked by judging impact per hour

#### A. Tax lens: "how much tax is in each purchase" (captain's idea, recommended)

Finnish prices include VAT (ALV), but almost nobody knows how much. Showing the VAT inside every purchase and every month is concrete financial literacy. It is also original: we know of no budgeting app that does it. The data supports a good estimate, because 94.6% of purchases have an MCC code and every row has a category.

**Rates must follow the transaction date.** The dataset runs from October 2024 to September 2026 and crosses three rate regimes ([Vero: rates of VAT](https://www.vero.fi/en/businesses-and-corporations/about-corporate-taxes/vat/rates-of-vat/), updated 1 January 2026):

| Period | General | Food and restaurant meals | Passenger transport, medicines, accommodation, culture, sport, books | Newspapers |
| --- | --- | --- | --- | --- |
| Oct–Dec 2024 | 25.5% | 14% | 10% | 10% |
| 2025 | 25.5% | 14% | 14% | 10% |
| From 1 Jan 2026 | 25.5% | 13.5% | 13.5% | 10% |

Healthcare and medical services are VAT-exempt. Residential rent is also exempt. Alcohol served in restaurants and bars stays at 25.5%.

**Method**
- VAT inside a price = `amount × r / (1 + r)`, computed in cents and rounded half up per transaction.
- Map MCC to a rate band first, then fall back to the category:

  | MCC | Band |
  | --- | --- |
  | 5411, 5422, 5451, 5499 (food) | food band |
  | 5812, 5814 (restaurants) | food band |
  | 5813 (bars) | general |
  | 4111, 4121 (passenger transport) | reduced band |
  | 5912 (pharmacy) | reduced band |
  | 7011 (hotels) | reduced band |
  | 7832, 7922 (cinema, events) | reduced band |
  | 8011, 8021, 8099 (doctors, dentists, health) | exempt |
  | 5541, 5542 (fuel), 7523 (parking) | general |
  | Home & Tech, Lifestyle | general |
  | Housing | exempt |

- Record the source of each rate (MCC or category) so the drawer can say how it was estimated.

**Demo numbers (September 2026, estimate)**
- `CUST01331`:
  - The €236.44 clothing purchase (MCC 5651, 26 Sep) contains about **€48.04 of VAT** at 25.5%.
  - The month's €1,768.76 of spending contains about **€135.64 of VAT**. Rent of €965.31 is exempt, so about **€17 of every €100 spent outside rent is VAT**.
- `CUST00001`:
  - About €212.38 of VAT in €1,878.66 of spending.
  - The €225.70 of restaurant meals contains €26.85 of VAT at 13.5%.

**Be honest in the UI**
- Always show "≈" and "estimated VAT".
- Grocery stores also sell non-food at 25.5%, and MCC 7999 can be either a sport service (13.5%) or other recreation (25.5%).
- Excise duties (fuel, alcohol, tobacco) are not included.

**UI**
- A "Tax inside" line on each transaction row.
- A monthly card: "≈ €135.64 of your spending was VAT", split by rate.
- A one-tap explainer of the three rates.
- The calculation drawer lists the rate and why it was chosen.

**Tests**
- One row per rate regime, including a 2025 vs 2026 restaurant purchase (14% vs 13.5%).
- An exempt dentist visit.
- A bar at 25.5%.
- An MCC-less purchase that falls back to its category.

**Optional, P2: income tax.** The data has net salary only. Let the user enter their tax-card withholding percentage, then show estimated gross pay and income tax. Label both as user input.

#### B. Free exploration (the brief's "MyData" point)

The brief asks to "let users explore their own data freely rather than showing fixed charts". Today the coach can only pick one of 7 intents and a precomputed candidate.

**Proposal**
- Add one generic, deterministic query: category (or basket) × period × measure (total, count, average, top merchants).
- It returns a small chart plus the rows.
- Gemini only fills in and validates the parameters, which also fixes item 2.

This is the highest-leverage change for both the AI and the MyData criteria.

#### C. A young-adult payday persona

The brief stresses young adults, but `CUST00001` is 63.

`CUST01331` is **18** and tells the "safe to spend" story directly:

- Rent of €965.31 leaves on 5 Sep.
- €236.44 goes on clothing on 26 Sep.
- The balance hits **−€11.82 on 28 Sep**, the day before pay arrives (€1,874.62 on 29 Sep). That pay came 45 days after the August pay on 15 Aug.
- Pay arrived on the 15th in 7 of the last 10 months and on the 29th in 3.
- Moving the purchase to payday keeps the lowest balance at €224.62.
- The tax lens adds: "€48.04 of that purchase was VAT".

This is common in the data. From April to September 2026, 15.2% of customer-months dip below zero. The median first negative day is 6 days before the customer's usual payday, and 15.7% of gaps between paychecks are 40 days or longer. Safe-to-spend should therefore account for an uncertain next payday instead of assuming one date.

#### D. Open-data benchmark (only if time allows)

Comparing the user with Statistics Finland's household budget survey by age group is legitimate, unlike synthetic peer comparisons. Add it only if the category definitions can be mapped honestly. Otherwise skip it.

#### Not this weekend

PSD2 multi-bank, the mortgage persona, and forecasts longer than 30 days.

### Suggested order until Sunday 10:00

| When | What |
| --- | --- |
| Sat evening | Items 1–3 (≈3 h), then open the PR to `main` and create the platform draft |
| Sat night | Tax lens A (≈3 h) and free exploration B (≈3 h) |
| Sun 06:00–09:30 | `CUST01331` demo story, 2-minute video, final submission. No new features after 08:00 |

### Agent prompt for Erin

```text
Repo: Yue-fy/Junction_Hannah_family. Run:
  git fetch && git switch Erin-lab-design/s-bank && git pull --ff-only
Read AGENTS.md and `s bank/docs/CAPTAIN_REVIEW.md`.
Work only inside `s bank/`.

Do the "Must-fix before submission" items 1-4 in order, with unittest cases for each. Then build the tax lens (section A):
- date-aware Finnish VAT rates from the table;
- MCC-first mapping with category fallback;
- integer cents, rounded half up per transaction;
- a per-row "tax inside" value, a monthly VAT card and an explainer;
- the calculation drawer shows the rate and its source;
- tests for each rate regime, an exempt row, a bar at 25.5% and an MCC-less row.
If time remains, do section B (one generic category x period x measure query that Gemini fills in).

Stop and ask before adding dependencies, deleting files or touching anything outside `s bank/`. Never commit data, .env or keys. Never push to main or force-push.

Finish:
- run `python3 -m unittest discover -s tests` from `s bank/`;
- walk the flow at phone width;
- push, then open a PR to main with screenshots and a short summary.
```

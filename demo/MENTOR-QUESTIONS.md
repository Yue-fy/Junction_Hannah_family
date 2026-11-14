# Questions for the Stoa mentor (Saturday morning)

Written by agent Q at 04:15 on 14 Nov from what the team learned overnight. Ordered by how much the answer changes
what we do in the last hours. Each question says **why we ask** and **what we do with each answer**, so whoever
talks to Stoa can decide on the spot. Keep it to 10 minutes: ask 1–6 first.

## 1. How is the hidden test scored, exactly?
- Is it the same scorer as the dataset (counts exact, areas/lengths/volumes within 2 %, text free-form)? Who grades
  text answers: a person, an LLM judge, or string match?
- Do you score per question and average, or per drawing / per question kind? Is there a weight per source?
- **Why:** our headline number changes a lot with the weighting. On our sealed test, micro accuracy is 87.4 % but
  weighted by source (CubiCasa raster counts are 68 % of the full dataset) it is 79.8 %.
- **Do:** if text is LLM-judged, spend the afternoon on IFC text answers (57.8 % judged today). If per kind is
  averaged, the small kinds (IFC, schedules) matter as much as CubiCasa.

## 2. What does a wrong answer cost compared with a low-confidence answer or "I don't know"?
- Do you use our `confidence`? E.g. accuracy only on answers above a threshold, a risk–coverage curve, a Brier score?
- Is "best estimate + low confidence + what is missing" (our policy) scored better than a confident guess?
- **Why:** we never refuse; we return the best estimate with a calibrated confidence (ECE 0.017 on sealed test, 98 %
  right when confidence ≥ 0.8), the assumptions, and what is missing. Our red team shows the remaining risk is
  *confidently wrong* answers on unusual wordings, not wrong answers in general.
- **Do:** if confidence is scored, tighten the caps on unseen wordings (costs a little accuracy, buys calibration).
  If only accuracy counts, loosen them.
- Follow-up from our red team: **if a question names something the drawing doesn't have** (a storey '7. Level' in a
  5-storey model, room 'Ballsaal' on a plan without one), what do you want back: "not found" + the list of what
  exists, or the closest match with a warning? (Tonight our IFC path answered the closest storey at 0.97 confidence;
  we are fixing that either way, but the answer format depends on you.)

## 3. What will the "harder, different" questions look like?
- More arithmetic on top of a quantity (prices, rates, per-unit ratios, percentages)? Questions across several
  drawings of one building? Questions about scans with no questions today (HABS, Finna, Europeana, Wikimedia)?
- New file types or the same sources? New languages?
- Will the files arrive in the same folder layout (`data/<source>/<file>`) and with their sibling formats
  (Swiss PDF + DXF + PNG; IFC + rendered plan PDFs)?
- **Why:** our deterministic solvers are near-perfect on the given question kinds (Swiss 98–100 %, IFC 97–100 %), but
  on our own sealed set of *new wordings of the same kinds* we drop to 63 % micro, and on derived quantities (price ×
  count etc.) to 35 %. We know where it breaks; we need to know which part to fix first.
- **Why the folder question:** our router recognises the source from the path. A copy of a CubiCasa plan outside the
  dataset folder is routed as "unknown raster" and loses the fine-tuned counter (red team, `redteam/REPORT.md`).

## 4. How do you score cost?
- Per question in dollars? Wall time? Does local GPU inference count, and at what price? Do you count the one-off
  cost of training our small model (33 min on one GPU)?
- **Why:** we track tokens, GPU seconds, hosted API calls and wall time per question ($0.28 per 1,000 questions on
  sealed test; 64 % of questions never call a model). We need to know which of these you want on the slide.

## 5. How do you score "the reasoning" and "the interface"?
- Do judges look at the trace / evidence of individual answers, or only at the demo?
- Is a highlighted box on the drawing / a highlighted element in the 3D model what you mean by verifiable in seconds?
- Would your customers rather see one answer with evidence, or a range ("7 windows, 90 %: 6–12")?
- **Why:** we have both (boxes on 2D plans, GUIDs in 3D, cross-checks "drawing says 12 doors, IFC says 12 ✓", count
  ranges). We want to spend the last hours on the one that scores.

## 6. Which question types matter most to your customers?
- Site engineers / estimators / facility managers? Quantity take-off (areas, lengths, counts) vs compliance (door
  widths, fire ratings) vs "find the sheet that shows X"?
- **Why:** it decides which three questions we show live in the 3-minute pitch.

## 7. Data and licences
- May we use models pretrained on the original public datasets (e.g. the CubiCasa5K segmentation model, CC BY-NC)?
  It adds located evidence (boxes) to 39 % of CubiCasa answers instead of 17 %, but saw most of your CubiCasa images
  in its training, so we label its accuracy as inflated and keep it off by default.
- Is fine-tuning a small model on the given dataset's train split allowed? (We trained a LoRA on Qwen3-VL-8B on our
  train split only; it is worth +6 weighted points on sealed test.)
- May we use the original datasets' public annotations (CubiCasa5K SVG labels, Swiss Dwellings geometry) at all,
  e.g. for training, if not as a lookup at test time? (We do not use them today.)
- Can we show your drawings in a public demo video if we keep each file's credit line?

## 8. Practicalities
- Will we get the hidden questions as files to run, or do you run our code? If you run it: which hardware, is there
  a GPU, is there internet (we use a local 8B vision model and, for a prize, NVIDIA's hosted Nemotron)?
- Time limit per question?
- When exactly are the example questions shown at noon, and in what form (file / slide)?
  → We have a one-command path to run any list of new questions: `python -m stoa.eval --solver pipeline --split
  file.jsonl --no-leaderboard` (KNOWLEDGE 03:47).

## What we tell them in one breath if asked "what did you build?"
Ask a question about a drawing or a building model → an answer, how sure we are, and where it came from, highlighted
on the 2D sheet or in the 3D model. Structure first, pixels last: we read vector geometry, IFC and schedule tables with
code, and only use a (small, fine-tuned) vision model when there is nothing to parse. Sealed test: 87 % (weighted 80 %),
98 % right when we say we are sure, $0.28 per 1,000 questions.

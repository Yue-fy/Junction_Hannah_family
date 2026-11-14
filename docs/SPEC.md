# SPEC — Make Blueprints Talk (Stoa)

> Owned by the captain. Keep it to one page.
> **Status:** DRAFT written overnight by agent S0 for the captain (Fri 13 Nov 23:40). Captain confirms in the morning.

## Challenge
- Partner / challenge: Stoa, "Make Blueprints Talk" (Verda's AI Infrastructure track)
- Link: Junction Platform challenge page (see `docs/EVENT.md`)
- Mentor contact(s): TBD (ask at the Stoa booth)
- Judging criteria: a **correct** answer plus **where in the drawing it came from**, so a human can verify it in
  seconds. Counts exact; areas, lengths and volumes within 2%; text answers free-form. Stoa wants approaches
  next year's frontier models won't make obsolete: hybrids of models, computer vision, 3D, geometry, small
  fine-tuned models.

## Problem
Site engineers and estimators spend hours reading drawings and BIM models to answer simple quantity questions
("how many windows on this floor?", "net area of room 2.14?"). Asking a general chat model gives a confident
number with no way to check it, and it is often wrong on dense technical drawings.

## Target user
A construction professional (estimator, site engineer, architect) who needs a quantity from a drawing or an IFC
model and must be able to trust it.

## Demo story
1. Pick a drawing or an IFC model, ask a question in any language ("How many windows on 2.korrus?").
2. Get the answer with a confidence, and every counted object or measured room highlighted: boxes/points on the
   2D drawing, highlighted elements in the 3D model. Click an item to zoom to it.
3. Show the accuracy table per source against the "just ask a VLM" baseline, and explain where and why it still fails.

## In scope (MVP)
- One Python package `stoa` with a shared answer contract (value, unit, confidence, evidence) and one eval tool.
- Solvers by source: IFC (ifcopenshell), vector/DXF and PDF schedules (geometry + text), raster counting
  (VLM + CV), routed by a question parser; "just ask a VLM" baseline.
- Abstain when unsure; evidence on every non-abstained answer.
- Web demo: question box, answer card, 2D viewer with evidence, 3D IFC viewer with highlighted elements.

## Out of scope (we say no to these)
- DWG parsing, training on leaked labels, user accounts, cloud deployment beyond a demo host.

## Stretch goals (only after the demo path is solid)
- Side-by-side "drawing says 12, model says 12 ✓" cross-check between rendered PDFs and the IFC model.
- Nemotron 3.5 Super VL doing visible core work (NVIDIA prize); Gemma for a sub-task (Gemma prize).
- A small fine-tuned model for raster symbol counting.

## Data & APIs from the partner
- Stoa Junction dataset (~14,000 drawings, 127,044 questions; preview 7,990). Kept outside git. Every file keeps
  its own licence (`data/<source>/LICENSE.md`, some NonCommercial/ShareAlike): show credits in the demo.
- Full data by source: cubicasa5k 85,514 count Qs (PNG), swiss_dwellings 37,584 (counts + areas, asked on PDF,
  DXF sibling), ifc_models 3,062 (29 models, asked on IFC and rendered PDFs), ifc_bench 820 text, opening_design 64.

## Open questions for mentors
- How is the hidden test set built (same sources and proportions as `questions.jsonl`?), and how are text answers judged?
- How much do verifiability/evidence count versus raw accuracy?
- May we use the original public annotations of CubiCasa5K / Swiss Dwellings (risk: they may equal the answers)?
- Which question types matter most for Stoa's customers?

## Submission checklist
- Deadline: final submission Sun 15 Nov 10:00 (see `docs/EVENT.md`)
- [ ] Demo video (check the length limit in the Junction rules)
- [ ] Project description
- [ ] Repo link and README
- [ ] Pitch slides

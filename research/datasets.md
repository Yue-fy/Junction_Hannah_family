# Datasets (R1): what exists, licences, leakage

Verified on 13 Nov 2026. [V] = checked on the primary page, or by range-reading the actual archive.
[S] = seen only in search results or secondary pages.
**Leakage rule (DECISION D3):** original labels of the datasets our drawings come from are off-limits
tonight, both as lookups and as training labels. Pretrained models trained on them may be evaluated only on
drawings outside their training split.

## The sources of our drawings

### CubiCasa5K [V]: source of our `cubicasa5k` (4,787 PNGs, 67% of the questions)
- **Links:** github.com/CubiCasa/CubiCasa5k · arXiv 1904.01920 (SCIA 2019) · zenodo.org/records/2613548 (one 5.47 GB zip).
- **Licence:**
  - Zenodo says CC BY-NC-SA 4.0; the repo says CC BY-NC 4.0. Apply the stricter one, as `data/cubicasa5k/LICENSE.md` does.
  - The weights (`model_best_val_loss_var.pkl`, Google Drive) have no separate licence, so treat them as NC.
- **Layout:** `cubicasa5k/{high_quality_architectural,high_quality,colorful}/<id>/{F1_original.png, F1_scaled.png, model.svg}`.
  - Multi-floor plans have F2–F4 images, but one `model.svg` covers all floors.
- **Mapping (verified by R1):** our `<folder>-<id>.png` is the original `/<folder>/<id>/`. All 4,787 map onto the official lists:
  - train 4,018 · val 382 · test 387.
  - The lists are in `$JUNCTION_SHARED/artifacts/R1/cc5k_split/`.
  - The leak-safe eval set is `cc5k_heldout.jsonl` (1,504 Qs on 376 drawings from the official test list).
- **Annotations, i.e. our answers (LEAKAGE):**
  - In `model.svg`: `<g id="Window">`, `<g id="Door">`, and `class="FixedFurniture <Type>"` (Toilet, Sink,
    DoubleSink, CornerSink, Bathtub, Shower, ShowerCab, SaunaBench, …, 52 types).
  - Also `class="Space <Type>"` (Bedroom, Bath, Kitchen, Outdoor, Sauna, …).
  - Agent check on plan 10052: 7 windows, 5 doors, 1 toilet. That matches our questions for colorful-10052 (windows 7, doors 5, WC seats 1).
- **Official model:**
  - Classes: 12 room classes, plus 11 icon classes (window, door, closet, electrical appliance, toilet, sink, sauna bench, fireplace, bathtub, chimney).
  - **No shower class.**
  - Icon IoU on test: window 66.8, door 53.6, toilet 62.8, sink 55.7, sauna bench 67.3, bathtub 26.7.
  - Trained on train and selected on val, so it has seen ~92% of our images.
- **Derived copies (same leakage):**
  - HF `phungpx/cubicassa5k-coco`
  - HF `jprve/FloorPlansV2` (bedroom-count labels)
  - Roboflow "cubicasa" floor-plan sets
  - the CubiCasa part of AECV-Bench

### Swiss Dwellings (Archilyse) [V]: source of our `swiss_dwellings` (30% of the questions)
- **Links:** concept DOI 10.5281/zenodo.7070951; latest v3.0.0 is zenodo.org/records/7788422 (2023-03-31). Licence **CC BY 4.0**.
- **Files:** `geometries.csv` (3.26 M rows, 13,905 floors; WKT in metres, site-local coordinates), `simulations.csv`, `locations.csv`.
  - There is no PNG/PDF/DXF; Stoa rendered those from the geometry.
  - Columns: apartment/site/building/plan/floor/unit/area ids, unit_usage, entity_type, entity_subtype, geometry, elevation, height.
  - Subtypes include BEDROOM, BATHROOM, BALCONY, LOGGIA, SHAFT, TOILET, SINK, BATHTUB, SHOWER, WINDOW, DOOR, ENTRANCE_DOOR.
- **LEAKAGE:** the agent found our floor site3387/bldg5238/floor23498 in it: 11 windows, DOOR 15 + ENTRANCE_DOOR 5 = 20 doors, 4 toilets, 4 sinks, 2 bathtubs. That equals our answers.
  - We don't need it anyway: the DXF Stoa ships gives the same numbers (`methods.md` §4).
- **Modified Swiss Dwellings (MSD, ECCV 2024):**
  - arXiv 2407.10121 · github.com/caspervanengelenburg/msd · 4TU DOI 10.4121/e1d89cb5-6872-48fc-be63-aadd687ee6f9 (CC BY 4.0).
  - 5,372 residential plans with no features (no bathtubs, no stairs). It leaks room types and polygons for the plans it kept.

### IFC-Bench v2 [V]: source of our `ifc_bench`
- huggingface.co/datasets/sylvainHellin/ifc-bench (CC BY 4.0; 4 models GPLv3) · github.com/sylvainHellin/cobbie.
- Its answer files are our answers, so D3 forbids using them as lookups. The benchmark's tooling and paper are fine to use.

## Other datasets we could use (no leakage; check licence before shipping)

| Dataset | What | Licence | Use for us | Effort |
|---|---|---|---|---|
| FloorPlanCAD (floorplancad.github.io) | 15,663 SVG+PNG CAD drawings, 28 "thing" symbol classes (door, window, sink, toilet, bathtub, …) | annotations CC BY-NC 4.0; authors don't own the drawings | Train or test a symbol spotter on vector/raster plans that are NOT in our data. Chinese CAD conventions. | M |
| ArchCAD-400K (arXiv 2503.22346, NeurIPS 2025) | 413k chunks from 5,538 drawings, 27 categories; 40K subset at HF `jackluoluo/ArchCAD` | "ACADEMIC" badge | Same as FloorPlanCAD, at a larger scale | M |
| R2V (art-programmer/FloorplanTransformation) | Vector annotations of LIFULL plans | code MIT; images need permission from LIFULL | Wall/door/room vectorisation baseline | H |
| ResPlan (arXiv 2508.14006) [S] | 17k plans, no furniture | data CC BY 4.0, code MIT | Room segmentation pretraining | M |
| RPLAN [S] | 80k Chinese residential layouts | request form | Layout priors only | H |
| PixMo-Points [V] | 2.38 M pointing and counting annotations | ODC-BY | Was used to train Molmo's pointing; not drawings | – |
| AECV-Bench [V] | 120 plans with counting labels, plus 192 drawing-QA pairs | no LICENSE | External sanity check of our counters. **Part of it is CubiCasa5K**, so check the overlap with our drawings first. | L |
| DrawingVQA [S] | 92 expert QA pairs on 33 structural sheets | no data link | Hard-question examples resembling Stoa's hidden set | L |

## Without leakage, what is still allowed for cubicasa?
- Count-level labels of OUR train split (questions.jsonl answers on train drawings): fine for priors,
  calibration and fitting `P(detected | true)`.
- External symbol datasets (FloorPlanCAD, ArchCAD) for detector training: no overlap with our drawings.
  Note the licences (NC/academic), and that the domain differs (Chinese CAD vs Finnish raster).
- Zero-shot models (Qwen3-VL, Molmo2, GeCo2, CountGD, SAM 3): fine.

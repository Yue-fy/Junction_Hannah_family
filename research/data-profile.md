# Data profile — Stoa "Make Blueprints Talk" full dataset

Generated 13 Nov 2026 by F from `$STOA_DATA` (full dataset, 127,044 questions). Script:
`PYTHONPATH=. $JUNCTION_VENV/bin/python experiments/f/profile_data.py` (plus the spot checks quoted below).
Stoa warned (13 Nov, 23:40) that the hidden test is harder and different. Read this as "what the given data
looks like", not as "what the test looks like".

## 1. What is asked, where

| source | type | questions | files asked | languages | notes |
|---|---|---:|---:|---|---|
| cubicasa5k | count | 85,514 | 4,787 PNG | EN + FI twin of every question | 12 concepts, 6–24 Qs per plan |
| swiss_dwellings | count | 25,568 | 1,040 PDF | EN + DE/FR/IT twin | DXF + PNG siblings for every PDF |
| swiss_dwellings | area (m²) | 12,016 | (same) | EN + DE/FR/IT twin | room, label total, apartment, floor total |
| ifc_models | area (m²) | 2,218 | 69 PDF + 15 IFC | EN, ET, NL, ES, DA, DE | mostly room net floor area |
| ifc_models | count | 642 | (same) | EN, DE, ES, DA, NL, ET, IT | per storey plan or whole model |
| ifc_models | volume (m³) | 138 | | EN, DE, DA, NL | slabs / walls per storey |
| ifc_models | length (m) | 64 | | EN, DE, DA, NL | total wall length per storey |
| ifc_bench | text | 820 | 25 IFC | EN | IFC-Bench v2, long multi-line answers |
| opening_design | count / area (ft²) / text | 39 / 9 / 16 | 3 PDF sheets | EN | door/window/finish schedules |

- 98.8% of questions come in **twins**: an English row followed by the same question in the drawing's
  language with the identical answer. `stoa.data.concept_map()` pairs them (cubicasa 100%, swiss 100%,
  ifc_models 89%). Eval splits keep one language per concept.
- Answer types: count → int (111,763); area/length/volume → float (9 opening_design areas are int); text → str.
  No negative answers, no zero areas.
- Sources **without any questions**: habs (1,506 JPG), finna (1,800 JPG), europeana (1,085 JPG), wikimedia
  (2,175 JPG + 135 SVG). Stoa said historical scans matter, so the hidden set may ask about them.
- opening_design has 678 PDFs, 271 DWG, 48 IFC and 9 DXF, but only 3 sheets carry questions (A-801 Sports
  Complex schedules: 41 Qs; A700 Cannery Trail schedules: 20; A-701 restrooms: 3).
- ifc_models holds 533 IFC (median 0.35 MB, max 85 MB), 500 PNG, 107 PDF/SVG plans. ifc_bench holds 30 IFC (median
  16 MB, **max 343 MB**): parse once and cache.

## 2. Question templates and answer priors (counts)

cubicasa5k (EN wording; FI twin identical answers). Mode share = how often the most common answer is right:

| concept | mode | mode share | mean | max | zeros |
|---|---:|---:|---:|---:|---:|
| windows | 4 | 14% | 8.8 | 92 | 0% |
| doors (doorways with a leaf) | 6 | 12% | 8.7 | 43 | 0% |
| floors (storeys) | 1 | 80% | 1.2 | 4 | 0% |
| WC seats | 1 | 60% | 1.4 | 20 | 4% |
| sinks + wash basins | 2 | 51% | 2.6 | 30 | 2% |
| showers + bathtubs | 1 | 76% | 1.2 | 22 | 6% |
| saunas | 1 | 57% | 0.6 | 2 | 43% |
| kitchens | 1 | 96% | 1.0 | 4 | 2% |
| bedrooms (MH) | 1 | 31% | 1.7 | 9 | 17% |
| bathrooms (KH, KPH, PH, PESUH, SH) | 1 | 89% | 1.0 | 4 | 7% |
| separate WC rooms | 0 | 56% | 0.5 | 7 | 56% |
| balconies | 0 | 51% | 0.5 | 3 | 51% |

→ The prior alone scores 54% on cubicasa dev. Gains must come from windows, doors, bedrooms, sinks: the
  high-variance concepts.

swiss_dwellings counts: rooms labelled X (6,227 EN; mode 2, 23%), apartments (mean 3.2), **doors (mean 30.7,
max 157)**, **windows (mean 17.8, max 137)**, WCs (4.1), washbasins (4.3), bathtubs (3.2), showers. These floors
are whole buildings, so pixel counting is hopeless. Use the DXF layers (S0 probe: windows 100%, room areas 99.7%).

swiss areas: room net area "room 2.10 ('Zimmer')" (2,045 EN), floor total of numbered indoor rooms (1,040),
label total (1,017), apartment A/B/C… net area (~1,860). All answers have 2 decimals.

ifc_models: room net floor area "the room 'Living Room (A102)' on 'Level 1'" (1,182 EN + NL/ES/DA/ET/DE
variants), counts "shown on the floor plan of '<storey>'" (rooms, doors, stairs, walls, columns, windows) and
"in the model '<name>'" (+ beams, sanitary/light fixtures), storey totals, wall length, slab/wall volume.
Volumes have 3 decimals (13% ≤ 2 dp), and the 2% tolerance applies.

## 3. File characteristics (spot checks)

| source | format | size / geometry | text layer |
|---|---|---|---|
| cubicasa5k | PNG, 90% RGB (10% RGBA) | width p10/p50/p90/max = 395 / 765 / 1,729 / 4,534 px; height 445 / 713 / 1,360 / 4,960 | none (raster); Finnish room codes drawn as pixels |
| swiss_dwellings | PDF 1 page, A3 landscape 1191×842 pt, vector, 0 images | 73–531 vector paths | 75–230 words: room label, room number, **sometimes the area** |
| swiss_dwellings | PNG | 2480×1753 (or portrait) | — |
| ifc_models | PDF 1 page, vector, 0 images, sizes vary (567×774 … 1991×1348 pt) | 87–695 paths | header "Scale 1:100 · cut at 1.20 m above storey level · Generated from IFC (… IfcConvert 0.9.0)"; room names; **areas not printed** |
| opening_design | PDF 3024×2160 pt (42"×30"), **page rotation 90°** | 5k–24k paths | 600–2,200 words (schedules are real text) |

- **Swiss PDFs print net areas on ~27% of floors** (53/200 PDFs contain "m²"). When they do, the gold value
  appears verbatim (119/400 room-area questions have the exact 2-dp gold on the PDF). Text order is not
  reliable (the id is sometimes followed by the next room's label), so match by position. Elsewhere, compute
  areas from the DXF.
- Counting room labels by text occurrence ("how many rooms labelled 'Zimmer'") matches gold on 231/300
  Swiss floors (77%). The misses are probably labels that are substrings of others ("Zimmer" in
  "Schlafzimmer") or multi-word labels. Use whole-word matching and position, or the DXF ROOM_TEXT layer.
- ifc_models PDF room-area values never appear on the plan (0/200): answer from the sibling `.ifc`
  (`stoa.data.siblings(path)[".ifc"]`).
- opening_design pages are rotated 90°. Evidence boxes in `pdf_pt` must use PyMuPDF's page space
  consistently, and the viewer must apply the rotation (PDF.js does if given the page rotation).

## 4. Oddities and pitfalls

- Twins: if you train or count on all rows, every fact counts twice (and both rows share an answer).
- Template normalisation (`stoa.data.template_of`) replaces quoted names and numbers. Quotes vary by
  language: '…', «…», „…“, “…”. Apostrophes inside words (women's) are not quotes.
- ifc_bench answers are paragraphs (lists of spaces with areas). `text_fuzzy` is a weak signal for them.
  Score these with a rubric or an LLM judge later.
- The same building appears in several sources: duplex, fzk_house, smiley_west, molio and digital_hub are
  in both ifc_bench and ifc_models. The split keeps each ifc project together within a source, but
  cross-source pairs are not forced together (e.g. bsc-duplex is in ifc_models train while ifc_bench
  duplex is in test). The question types differ (numeric vs text), so the leakage risk is low.
- ifc_models variants: bimspeed-vitoria_ald26-before vs -project are near-duplicates. bsc-clinic_* and
  bsc-duplex_* are discipline models of one building. They are grouped by project.

## 5. Splits (v2, final; `stoa/eval/splits.py`, seed 20261113)

| split | questions | groups | composition |
|---|---:|---:|---|
| smoke | 206 | 20 cubicasa drawings, 10 swiss sites, 1 ifc project (kit-fzk-haus), 1 ifc_bench project, 1 sheet | quick checks |
| dev | 2,215 | 200 cubicasa, 100 swiss sites, 4 ifc projects, 3 ifc_bench projects, 2 sheets | cubicasa 800, swiss 400+400, ifc area 259 / count 64 / length 9 / volume 22, ifc_bench 200, opening_design 61 |
| test (sealed, S0 only) | 2,199 | 201 cubicasa, 100 swiss sites, 3 ifc projects, 4 ifc_bench projects | no opening_design |
| train | 109,952 | 4,366 cubicasa, 830 swiss sites, 8 ifc projects, 8 ifc_bench projects | everything of those drawings |
| unused | 12,472 | twins and capped-out questions of eval drawings | never train on these |
| hard | 711 | dev drawings only | 250 translations, 250 paraphrases, 211 compositions (`stoa/eval/hard.py`) |
| cc5k_heldout | 1,460 | 365 cubicasa drawings in the official CubiCasa5K test list, minus our test | only for CC5K-pretrained models (S0 D3) |

Headline metric: `weighted_acc` = bucket accuracies weighted by the bucket's share of scored questions in the
full dataset (cubicasa count 67.8%, swiss count 20.3%, swiss area 9.5%, ifc area 1.8%, …).

Floor (dummy = mode/median of the train answers per template): dev micro 26.2%, **weighted_acc 40.4%**, macro 9.6%
(cubicasa 54.1%, swiss count 16.0%, swiss area 4.2%, ifc area 1.9%). hard: translation 30.0%, paraphrase
8.8%, composition 3.7%.

## Historical scans (no questions; added 00:50, 14 Nov)

Stoa: "historical drawings (scans) matter … the hidden set may ask about them". What is there (from each source's
README table and the files):

| source | images | licences | long side px p10/p50/p90 | what the titles say |
|---|---:|---|---|---|
| habs (HABS/HAER/HALS, US NPS via LoC) | 1,506 JPG, 1.1 GB | PDM (all) | 3000 / 3000 / 3000 | "HABS AK,19-FOGRE,1-A- (sheet 1 of 3) - <building>, <place>": building, place, sheet n of m |
| finna (Helsinki City Archives, Architecture & Design Museum) | 1,800 JPG, 1.5 GB | CC BY 4.0 (all) | 3000 / 3000 / 3000 | Finnish address + kind: julkisivu (elevation) 430, leikkaus (section) 376, pohjapiirus (plan) 229, asemapiirros (site plan) 110 |
| europeana | 1,085 JPG, 0.4 GB | PDM 487, CC BY 176, **CC BY-NC 113, BY-NC-SA 87**, CC0 93, BY-SA 50 | 781 / 1200 / 3000 | many languages (sk, pt, hr, de, it …): "Grundriss", "tlocrt", "Pôdorys" … |
| wikimedia (WAFFLE list) | 2,175 JPG + 135 SVG (each SVG has a JPG twin), 0.8 GB | PDM 1,207, BY-SA 4.0 449, BY-SA 3.0 277, no-known-restrictions 136, CC0 75, BY 60 | 588 / 1350 / 2500 | building names in many languages; book plates ("Choix des monuments … Plans") |

- **Multi-sheet sets (cross-document links for the KG):** habs 1,271 projects, 156 with ≥ 2 sheets (file prefix
  before `_sheet`, e.g. `il0377_sheet_0000N`, up to 4); finna 919 title groups, 190 with ≥ 2 drawings (same address:
  plan + elevation + section of one building, e.g. "Mannerheimintie 17" 36 drawings, "Meilahden Huvila-alue" 128).
  Questions like "how tall is the facade drawn on the elevation of the building in this plan" need these links.
- The README tables give title, licence, credit and source URL per file: the only metadata. Use them as evidence
  for "what/where is this building" and as the credit line in the demo (COMMON rule 4). Scans are downscaled to
  ≤ 3,000 px, so small dimension text may be unreadable: say so in `missing`.
- No ground truth exists for these, so nothing can be scored. The `hard`/`hard2` splits do not cover them. Any
  answer must carry assumptions (scale from a scale bar or dimension string; else "no scale found").
- Licence trap: 200 europeana files are non-commercial (BY-NC / BY-NC-SA). Fine to show in a hackathon demo with
  credit, but keep them out of anything commercial and never commit them (data stays outside git anyway).

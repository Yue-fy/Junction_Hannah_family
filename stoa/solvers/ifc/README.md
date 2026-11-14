# `ifc` solver + project knowledge graph (owner: W1)

Answers questions about IFC building models, and about drawings rendered from them, from the model itself.
Evidence: one IFC GlobalId per counted or summed element, plus a `pdf_pt` box on the plan for the same GUID.

```bash
$JUNCTION_VENV/bin/python -m stoa.eval --solver ifc --split dev --source ifc_models   # 354/354
$JUNCTION_VENV/bin/python -m stoa.eval --solver ifc --split hard --source ifc_models  # 141/141
$JUNCTION_VENV/bin/python -m pytest -q tests/test_ifc_solver.py tests/test_kg.py
```

| File | What |
|---|---|
| `index.py` | `load_index(path)`: parses a model once into storeys and elements (guid, class, effective class, type, storey, Qto, props, materials, geometry), pickled under `$JUNCTION_SHARED/artifacts/W1/ifc_index/`. `ifc_index(path)` returns JSON for the API and the viewer. |
| `parse.py` | Multilingual, template-free question parser → `Intent` (metric, kinds, quoted names, op, filters, group-by). |
| `resolve.py` | Matches storey, room and model names (exact → normalised → fuzzy). |
| `solver.py` | The solver. The definitions are in its docstring; there is a geometry fallback for models without Qto, a 2D link, and cross-checks in the trace. |
| `plan2d.py` | Plan SVG twin → `pdf_pt` box per GUID, room polygons and label boxes. |
| `factcard.py` | For free-text questions no rule covers: one local-LLM call over a fact card built from the model. |
| `../../kg/` | `stoa.kg.links(path)` returns the project graph. `stoa.kg.crosscheck(path, intent, answer)` checks any solver's answer against the IFC model, the drawing, or the DXF. |

How the dataset's gold values were computed (100% on train; see `experiments/w1/explore_defs.py`):
- Room net floor area = footprint of the IfcSpace body geometry (not Revit `Area`, not Qto).
- Wall and slab volume = Qto `NetVolume`. Wall length = Qto `Length`. Wall side area = Qto `NetSideArea`.
- A count "on the floor plan of X" = elements of that class whose spatial container is storey X. Walls are
  IfcWall + IfcWallStandardCase. For IFC2X3 MEP, the effective class comes from the type object.

Question kinds beyond the dataset templates (F's `hard2`: 36/36):
- Operators composed in `solver._compose` from atomic answers (each part keeps its evidence; arithmetic in code):
  average per element, share/percentage of a storey or of the model or of an unfiltered total
  ("% of wall volume that is load-bearing"), threshold counts ("how many of rooms A..D have > 13 m²"),
  "which storey has more X, A or B" (answers the asked name), sum/difference over several storeys.
- Exclusions ("excluding external walls", "not counting windows") are applied when they name a filter or a
  coordinated kind; otherwise confidence is capped at 0.3 and the reason goes to `missing`.
- Unquoted storeys ("level 4", "on the 1.OG floor", "second floor") are resolved by name, number or ordinal.
- List/description requests ("What are the spaces on level 4, with their areas?") are not answered with one
  number: the rule's value goes to the fact-card LLM as a verified fact, with a focus section for the storey.
- Placeholder rooms (>= 80% of IfcSpaces ~1 m², e.g. sixty5) cap room-area confidence at 0.15 and say why.

Harder / different wordings (cycle 4; self-written probes in `experiments/w1/probe.py`, tests in
`tests/test_ifc_arith.py`):
- `arith.py` + `solver._outer`: arithmetic around atomic quantities, computed in code from the normal rules' answers
  (same evidence): prices/rates given in the question ("each door costs 450 EUR", "35 EUR per m²", "€320 each",
  DE/NL/FR/ES/IT "jede Tür … 450 Euro"), multipliers ("every window needs 2 curtains"), add/remove N, ratios
  ("m² of floor per door", "windows per room", "ratio of doors to windows"), numeric yes/no ("Are there more than 40
  doors?" -> yes/no), +N%, window-to-wall ratio (window opening area / external wall gross side area, %), building
  height (highest element top - ground-floor level), "taller than N".
- Geometry outline (`storey_outline`: union of room/wall/column footprints, holes filled): gross floor area, perimeter,
  and external walls when the model has no `IsExternal` (walls on the outline; FZK-Haus 12 x 10 m -> 120 m², 44 m).
- Room relations by plan geometry (`adjacent`: a door/window footprint within 0.35 m of the room): doors of room X,
  rooms with no window / more than one door (conf 0.6-0.65).
- Rooms: largest/smallest/second largest/median room (value or name), largest minus smallest, which/list rooms above,
  below or between thresholds, threshold sums, room volume and ceiling height, room types in any language
  (`arith.ROOM_TYPES`: "bathrooms" -> 'Bad', 'TUALETTRUUM'; falls back to the whole model when the sheet's storey has
  none), room-type shares over the storey's rooms.
- Scope: "whole building"/"all floors" on a plan sheet -> whole model; "each floor" -> breakdown over the model;
  "which storey has the most X" over all storeys; two named storeys summed by default; "compared to" shows both;
  top/lowest storey; storeys above/below ground.
- Guards (confidence <= 0.3 + a `missing` note): a number in the question no rule used, an unresolved quoted name, a
  room type the model doesn't have, an orientation ("north facade"), and a relation between two element kinds the rules
  don't model ("has the most doors").

IFC-Bench style questions (free text, judged; cycle 3):
- Type breakdowns name types the way the authoring tool shows them (`index.type_key_fn`): a shared element Name
  when names are type-like (>= 70% of elements share it with >= 2 others; Revit ':123456' ids stripped), else the
  IfcTypeObject name, else ObjectType. "materials / made of / composition" adds each type's layer materials and the
  unique material list; space breakdowns list every room with its area under its storey (<= 60 rooms).
- Material filters ("concrete in the walls", "steel beams", DE/NL/FR/ES/IT words): elements whose type or name says
  the material first; else elements with a layer of it, and then volume = element volume x layer thickness share
  (4351 insulation 81.7 vs gold 82.2 m³). Nothing says the material -> all elements, confidence <= 0.3.
- "floor slabs" drop roof / landing / foundation slabs. No IfcFooting -> slabs typed BASESLAB or named
  foundation/footing/pad. No IfcRoof -> slabs/coverings typed ROOF.
- Kinds missing from the model: IFC2X3 pipe/duct accessories -> IfcValve / IfcDamper + IfcAirTerminalBox; anything
  else (switches, outlets, toilets, ...) -> proxies/generic elements named like it (confidence <= 0.6).
- Dimensions (index v7): door/window OverallWidth/OverallHeight and wall/slab thickness (sum of layer thicknesses,
  or one material's layers): largest / smallest (+ the type and element name), average, or the distribution.
- New MEP kinds: pipe/duct accessories, meters/sensors, junction boxes, cable fittings, alarms, appliances.

2D cross-checks (`stoa.kg`): the ifc_models sheets are horizontal cuts at storey floor + 1.2 m and draw every
element crossing that plane, of any storey. Checks compare like with like (`_cut_compare`: elements of the
storey that cross the plane vs drawn elements of that storey; 244/268 plan x class rows equal) and explain the
rest (lintel walls above the cut, the next floor drawn on a basement sheet). `ok=None` = no 2D data.

Options (`--solver-arg`):
- `qto=0` ignores Qto and uses geometry only (accuracy measured per kind: volume 69–85%, length 62%, side area 43%).
- `plan2d=0` turns off the 2D boxes.
- `llm=0` turns off the LLM fallback (the solver then refuses free text).

Pitfalls are in KNOWLEDGE.md (W1 entries).

## Languages, unusual models, multi-part questions (cycle 5)

- **Cross-language check** (`IfcSolver._cross_language`): a non-English question whose wording is not a train template
  is solved twice by the rules (as is, and via `stoa.llm.to_english(force=True)`, one local call). Agree → keep;
  same element kind but different value → English reading (the raw parse missed an operator/unit word) ≤ 0.75; raw
  found no element kind → English ≤ 0.75; different element kinds → the parser's own reading for dataset languages
  (`PARSER_LANGS`) ≤ 0.6–0.75, else English ≤ 0.5. The LLM fallback runs at most once, after the choice
  (`_llm_stage`). `translate=0` turns it off. Probe: `experiments/w1/probes/c5_ml.py` + `experiments/w1/ml_run.py`.
- **Several buildings** (`buildings_of`, `main_building`, `own_storeys`): neighbour/context buildings with storeys
  of the same names (IFC-Bench city_house_munich). A named storey = the main building's level; "the building" =
  the main building; storey counts / which-storey / top floor range over the main building; conf ≤ 0.75.
- **Multi-part questions** (`_multi_part`): when the two-questions guard fires, one local-LLM call splits the
  question into self-contained parts, the rules answer each, the answer is the parts joined as text.
- Door width/height swapped on some instances of a type → read transposed; "how many different X types" = count;
  storeys above/below a named storey; basement / underground level by name (else highest storey below 0); datum
  elevations (no storey at 0) for above/below ground; area-zone spaces left out of "largest room"; vertical
  distance between two named storeys = elevation difference. Probes: `experiments/w1/probes/c5_q2..q4.txt`.

## Numbers, rates, storey words, calibration (cycle 6, 08:11–09:00)
Fixes for red-team / teammate reports, each checked on probes written before the fix
(`experiments/w1/probes/c6_q1.txt` 22 Qs, `c6_q2.txt` 21 Qs on 4 models in en/de/nl/pl/et/fi; 43/43 right after,
also end to end through `pipeline`). ifc_models train/dev/hard/hard2 stay 100% with 0 answers changed.
- **Digit grouping** (`arith.ungroup`, applied in `text_of`): '1,200 euros' / '1.200 €' / "1'200 CHF" / '1 200 euroa' /
  '1,250.50' / '1.250,50' -> plain numbers. A comma + 3 digits groups, a dot + 3 digits groups only next to a
  currency or with several groups ('1.200 m' stays 1.2 m), a space only next to a currency. Was: 55.2 EUR at 0.92.
- **Rates and units**: '15 metres of wall per day' -> wall length / 15 = days (`Outer.rate`; was 'add 15');
  'a door takes 1.5 hours' -> h, '45 minutes' -> min, kg, l (`unit_word`); verb-final wording kept by translations
  ('if each door 450 euros costs').
- **Storey words**: two-storey yes/no ('Does A have more windows than B?' -> 'no (55 < 60)', ops gt2/lt2);
  unresolved ordinals ('7th floor' on a 5-storey model) -> 0.3; 'basement floor' (-1) no longer matches '1.OG';
  'KG' = basement; Finnish/Swedish/Polish/... basement words; unquoted storey pairs ('EG and 1.OG combined') summed.
- **Used floors** (`used_storeys`): storeys with a door, or rooms while not named roof/foundation. 'How many floors /
  storeys / levels' = used floors at 0.6, total IfcBuildingStorey count in `missing` (IFC-Bench smiley_west 'number of
  levels' gold 4 = used floors of 5; esplanades 5 of 7, duplex 2 of 4). 'top/lowest floor' for element questions =
  highest/lowest used floor (capped 0.85, skipped level named); 'elevation of the top storey' = the literal top level.
  'Which floor has the fewest X' ranks used floors only.
- **Calibration**: Qto ≠ shape cap 0.7 -> 0.85 (gold follows the explicit Qto, S0 D15 B; F's area probe 36 -> 68 of
  78 right answers at ≥0.8, 0 wrong); a few stairs nested in another stair -> 0.85 + raw count (count probe AUROC
  0.478 -> 0.957).
- **Cost**: the cross-language LLM check skips dataset wordings of train/dev/hard/hard2 (`_known_wording`): dev ifc
  LLM calls 152 -> 0, $0.027 -> $0.002 per 1k.
- **Plumbing fixtures**: 'plumbing fixture(s)' = sanitary kind; 'their respective counts' -> breakdown by type from
  the model (4351: 21 with GUIDs) instead of the fact-card LLM.
- Exclusions by quote position: storey 'Attic' vs room 'Attic (414B-…)' (W4); no 'exclusion NOT applied' line when
  the rest rule applied it.
- Later in the cycle: digits are ungrouped once in `solve()` outside quoted names (`ungroup_question`; 'wider than
  1,000 mm' was read as 1.0 mm); roof levels by whole word ('Dachgeschoss' is an attic floor: IFC-Bench 'number of
  levels' golds 4/4); `cable_tray` kind (carriers named tray/ladder/trunking, conduits left out); derived wordings
  (probe 4 `experiments/w1/probes/c6_derived.py`, 6 -> 10/10): '25% of the doors are replaced' = 25% of the count
  ('remain' = 75%), 'share of the openings on S are windows' = windows / (doors + windows) at 0.6, 'gets a lock
  costing 1,050 euros', 'weighs 35 kg'. Probe 3 (`c6_q3.txt`, 3 untuned IFC-Bench models, es/sv/cs) 15/15.
- Last hour: **plan vs model** (`_plan_vs_model`, Stoa point 4, Q v17): "in the model but not drawn on this plan"
  = storey elements minus the sheet's GlobalId-tagged ones (esplanades windows 55 - 52 = 3, all wholly outside the
  1.2 m cut plane, evidence = the 3 GUIDs), "do the plan and the model agree on the number of X on S" -> yes/no with
  both counts, "how many floor plan sheets" -> the model's plan files; bug 19 (a storey word beats a split part's
  'of the building model'); 'how high above the ground floor is the top floor' = elevation difference; 'how far is A
  above B' and 'is the floor-to-floor height … more than 3 m' (yes/no); Italian/other 'whole building' words; room
  labels typed without quotes ('Living (414B-19-001-002)', F's wording probe 125 -> 135/135).
Tests: `tests/test_ifc_c6.py`.

## Answers that are sets: room lists, storey sets, where a room is (cycle 7, 09:10–10:00)
Q's red-team v19 (list answers on the demo model) found 4 confident misses at 0.90–0.92; a fresh probe written before
fixing (`experiments/w1/probes/c7_lists.txt`, 28 Qs on esplanades / warmond / digitalhub / smiley, en/et/de, gold =
the model's own rooms and counts) had 12/28 right with 9 confident-wrong -> 28/28, 0 (pipeline end to end 38/38 incl.
10 later rows). Outputs: `$JUNCTION_SHARED/artifacts/W1/probes-c7/`.
- `room_filter(idx, question)`: the room set a question names outside quotes: a room label of the model written in
  the question (1–3 words, plural endings: 'ELUTUBA+KÖÖK rooms', 'Gruppenbüros', 'Kellerräume', 'the living
  rooms'), else a multilingual room type (`arith.ROOM_TYPES`: 'WCs' -> toilet). Threshold lists / counts / sums over
  every room of a storey now keep only that set ('Which ELUTUBA+KÖÖK rooms are smaller than 25 m²?' 34 -> 1 room).
  'Which bedrooms …' and German 'Welche … Räume/Gruppenbüros …' are threshold lists too.
- `_storey_select` (before the other rules): (1) **storey sets by a threshold**: 'Which floors have more than 55
  rooms?', 'How many floors have fewer than 42 doors?', 'Which floors have a total floor area of more than 860 m²?' ->
  each used storey with the same rule as 'How many X are on S?' / 'What is the <measure> of S?', keep those that pass
  (value names only the passing floors; the rest are in the assumptions). Confidence = 0.9 × the lowest of the
  passing floors and close calls (a floor far from the threshold cannot flip the set). (2) **where a room is**: 'On
  which floors is there a room called MAGAMISTUBA?', 'On which floor is the room SERVER?', "On which storey is the
  space 'LIFT'?" (was the sheet storey's room count 50 at 0.97), 'On which floor is the kitchen?' (type, 0.8).
- `rooms_named(idx, question)`: quoted name / 'called X' / 'room 117' -> exact LongName / Name / 'LongName (Name)',
  else all rooms with that label, else `room_filter`.
- `_plan_vs_model`: **which sheet shows a room** ('Which sheet shows the server room?' -> plan-01-1-korrus, storey
  '1.korrus', SERVER (117); evidence = the room's box on the sheet (GlobalId-tagged) + its GUID in the model) and
  **'Does this drawing show every window that the model has on S?'** (drawn ⊇ modelled: 'no: 52 of the 55 …; 3 lie
  wholly above/below the cut plane').
- Text: 'between 20 and 25 m2' (the upper bound was missing), the model's label in list texts.
No dataset question (0 of 3,034 non-test ifc_models / ifc_bench) uses these wordings; ifc_models train/dev/hard/hard2
0 answers changed; F's area (137) and count (301) probes 0 changed; c4–c6 probes (266) 0 changed. Tests:
`tests/test_ifc_c7.py`.
Later in cycle 7 (all probes written before fixing; outputs in `$JUNCTION_SHARED/artifacts/W1/probes-c7/`):
- **Ground floor role** (F 09:24, a confident-wrong class: smiley 'walls on the ground floor' = whole model 281 @ 0.97):
  `parse.storey_mention` maps 'ground floor / ground level / Erdgeschoss / rez-de-chaussée / pohjakerros …' to a
  storey NAMED so (EG, Erdgeschoss, GF, RDC, Begane grond, E00…), else `_repair_intent` picks the floor with rooms or
  doors nearest elevation 0 (≤ 0.85; esplanades '1.korrus', clinic 'First Floor', warmond '1. Level'), else cap 0.5.
  'above/below ground level' is a reference height (`ground_reference`), not the role. 13-Q probe on 9 models: 6
  confident-wrong -> 13/13; F's storey-role probe 114/114.
- **2D on another storey's sheet**: a question about storey S asked on the sheet of T is boxed and cross-checked on S's
  own plan (it compared with T's drawing and lowered right answers to 0.75).
- **Links** (Q v20, R1's kg probe): 'does this drawing not show', German/French/Finnish/Estonian agree words
  ('stimmen … überein', 'même nombre … maquette'), sheet of a storey ('Which sheet is the floor plan of 3.korrus /
  shows the attic'), sheets in total (plans + sections + elevations), 'how many section / elevation drawings' and
  'is there a section drawing' (sibling files `<model>_section-*.pdf`), storeys without their own plan, 'more windows
  in the model than the plan shows', 'the plan shows doors the model assigns to other storeys'. Q v20 6/19 -> 24/24
  (19 + 5 own), R1 probe 11/21 with 4 confident-wrong -> 20/21, 0 (kg07 'another dataset' is R1's kg_qa).
- **Storeys with none of a kind**: 'Which storeys of the model have no rooms at all?' (0.85 when the class is used on
  other storeys, else 0.5).
- **Lists** (Q v24): excluded room types (`room_exclusions`: 'apart from the living rooms and kitchens', '… are not
  living rooms', 'except the bedrooms'), list questions after a leading clause, ties name every room equal to the
  centimetre ('largest room on Level 2' -> 4 bedrooms).
- **Two questions in any language** (`_two_q`): 'Montako ovea ja montako ikkunaa …' (the translation merged them into a
  sum); the original wording is split when the translation lost the second question.
- `factcard.answer_free_text` uses `llm.text_backend()` (S0 D21; inert unless `STOA_TEXT_BACKEND=local2`).
Every step: ifc_models train/dev/hard/hard2 0 answers changed; 0 of 3,882 dataset IFC questions match the new patterns.

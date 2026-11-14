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
Tests: `tests/test_ifc_c6.py`.

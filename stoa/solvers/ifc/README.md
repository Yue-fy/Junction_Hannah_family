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

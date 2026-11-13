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

2D cross-checks (`stoa.kg`): the ifc_models sheets are horizontal cuts at storey floor + 1.2 m and draw every
element crossing that plane, of any storey. Checks compare like with like (`_cut_compare`: elements of the
storey that cross the plane vs drawn elements of that storey; 244/268 plan x class rows equal) and explain the
rest (lintel walls above the cut, the next floor drawn on a basement sheet). `ok=None` = no 2D data.

Options (`--solver-arg`):
- `qto=0` ignores Qto and uses geometry only (accuracy measured per kind: volume 69–85%, length 62%, side area 43%).
- `plan2d=0` turns off the 2D boxes.
- `llm=0` turns off the LLM fallback (the solver then refuses free text).

Pitfalls are in KNOWLEDGE.md (W1 entries).

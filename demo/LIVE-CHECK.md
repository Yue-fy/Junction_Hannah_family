# Demo pre-flight check

Run `20261114-040906-pipeline-live_questions-12ae` on night 0589ce3, 04:09 14 Nov, shared GPU busy (other agents' evals).
Re-run before the pitch: `$JUNCTION_VENV/bin/python -m stoa.eval --solver pipeline --split demo/live_questions.jsonl --no-leaderboard --workers 4`.

| kind | question | answer | gold | ok | conf | solver | boxes | latency |
|---|---|---|---|---|---:|---|---:|---:|
| ifc | What is the net floor area of the room 'KORIDOR (119)' on '1.korrus', in m²? | 63.841 m2 | 63.84 | ✓ | 0.99 | ifc | 2 | 1.3 s |
| ifc-live-typed | how many doors on the first floor (1.korrus)? | 46 count | 46 | ✓ | 0.98 | ifc | 92 | 1.3 s |
| ifc | How many doors are shown on the floor plan of '1.korrus'? | 46 count | 46 | ✓ | 0.99 | ifc | 92 | 1.3 s |
| vector | How many doors (interior doors and entrance doors together) are drawn on this fl | 36 count | 36 | ✓ | 0.99 | dxf | 36 | 0.3 s |
| vector | Wie viele Türen und Fenster sind insgesamt auf diesem Grundriss eingezeichnet? | 64 count | 64 | ✓ | 0.98 | compose | 64 | 1.0 s |
| vector | What is the net floor area of apartment B in m², summing all its rooms except ba | 80.83 m2 | 80.83 | ✓ | 0.99 | dxf | 7 | 0.0 s |
| vector-live-typed | how many doors are on this plan? | 36 count | 36 | ✓ | 0.99 | dxf | 36 | 2.2 s |
| vector-live-typed | How big is apartment B? | 80.83 m2 | 80.83 | ✓ | 0.80 | dxf | 7 | 1.2 s |
| raster | Kuinka monta makuuhuonetta (MH) pohjapiirustuksessa on? | 3 count | 3 | ✓ | 0.86 | vlm_lora | 3 | 3.2 s |
| raster | How many toilet bowls (WC seats) are drawn on this floor plan? | 2 count | 2 | ✓ | 0.88 | vlm_lora | 5 | 1.4 s |
| raster | How many saunas are on this floor plan? | 1 count | 1 | ✓ | 0.78 | vlm_lora | 0 | 0.9 s |
| ifc-live-typed | how big is the corridor KORIDOR (119) on 1.korrus? | KORIDOR (119) on 1.korrus has a net floor …  | 63.84 | ✗ | 0.30 | ifc | 1 | 9.7 s |
| raster-catch-miss | How many saunas are on this floor plan? | 0 count | 1 | ✗ | 0.78 | vlm_lora | 0 | 0.7 s |
| schedule | On sheet A-801 of the Xcel Sports Complex drawings, what is the area of room 122 | 3814.0 ft2 | 3814 | ✓ | 0.85 | schedule | 1 | 8.3 s |
| raster-live-typed | How many bedrooms does this apartment have? | 3  | 3 | ✓ | 0.86 | agent | 3 | 14.6 s |
| ifc-derived | If each door costs 450 euros, what do all the doors on '1.korrus' cost in total? | 20700.0 EUR | 20700 | — | 0.89 | agent | 6 | 18.1 s |

Notes:
- `raster-catch-miss` is meant to be wrong (the LoRA says 0 saunas, gold 1): it is the "Show where" step.
- `ifc-derived` (450 € per door) is now answered by the **agent first** (W4's derived-quantity routing): 3 steps (ask doors on '1.korrus' → 46; calc 46 × 450; answer 20,700 EUR) and the IFC rules give the same 20,700 (cross-check ✓). 18 s on a busy GPU (3 local LLM calls); W5's tour text says "0 model calls", which was true for an earlier night.
- **Don't type "how big is …" on the IFC drawing**: it is not parsed as an area question (red-team bug 7) and comes back as a text answer at conf 0.30 (the number in the text, 63.8 m², is right). Use the template wording. "How big is apartment B?" on the Swiss plan works (dxf, conf 0.80).
- "How many bedrooms does this apartment have?" works but goes through the agent (14.6 s); the Finnish template wording takes 3.2 s.

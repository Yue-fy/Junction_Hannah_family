# Related work (R1)

The pitch's "related work". One line on what each item is, one on how it helps us, then link, licence and effort.
Unless an item is marked otherwise, its link was opened during the survey (23:35–23:50, 13 Nov 2026).
"(snippet)" means the item was seen only in search results. arXiv `abs` pages were unreachable from the
box, so many links point to the `html` versions.

## 1. VLMs on construction drawings: what they can and can't do

| Item | What | How it helps us | Link | Licence | Effort |
|---|---|---|---|---|---|
| AECV-Bench (Jan 2026) | Counting on 120 floor plans, plus 192 drawing-QA pairs | Frontier VLMs read drawing text well (OCR-style QA up to ~0.95) but score only ~0.09–0.39 exact-match on door/window counts. Use them for reading text and routing, not for counting symbols. | github.com/AECFoundry/AECV-Bench · arxiv.org/abs/2601.04819 | no LICENSE file | L |
| DrawingVQA (Jul 2026) | 92 expert QA pairs on 33 structural IFC (issued-for-construction) sheets, at 3 reasoning depths | Gemini-2.5-pro 71.7% vs professionals 94.9%. The bottleneck is reasoning across sheets, which needs retrieval of the right sheet plus cross-reference resolution (our knowledge-graph idea). | alphaxiv.org/abs/2607.15418 | no data link found | L |
| ArchSIBench (May 2026) | 3,000 multiple-choice spatial-reasoning questions on plans and sections | The best model (77.9) is still below non-architect humans. Spatial reasoning belongs in geometry code. | huggingface.co/datasets/ArchSIBench/ArchSIBench | Apache-2.0 | L |
| Aliyev & Barsi 2026 | VLM room-area estimation on 100 plans | VLMs get MAPE ≈ 43%; simple pixel counting gets 1.58% per plan. Never let a VLM compute an area. | pp.bme.hu/ci/article/view/44138 | open access | L |
| AECBench (Tongji 2025) | 4,800 text-only AEC knowledge questions | LLMs are weak at multi-step calculation, so arithmetic belongs in code | github.com/ArchiAI-LAB/AECBench | CC BY-NC 4.0 | L |
| DocVQA, InfographicVQA, ChartQA | Standard document, infographic and chart QA sets | Borrow ANLS and answer normalisation for free-text answers | arxiv.org/abs/2007.00398 · arxiv.org/abs/2104.12756 · arxiv.org/abs/2203.10244 | various | L |

Not found in any search: "BlueprintQA", "ArchCAD-QA", "DrawingQA". "CAD-VQA" (arXiv 2409.02253) is about
mechanical 3D parts, so it's off-domain.

## 2. BIM/IFC question answering

| Item | What | How it helps us | Link | Licence | Effort |
|---|---|---|---|---|---|
| IFC-Bench v2 + "cobbie" (TUM, arXiv 2605.01698, May 2026) | 1,027 QA pairs over 21–22 projects: retrieval 152, aggregation 569, geometric/spatial 112, incomplete-information 194. Judged by an LLM on abstention, faithfulness, completeness, transparency and relevance. | This is our `ifc_bench` source. Their iterative agent (write IfcOpenShell code, run it, refine) scored 56.0% vs 19.1% for one-shot code. The incomplete-information category matches Stoa's "you know what you don't know". | huggingface.co/datasets/sylvainHellin/ifc-bench · github.com/sylvainHellin/cobbie | CC BY 4.0 (4 models GPLv3) | L |
| ifcmcp (official, in IfcOpenShell; PyPI `ifcopenshell-mcp`) | MCP server with tools such as `ifc_select`, `ifc_relations`, `ifc_quantify`, `ifc_plot` | A ready tool layer for an IFC agent (Stoa: "reuse existing resources"). `ifc_plot` renders 2D views we can show as evidence. | pypi.org/project/ifcopenshell-mcp · github.com/IfcOpenShell/IfcOpenShell | LGPL-3.0+ | L |
| MCP4IFC (Rostock, Oct 2025) | 50+ IFC tools, with a Blender/Bonsai bridge | 83.1% on querying (a 65-task subset of IFC-Bench v1) | arxiv.org/html/2511.05533v1 | code licence unverified | M |
| IfcLLM (UNSW 2026) | IFC loaded into SQLite (16 tables) plus a Neo4j room/door/stair graph; an agent routes each query to SQL or Cypher and retries up to 5 times | 96% on 30 queries. Its failure-mode list (hallucinated schema, result overflow, silent semantic errors) is a ready red-team checklist. | arxiv.org/html/2605.13236 | unverified | M |
| Graph-RAG from IFC (BCU, Apr 2025) | IfcOpenShell → Neo4j; GPT-4o writes Cypher | Fails on multi-hop questions, so keep the graph shallow and the tools typed | arxiv.org/pdf/2504.16813 | no code | M |
| BIM-GPT (Stanford 2023) | Prompted query classification + retrieval, 99.5% on classification | The classic baseline for routing questions | arxiv.org/abs/2304.09333 | – | L |
| Bonsai MCP | MCP bridge to a live Blender+Bonsai session | Viewer screenshots as evidence (demo only) | github.com/JotaDeRodriguez/Bonsai_mcp | MIT | M |

## 3. What "net floor area" means: area standards

The norm texts are paywalled; these come from secondary sources (links in the survey notes). Our swiss data
behaves like the SIA rules below (see `methods.md` §4).

- **SIA 416 (CH):** GF = NGF + KF, and NGF = NF (HNF + NNF) + VF + FF.
  - KF holds walls, columns and small shafts; it is outside NGF. Corridors and stairwells are VF, inside NGF.
  - Balconies, loggias and terraces are outside GF (AGF).
- **DIN 277:2021 (DE):** NRF = NUF + TF + VF. Measured as clear dimensions at floor-finish level.
  - Shafts and niches ≤ 1 m² go to KGF and are excluded. Stairs are projected and assigned to the storey above.
  - Balconies are reported separately, as NRF(S).
  - Source: bauprofessor.de.
- **Finland, huoneistoala (SFS 5139 / RT 12-10277):** measured to the apartment-side faces of the enclosing walls.
  - Load-bearing and fire walls are excluded; non-load-bearing partitions are included.
  - Space below 1.6 m height is excluded. An internal stair is counted n−1 times.
  - Source: sanastot.suomi.fi, concept c932.
- **IPMS (RICS, 2023):** measured to the Internal Dominant Face. Internal walls and columns are not deducted.
  - Voids are excluded except at their lowest level. Balconies are reported separately.
- **ANSI/BOMA Z65.1:** major vertical penetrations (stairs, lifts, multi-floor shafts) are excluded from rentable area.

Takeaway: "net floor area" is a parameter, not a fact. An answer should name its standard and list what it
excluded, as `Answer.assumptions`.

## 4. Scale recovery from drawings (historical scans, PDFs without scale)

| Item | Method | How it helps us | Link | Licence | Effort |
|---|---|---|---|---|---|
| Talebi-Kalaleh & Mei, arXiv 2608.17237 (Aug 2026) | Pair each OCR'd dimension string with its dimension line (≤ 12 mm, ≤ 6°, terminators at both ends). Each pair gives a ratio D/d. Reject outliers by MAD, then snap to the nearest of 15 standard scales if within 1.5%. A manual 2-point calibration overrides; the fallback is 1:100 at zero confidence. | A complete, copyable recipe for scans | arxiv.org/html/2608.17237 | no code | M |
| Gautam et al., arXiv 2607.00015 | OCR "1:N" + PDF page size + DPI → shoelace areas | Simplest path for vector PDFs | arxiv.org/html/2607.00015 | CC BY 4.0 | L |
| Liang, Fukuda & Yabuki, EC3 2026 | OCR + segmentation → metric grid from the annotations (strict OCR accuracy 90.2%) | Links each dimension to the element it measures | ec-3.org/wp-content/uploads/2026/08/EC32026_212.pdf | – | M–H |
| "Robust DL-based scale inference", ASCE (snippet) | YOLOv7 finds dimension lines, EasyOCR reads them, and a vote picks the pixel resolution | The voting idea | ascelibrary.com/doi/10.1061/9780784485248.087 | – | M |
| US patent 10395147 | scale = OCR'd room area ÷ room pixel area | A cheap cross-check when plans print m² labels, which some cubicasa plans do | patent | – | L |

## 5. Symbol counting on raster plans (cubicasa windows, doors, WC seats, sinks, showers/bathtubs)

| Item | What | How it helps us | Link | Licence | Effort |
|---|---|---|---|---|---|
| AECV-Bench counting results [V] | Exact-match accuracy, door / window / bedroom / toilet. Gemini 3 Pro: 0.39 / 0.34 / 0.89 / 0.82. GPT-5.2: 0.28 / 0.27 / 0.91 / 0.76. Qwen3-VL-8B: 0.09 / 0.10 / 0.76 / 0.81. | Asking a VLM "how many doors" fails even for frontier models, so count with pointing or detection. Rooms and bedrooms are easy because they are read from labels (matches our +41 pts on bedrooms). | github.com/AECFoundry/AECV-Bench | no LICENSE | – |
| GeCo2 (AAAI 2026, arXiv 2511.08048) [V] | Exemplar-based counting built for small, dense objects, with no upscaling or tiling heuristics | Give 1–3 exemplar boxes of a window/door symbol and get all its repeats as boxes (evidence) | arXiv 2511.08048; weights on HF and Drive | MIT | M |
| GeCo / DAVE / LOCA (NeurIPS 2024 / CVPR 2024 / ICCV 2023) [V] | Low-shot counters with released weights | GeCo2 fallbacks | – | MIT | M |
| CountGD (NeurIPS 2024) [V] | Counting prompted by text plus visual exemplars, 1.2 GB weights | "toilet" text + one exemplar crop | – | MIT | M |
| SAM 3 (arXiv 2511.16719) [V] | Segmentation prompted by text or exemplar | Instance masks as evidence | facebookresearch/sam3 | SAM License, gated | M |
| T-Rex2 / Rex-Omni [V/U] | Visual-prompt counting | T-Rex2 is API-only (IDEA licence); Rex-Omni's licence is unverified | – | – | – |
| Molmo2 (arXiv 2601.10611) [V] | VLM with native pointing; points in 0–1000 coordinates | One point per object = count + evidence. Trained on PixMo-Points (ODC-BY). | – | Apache-2.0 weights (card notes NC third-party training data) | L–M |
| Qwen3-VL (our server) [V] | Box and point grounding in 0–1000 coordinates; the tech report covers direct, box-based and point-based counting | Already served on :8001 | – | Apache-2.0 | L |
| ViCrop (ICLR 2025, arXiv 2502.17422) [V] | Shows that the size of the target detail limits MLLM accuracy; training-free cropping fixes much of it | Supports upscaling and tiling of 700 px plans | – | – | L |
| LVLM-COUNT (arXiv 2412.00686) [S] | Divide and conquer for VLM counting, guarding against objects cut at tile borders | The tiling and de-duplication recipe (`methods.md` §3) | – | – | L |
| SAHI (obss/sahi) [V] | Sliced inference for detectors (ultralytics, HF, mmdet, GroundingDINO) | Drop-in tiling + merge for any detector | github.com/obss/sahi | MIT | L |
| CubiCasa5K multi-task model [V] | Room + icon segmentation; icon IoU: window 66.8, door 53.6, toilet 62.8, sink 55.7, bathtub 26.7. **No shower class.** | **Measured tonight (R1, §3a of methods.md):** on cc5k_heldout, connected components of the icon map beat the prior by +15 to +30 pts (windows 34%, doors 40%, WC 76%, sinks 60%), CPU ~1 s/plan. Trained on 84% of our drawings (original train list); D3: report only on `cc5k_heldout`. Paper: Kalervo et al., "CubiCasa5K: A Dataset and an Improved Multi-Task Model for Floorplan Image Analysis", SCIA 2019, arXiv 1904.01920. | github.com/CubiCasa/CubiCasa5k | CC BY-NC | M |
| Later CubiCasa work [S] | MuraNet (arXiv 2309.00348, YOLOX-style door/window detector), FGSSNet (arXiv 2507.10343), PCP-Net (2026, room mIoU 71.3), Raster2Seq (arXiv 2602.09016) | Same leakage caveat as the official model | – | – | – |

## 6. Symbol spotting on vector CAD (for DXF/PDF without clean layers)

Panoptic quality (PQ) on FloorPlanCAD, from ArchCAD Table 2 [V]. All are trained on Chinese CAD conventions.
Our swiss DXFs don't need these, because their layers are clean.

| Method | PQ | Code / licence | Weights |
|---|---|---|---|
| CADTransformer (CVPR 2022) | 68.9 | MIT | not released |
| GAT-CADNet (CVPR 2022) | 73.7 | none found | – |
| SymPoint (ICLR 2024) | 83.3 | IDEA licence, NC research | OneDrive |
| SymPoint-V2 | 90.1 (with layer priors) / 83.2 | no LICENSE | Drive |
| CADSpotting (arXiv 2412.07377) | 88.9 | not found | – |
| DPSS (ArchCAD, NeurIPS 2025) | 89.5 | released | unclear |
| VecFormer (NeurIPS 2025, WesKwong/VecFormer) [S] | 91.1 | Apache-2.0 | not listed |

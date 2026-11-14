# Expert workbench

One web page for a domain expert (human in the loop) to check our answers, add hard questions, and write
physics/sanity rules. FastAPI + plain HTML/JS/CSS (no build step). Owner: agent H.

    workbench/restart.sh                       # (re)start on 127.0.0.1:8200, log in $JUNCTION_SHARED/logs/workbench.log
    PORT=8299 WORKBENCH_HUMAN_DIR=/tmp/x/human workbench/restart.sh   # a test instance that never touches the expert's files
    $JUNCTION_VENV/bin/python -m pytest -q workbench

| Tab | What the expert does | Written to `$JUNCTION_SHARED/human/` |
|---|---|---|
| 1 Check our answers | sees a drawing with our evidence boxes (zoom/pan), the question, our answer + confidence, the reference; ✓ / ✗ / ? (+ comment) | `audit.jsonl` |
| 2 Add a hard question | picks any non-test drawing (dev drawings + historical scans), writes a question + answer + method + sureness; measures lengths/areas (scale by 2 clicks or printed 1:N); marks boxes; "Ask our system" runs the pipeline | `questions.jsonl` (eval split `human`) |
| 3 Physics & sanity rules | min/max/unit/why + free-text uncertainty rules; each rule is tested live on our newest full dev run | `rules.jsonl` |

**After the noon reveal (Stoa's examples):** put them in a jsonl (`{"path", "question", "answer"?}`; paths may be
outside the dataset), run `python -m stoa.eval --solver pipeline --split <file> --no-leaderboard`, then
`python -m workbench.batch <predictions file or run id> --name stoa --label "Stoa's example questions" --ref-label Stoa`.
The page shows "Load N items" at once; drawings outside the dataset are copied into `human/drawings/`. Items without
a reference answer get the expert's verdict as their reference (rows with `origin: "audit"` in `questions.jsonl`, scored
by `--split human`). Tab 2 also takes uploads ("Add your own drawing…": PDF/PNG/JPEG/TIFF/WebP ≤ 60 MB → `human/drawings/`).
REPORT.md shows the median time to verify (item shown → verdict).

Other files: `audit_items.jsonl` (the audit sample, `python -m workbench.precompute`), `audit_items_more.jsonl` (an optional
harder batch from `hard2`, loaded by a button when the first batch is done), `REPORT.md` (`python -m workbench.report`,
rebuilt after every save), `RULES_CHECK.md` (`python -m workbench.rules_check [PRED.jsonl]`). Schemas: `human/README.md`.

Safety: only drawing files (raster, PDF, SVG) under `$STOA_DATA/data` or directly in `$JUNCTION_SHARED/human/drawings/`
(flat, no sub-folders, no dot-files) are rendered, to PNG/JPEG in
`$JUNCTION_SHARED/artifacts/H/cache`; `..`, absolute paths and other files get 400; drawings of the sealed `test` split are
hidden and refused. No `/docs`. URLs are relative, so the page also works behind a path prefix (keep the trailing `/`).

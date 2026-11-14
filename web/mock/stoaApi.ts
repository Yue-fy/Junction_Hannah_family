/**
 * Vite dev/preview middleware for `/api/*`.
 *
 * Every request first goes to W4's real API (STOA_API_URL, default http://127.0.0.1:8100, path without
 * the `/api` prefix). If that server is down (connection refused) — or for an endpoint it doesn't have
 * yet (404/405 on GET /questions, /kg, /files) — a local mock answers instead, built from the dataset on
 * disk (STOA_DATA) and the fixture Answers in `fixtures/answers.json`. The response header
 * `X-Stoa-Backend: live|mock` tells the UI which one answered.
 *
 * `/api/file` is always served straight from disk when STOA_DATA is set (same bytes, no proxy hop).
 * `/api/kg` falls back to running W1's `stoa.kg.links(path)` with the shared venv (backend "kg").
 */
import fs from "node:fs";
import { execFile } from "node:child_process";
import { createHash } from "node:crypto";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import type { Connect, Plugin } from "vite";

const DATA = process.env.STOA_DATA ?? "/home/fangy4/work/projects/junction-data/stoa-full/junction-dataset";
const LIVE = process.env.STOA_API_URL ?? "http://127.0.0.1:8100";
const FIXTURES = path.resolve(__dirname, "../fixtures/answers.json");

type Q = { path: string; question: string; answer?: unknown; unit: string | null; type: string };
type LicenceInfo = { license: string; credit: string; title?: string; url?: string };

const MIME: Record<string, string> = {
  ".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
  ".svg": "image/svg+xml", ".ifc": "application/octet-stream", ".dxf": "application/dxf", ".json": "application/json",
};

// Curated demo files first (train split / demo-safe; see board W5 + KNOWLEDGE).
const DEMO = [
  "data/ifc_models/bsc-esplanades_1807-ep-ar-v18_plan-01-1-korrus.pdf",
  "data/swiss_dwellings/site1000_bldg2082_floor9385.pdf",
  "data/opening_design/Sports_Complex/Sheets - Current Set/A-801 - Door and Finish Schedules & Wall Types.pdf",
  "data/cubicasa5k/colorful-10052.png",
];

let questions: Q[] | null = null;
function loadQuestions(): Q[] {
  if (questions) return questions;
  const f = path.join(DATA, "questions.jsonl");
  questions = fs.existsSync(f)
    ? fs.readFileSync(f, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l) as Q)
    : [];
  return questions;
}

let byPath: Map<string, Q[]> | null = null;
function questionsByPath(): Map<string, Q[]> {
  if (byPath) return byPath;
  byPath = new Map();
  for (const q of loadQuestions()) {
    const l = byPath.get(q.path) ?? [];
    l.push(q);
    byPath.set(q.path, l);
  }
  return byPath;
}

const licences = new Map<string, { all?: LicenceInfo; files: Map<string, LicenceInfo> }>();
function licenceFor(rel: string): LicenceInfo {
  const source = rel.split("/")[1];
  if (!licences.has(source)) {
    const entry = { all: undefined as LicenceInfo | undefined, files: new Map<string, LicenceInfo>() };
    const f = path.join(DATA, "data", source, "LICENSE.md");
    if (fs.existsSync(f)) {
      for (const line of fs.readFileSync(f, "utf8").split("\n")) {
        const all = line.match(/^All files: (\S+?)\. Credit: (.*)$/);
        if (all) entry.all = { license: all[1], credit: all[2] };
        const row = line.match(/^\| (.+?) \| (.*?) \| (.*?) \| (.*?) \| (.*?) \|$/);
        if (row && row[1] !== "file" && !row[1].startsWith("---"))
          entry.files.set(row[1], { title: row[2], license: row[3], credit: row[4], url: row[5] });
      }
    }
    licences.set(source, entry);
  }
  const e = licences.get(source)!;
  const inSource = rel.split("/").slice(2).join("/");
  return e.files.get(inSource) ?? e.files.get(path.basename(rel)) ?? e.all ?? { license: "see LICENSE.md", credit: source };
}

function safeAbs(rel: string): string | null {
  if (!rel.startsWith("data/") || rel.includes("..")) return null;
  const abs = path.join(DATA, rel);
  return abs.startsWith(path.join(DATA, "data")) && fs.existsSync(abs) ? abs : null;
}

/** Same-drawing siblings: same stem, other extension; ifc_models plans → parent model `.ifc`. */
function siblings(rel: string): Record<string, string> {
  const dir = path.dirname(rel);
  const ext = path.extname(rel);
  const stem = path.basename(rel, ext);
  const out: Record<string, string> = {};
  for (const e of [".pdf", ".svg", ".png", ".jpg", ".dxf", ".ifc"]) {
    if (e === ext) continue;
    if (safeAbs(`${dir}/${stem}${e}`)) out[e] = `${dir}/${stem}${e}`;
  }
  const m = stem.match(/^(.*?)_(plan|section|elevation)-/);
  if (rel.startsWith("data/ifc_models/") && m && safeAbs(`${dir}/${m[1]}.ifc`)) out[".ifc"] = `${dir}/${m[1]}.ifc`;
  return out;
}

function fileInfo(rel: string) {
  const lic = licenceFor(rel);
  return {
    path: rel, source: rel.split("/")[1], ext: path.extname(rel).toLowerCase(), siblings: siblings(rel),
    n_questions: questionsByPath().get(rel)?.length ?? 0, license: lic.license, credit: lic.credit,
    title: lic.title ?? "", source_url: lic.url ?? "",
  };
}

/** Directory-based links (fallback when stoa.kg is not available): siblings + other sheets/floors of the set. */
/** What a historical sheet shows, from its title in data/<source>/LICENSE.md ("…, North Elevation - Creque …"). */
function sheetLabel(rel: string) {
  const t = licenceFor(rel).title ?? "";
  const head = t.split(" - ")[0].trim();
  const sheet = head.match(/\(sheet (\d+ of \d+)\)/);
  if (sheet) return `sheet ${sheet[1]}`;
  return head.length > 48 ? `${head.slice(0, 46)}…` : head;
}

function kgFromDisk(rel: string) {
  const files: { path: string; kind: string; storey: string | null; relation: string; label?: string }[] = [];
  const add = (p: string, kind: string, relation: string, label?: string) => {
    if (p !== rel && !files.some((n) => n.path === p)) files.push({ path: p, kind, storey: null, relation, ...(label ? { label } : {}) });
  };
  const sib = siblings(rel);
  for (const [e, p] of Object.entries(sib)) {
    add(p, e === ".ifc" && rel.startsWith("data/ifc_models/") ? "model" : "sibling",
      e === ".ifc" && rel.startsWith("data/ifc_models/") ? "model this sheet was cut from"
        : e === ".svg" ? "same sheet, vector with IFC GlobalIds" : e === ".dxf" ? "same drawing, CAD layers" : "same drawing, other format");
  }
  if (rel.startsWith("data/ifc_models/")) {
    const model = (sib[".ifc"] ?? rel).replace(/\.(ifc|pdf|svg)$/, "").replace(/_(plan|section|elevation)-.*$/, "");
    const base = path.basename(model);
    for (const f of fs.readdirSync(path.join(DATA, "data/ifc_models")))
      if (f.startsWith(base + "_") && f.endsWith(".pdf"))
        add(`data/ifc_models/${f}`, f.includes("_plan-") ? "plan" : f.includes("_section-") ? "section" : "elevation",
          f.includes("_plan-") ? "other storey plan" : "section / elevation");
  }
  if (rel.startsWith("data/swiss_dwellings/")) {
    const site = path.basename(rel).split("_")[0];
    for (const f of fs.readdirSync(path.join(DATA, "data/swiss_dwellings")))
      if (f.startsWith(site + "_") && f.endsWith(".pdf")) add(`data/swiss_dwellings/${f}`, "floor", "other floor of the same site");
  }
  // historical scans: other sheets of the same HABS/HAER/HALS survey (file prefix = Library of Congress item), and
  // Finna drawings filed under the same address (title). Labels name the view from the catalogue title.
  if (rel.startsWith("data/habs/")) {
    const item = path.basename(rel).split("_sheet_")[0];
    const own = sheetLabel(rel).split(", ")[0] + ", "; // "Head House and Residence, " shared with the open sheet
    for (const f of fs.readdirSync(path.join(DATA, "data/habs")).sort())
      if (f.startsWith(item + "_sheet_")) {
        const l = sheetLabel(`data/habs/${f}`);
        add(`data/habs/${f}`, "sheet", "other sheet of the same survey (Library of Congress item)", l.startsWith(own) ? l.slice(own.length) : l);
      }
  }
  if (rel.startsWith("data/finna/")) {
    const title = licenceFor(rel).title;
    if (title) {
      licenceFor(rel); // loads the table
      const entry = licences.get("finna");
      const set = [...(entry?.files ?? [])].filter(([, info]) => info.title === title).map(([f]) => f).sort();
      set.forEach((f, k) => add(`data/finna/${f}`, "sheet", `drawing filed under the same address (${title})`, `drawing ${k + 1} of ${set.length}`));
    }
  }
  if (rel.startsWith("data/opening_design/")) {
    const dir = path.dirname(rel);
    for (const f of fs.readdirSync(path.join(DATA, dir)).sort().slice(0, 40))
      if (/\.(pdf|ifc)$/i.test(f)) add(`${dir}/${f}`, /\.ifc$/i.test(f) ? "model" : "sheet", "same drawing set");
  }
  return { path: rel, source: rel.split("/")[1], group: rel.split("/").slice(1, 3).join("/"), siblings: sib, files: files.slice(0, 40) };
}

/**
 * Knowledge graph for one file. W1's `stoa.kg.links(path)` (night-W1) via the API's GET /kg when it exists;
 * otherwise this middleware runs it itself with the shared venv (repo root, or STOA_KG_REPO = a checkout that
 * has stoa/kg); if that fails too, the directory-based links above. Cached per path.
 */
const KG_REPO = process.env.STOA_KG_REPO ?? path.resolve(__dirname, "../..");
const PY = process.env.JUNCTION_VENV ? `${process.env.JUNCTION_VENV}/bin/python` : "python3";
const kgCache = new Map<string, Promise<{ body: Record<string, unknown>; backend: string }>>();
/**
 * Room graph of a CubiCasa plan (R1, experiments/r1/room_graph/graph.py): rooms (class, printed label, ~m² with an
 * 80% band, box, centroid), doors and which rooms each links, open-plan links, windows. Read from R1's cached
 * pretrained-CubiCasa5K segmentation (live=False: never runs the network here); no LLM. Local only, cached per path.
 */
const ROOMS_PY = "import json,sys\nfrom experiments.r1.room_graph.graph import room_graph\ng = room_graph(sys.argv[1], live=False)\nprint(json.dumps(g))";
const roomsCache = new Map<string, Promise<Record<string, unknown> | null>>();
const ROOMS_REC = path.resolve(__dirname, "../fixtures/rooms.json"); // {path: graph}, written by fixtures/record.py
function roomGraph(rel: string) {
  if (!roomsCache.has(rel)) {
    roomsCache.set(rel, new Promise((resolve) => {
      execFile(PY, ["-c", ROOMS_PY, rel], { cwd: KG_REPO, timeout: 60_000, maxBuffer: 16 << 20, env: { ...process.env, STOA_DATA: DATA } },
        (err, stdout) => {
          let g: Record<string, unknown> | null = null;
          try {
            g = err ? null : JSON.parse(stdout);
          } catch {
            g = null;
          }
          if (!g) roomsCache.delete(rel);
          resolve(g);
        });
    }));
  }
  return roomsCache.get(rel)!;
}

const KG_PY = "import json,sys\nfrom stoa.kg import links\nprint(json.dumps(links(sys.argv[1])))";
function kg(rel: string) {
  if (!kgCache.has(rel)) {
    kgCache.set(rel, new Promise((resolve) => {
      execFile(PY, ["-c", KG_PY, rel], { cwd: KG_REPO, timeout: 120_000, maxBuffer: 64 << 20, env: { ...process.env, STOA_DATA: DATA } },
        (err, stdout) => {
          const disk = { ...kgFromDisk(rel), kg_error: "" };
          if (err) {
            disk.kg_error = String(err.message).split("\n").filter(Boolean).slice(-1)[0] ?? "stoa.kg failed";
            kgCache.delete(rel); // retry next time (e.g. after night merges stoa.kg)
            return resolve({ body: disk, backend: "mock" });
          }
          try {
            const body = JSON.parse(stdout) as Record<string, unknown>;
            // stoa.kg links only siblings for some sources: keep its data, add the directory links for those.
            if (!Array.isArray(body.files) || body.files.length === 0) body.files = disk.files;
            resolve({ body, backend: "kg" });
          } catch (e) {
            kgCache.delete(rel);
            resolve({ body: { ...disk, kg_error: String(e) }, backend: "mock" });
          }
        });
    }));
  }
  return kgCache.get(rel)!;
}

/**
 * Benchmark summary for the "How well it works" view: the latest full runs of the integrated pipeline and two
 * baselines (just ask the VLM; the per-template prior) on dev and on the hard (generality) split, read from
 * stoa.eval's leaderboard (STOA_LEADERBOARD, default $JUNCTION_SHARED/results/leaderboard.jsonl). Without it,
 * the committed snapshot fixtures/bench.json (refresh: curl localhost:5173/api/bench > web/fixtures/bench.json).
 */
const LEADERBOARD = process.env.STOA_LEADERBOARD
  ?? path.join(process.env.JUNCTION_SHARED ?? "/home/fangy4/work/projects/junction-shared", "results/leaderboard.jsonl");
const BENCH_SNAPSHOT = path.resolve(__dirname, "../fixtures/bench.json");
type Bucket = { n: number; scored_n?: number; correct?: number; accuracy?: number | null };
type LbRow = {
  time: string; run_id: string; solver: string; split: string; n: number; commit?: string; agent?: string; note?: string;
  solver_args?: Record<string, unknown> | null;
  limit?: number | null; sources?: unknown; types?: unknown; grep?: unknown; handled_only?: boolean;
  metrics: Record<string, unknown> & { by_bucket?: Record<string, Bucket>; errors?: number };
};
function bench() {
  if (!fs.existsSync(LEADERBOARD))
    return fs.existsSync(BENCH_SNAPSHOT) ? { ...JSON.parse(fs.readFileSync(BENCH_SNAPSHOT, "utf8")), from: "snapshot" } : null;
  const rows = fs.readFileSync(LEADERBOARD, "utf8").split("\n").filter(Boolean).flatMap((l) => {
    try {
      return [JSON.parse(l) as LbRow];
    } catch {
      return [];
    }
  });
  const full = (r: LbRow) => !r.limit && !r.sources && !r.types && !r.grep && !r.handled_only && !r.metrics.errors;
  // The pipeline rows come from the integration runs of S0 and F (both measure `night`-equivalent commits; other agents
  // also log runs of uncommitted work), all on ONE commit when possible: the commit of the latest full S0/F dev run
  // (since D14, S0 skips duplicate dev/hard runs and F's runs are the reference). Baselines: latest full run of anyone.
  const integ = (r: LbRow) => r.agent === "S0" || r.agent === "F";
  // S0's sealed test (experiments/s0/run_test.sh): only the CLEAN run counts (cc5k=0, or the single run when the
  // pipeline has no cc5k switch); the cc5k=1 run is labelled inflated (D8) and never shown as the headline.
  // Ablations (e.g. test-lora0: cc5k=0 + lora=0) are not the headline either: exactly {cc5k: 0}, or no args at all.
  const clean = (r: LbRow) => {
    const args = Object.keys(r.solver_args ?? {});
    if (/test-(lora|cc5k1)/i.test(r.note ?? "")) return false;
    if (/test-cc5k0\b/.test(r.note ?? "")) return true;
    return (args.length === 1 && String(r.solver_args?.cc5k) === "0") || (args.length === 0 && !/cc5k|lora/i.test(r.note ?? ""));
  };
  const tests = rows.filter((r) => r.solver === "pipeline" && r.split === "test" && r.agent === "S0" && r.n >= 500 && full(r) && clean(r));
  const test = tests.at(-1);
  const devOn = (commit?: string) => rows.some((r) => r.solver === "pipeline" && r.split === "dev" && r.n >= 1500 && full(r) && integ(r) && r.commit === commit);
  // ONE commit for every pipeline number: the sealed test's commit when dev was also run on it (the whole scorecard of
  // that milestone: dev, hard, hard2*, test), else the commit of the latest full S0/F dev run
  const anchor = test && devOn(test.commit) ? test.commit
    : rows.filter((r) => r.solver === "pipeline" && r.split === "dev" && r.n >= 1500 && full(r) && integ(r)).at(-1)?.commit;
  const pickPipeline = (ok: LbRow[]) => {
    const mine = ok.filter(integ);
    return mine.filter((r) => anchor && r.commit === anchor).at(-1) ?? mine.at(-1) ?? ok.at(-1);
  };
  const pick = (solver: string, split: string, minN: number) => {
    const ok = rows.filter((r) => r.solver === solver && r.split === split && r.n >= minN && full(r));
    return solver === "pipeline" ? pickPipeline(ok) : ok.at(-1);
  };
  const summary = (r: LbRow | undefined) => {
    if (!r) return null;
    const m = r.metrics;
    const bySource: Record<string, { n: number; correct: number; accuracy: number }> = {};
    for (const [k, b] of Object.entries(m.by_bucket ?? {})) {
      const scored = b.scored_n ?? b.n;
      if (!scored) continue; // text-only buckets are not scored
      const src = k.split("/")[0];
      const e = (bySource[src] ??= { n: 0, correct: 0, accuracy: 0 });
      e.n += scored;
      e.correct += b.correct ?? Math.round((b.accuracy ?? 0) * scored);
      e.accuracy = e.correct / e.n;
    }
    const keep = ["weighted_acc", "accuracy", "macro_accuracy", "usd_per_1k_q", "latency_p50_s", "latency_p95_s",
      "evidence_rate", "refusal_rate", "by_tier", "by_kind", "calibration", "cost_mean"];
    return {
      run_id: r.run_id, solver: r.solver, split: r.split, time: r.time, commit: r.commit, agent: r.agent, note: r.note, n: r.n,
      ...Object.fromEntries(keep.map((k) => [k, m[k] ?? null])), by_source: bySource,
    };
  };
  const out: Record<string, Record<string, unknown>> = {};
  for (const [split, minN] of [["dev", 1500], ["hard", 500]] as const)
    out[split] = { pipeline: summary(pick("pipeline", split, minN)), vlm_direct: summary(pick("vlm_direct", split, minN)),
      prior: summary(pick("prior", split, minN)) };
  // the same sealed test without R2's counting LoRA (run_test.sh "test-lora0": cc5k=0 + lora=0, same commit): shows what the
  // small fine-tuned model adds on data nobody has seen
  const lora0 = test && rows.filter((r) => r.solver === "pipeline" && r.split === "test" && r.agent === "S0" && full(r)
    && r.commit === test.commit && (/test-lora0\b/.test(r.note ?? "") || String(r.solver_args?.lora ?? "") === "0")).at(-1);
  // the previous sealed test on an earlier commit (test 1 before test 2): the overnight progress line
  const prev = test && tests.filter((r) => r.commit !== test.commit).at(-1);
  out.test = { pipeline: summary(test), ...(lora0 ? { no_lora: summary(lora0) } : {}), ...(prev ? { previous: summary(prev) } : {}) };
  // novel question kinds (operators no template covers): hard2 = developed on; hard2q = held-out rewording (D10, now
  // "worn"); hard2r = F's sealed fresh draw in a fourth wording (D12, the clean one). Aggregates only.
  // hard3 = sealed derived quantities (D15: ratios, differences, per-unit values). With a previous sealed test, the same
  // split on that test's commit (any agent: F logged hard3's test-1 baseline) shows how far the night moved them.
  for (const split of ["hard2", "hard2q", "hard2r", "hard3"]) {
    // the integration run on the same commit as dev/hard first (F logs a base and a candidate commit side by side)
    const was = prev && rows.filter((r) => r.solver === "pipeline" && r.split === split && r.n >= 100 && full(r) && r.commit === prev.commit).at(-1);
    out[split] = { pipeline: summary(pick("pipeline", split, split === "hard3" ? 100 : 200)), ...(was ? { previous: summary(was) } : {}) };
  }
  return { from: "leaderboard", generated: new Date().toISOString(), runs: out };
}

type Fixture = { path: string; question: string; answer: Record<string, unknown>; recorded_at?: string; solver?: string; solver_args?: Record<string, unknown> };
const RECORDED = path.resolve(__dirname, "../fixtures/recorded.json");
/** Recorded live-API answers (fixtures/record.py) first, then the hand-computed fixtures. */
function fixtures(): Fixture[] {
  const read = (f: string) => {
    try {
      return JSON.parse(fs.readFileSync(f, "utf8")) as Fixture[];
    } catch {
      return [];
    }
  };
  return [...read(RECORDED), ...read(FIXTURES)];
}
const norm = (s: string) => s.trim().toLowerCase().replace(/\s+/g, " ");

const solverKey = (solver?: string, args?: Record<string, unknown>) =>
  `${solver && solver !== "pipeline" ? solver : "pipeline"} ${JSON.stringify(Object.fromEntries(Object.entries(args ?? {}).sort()))}`;

function mockAsk(body: { path: string; question: string; solver?: string; solver_args?: Record<string, unknown> }) {
  const want = solverKey(body.solver, body.solver_args);
  const fx = fixtures().find((f) => f.path === body.path && norm(f.question) === norm(body.question)
    && solverKey(f.solver, f.solver_args) === want);
  if (fx) return { ...fx.answer, recorded_at: fx.recorded_at, trace: [...((fx.answer.trace as string[]) ?? []),
    fx.recorded_at ? `(mock API: replay of the live answer recorded ${fx.recorded_at})` : "(mock API: precomputed fixture)"] };
  return {
    value: null, unit: null, confidence: 0, evidence: [], solver: "mock",
    trace: ["mock API: no fixture for this question", "start W4's API on :8100 for live answers"],
    assumptions: [], missing: ["live API (stoa.api on port 8100) not reachable"],
    cost: { llm_tokens_in: 0, llm_tokens_out: 0, gpu_seconds: 0, api_calls: 0, llm_calls: 0, wall_seconds: 0 },
  };
}

function send(res: http.ServerResponse, status: number, body: unknown, backend = "mock") {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json");
  res.setHeader("X-Stoa-Backend", backend);
  res.end(JSON.stringify(body));
}

function readBody(req: http.IncomingMessage): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => resolve(Buffer.concat(chunks)));
    req.on("error", reject);
  });
}

/**
 * "Your own drawing": files a visitor uploads (PDF, PNG, JPG, IFC). Saved outside the repo and the dataset, in
 * STOA_UPLOADS (default: <tmp>/stoa-uploads/<sha256[:12]>/<name>), and known to the browser as the virtual path
 * `upload/<id>/<name>`. The API only accepts dataset paths, so questions about them run the pipeline here with the
 * shared venv (web/server/ask_upload.py, one process per question, ~0.3 s to load). Local only; cached per question.
 */
const UPLOADS = process.env.STOA_UPLOADS ?? path.join(os.tmpdir(), "stoa-uploads");
const UPLOAD_EXT = new Set([".pdf", ".png", ".jpg", ".jpeg", ".ifc"]);
const UPLOAD_MAX = 200 << 20;
const isUpload = (p: string | null | undefined) => !!p && p.startsWith("upload/");
// A declared drawing style (optional): the file is stored under ".../data/<style>/" so stoa.data.source_of() gives that
// source and the pipeline may use the readers trained on it (CubiCasa5K: the LoRA counter's gate, the symbol detector).
// The virtual path carries it: upload/<id>/cubicasa5k/<name>.
const UPLOAD_STYLES = new Set(["cubicasa5k"]);
function uploadAbs(virtual: string): string | null {
  const m = virtual.match(/^upload\/([0-9a-f]{12})\/(?:([a-z0-9_]+)\/)?([^/\\]+)$/);
  if (!m || m[3].startsWith(".") || (m[2] && !UPLOAD_STYLES.has(m[2]))) return null;
  const abs = m[2] ? path.join(UPLOADS, m[1], "data", m[2], m[3]) : path.join(UPLOADS, m[1], m[3]);
  return fs.existsSync(abs) ? abs : null;
}
function uploadInfo(virtual: string) {
  const ext = path.extname(virtual).toLowerCase();
  const style = virtual.split("/").length > 3 ? virtual.split("/")[2] : "";
  return { path: virtual, source: "upload", ext, siblings: { [ext]: virtual }, n_questions: 0, license: "your file", style,
    credit: "your upload: not in the dataset, kept only on this machine (temp folder)", title: path.basename(virtual), source_url: "" };
}
async function saveUpload(name: string, body: Buffer, style = "") {
  const safe = path.basename(name).replace(/[^\w.\- ()]+/g, "_").replace(/^\.+/, "").slice(-120) || "upload";
  const ext = path.extname(safe).toLowerCase();
  if (!UPLOAD_EXT.has(ext)) throw Object.assign(new Error(`only ${[...UPLOAD_EXT].join(", ")} files`), { status: 415 });
  if (!body.length || body.length > UPLOAD_MAX) throw Object.assign(new Error(`file is empty or over ${UPLOAD_MAX >> 20} MB`), { status: 413 });
  if (style && (!UPLOAD_STYLES.has(style) || ![".png", ".jpg", ".jpeg"].includes(ext))) style = "";
  const id = createHash("sha256").update(style).update(body).digest("hex").slice(0, 12);
  const dir = style ? path.join(UPLOADS, id, "data", style) : path.join(UPLOADS, id);
  fs.mkdirSync(dir, { recursive: true });
  const abs = path.join(dir, safe);
  if (!fs.existsSync(abs)) fs.writeFileSync(abs, body);
  return uploadInfo(style ? `upload/${id}/${style}/${safe}` : `upload/${id}/${safe}`);
}
const ASK_UPLOAD = path.resolve(__dirname, "../server/ask_upload.py");
const uploadAnswers = new Map<string, Promise<Record<string, unknown>>>();
function askUpload(b: { path: string; question?: string; solver?: string; solver_args?: Record<string, unknown> }, abs: string) {
  const key = JSON.stringify([b.path, (b.question ?? "").trim(), b.solver ?? "pipeline", b.solver_args ?? {}]);
  const hit = uploadAnswers.get(key);
  if (hit) return hit.then((a) => ({ ...a, cached: true }));
  const p = new Promise<Record<string, unknown>>((resolve, reject) => {
    const child = execFile(PY, [ASK_UPLOAD], { cwd: KG_REPO, timeout: 600_000, maxBuffer: 64 << 20, env: { ...process.env, STOA_DATA: DATA } },
      (err, stdout, stderr) => {
        if (err) return reject(new Error(`the solver failed on this file: ${String(stderr || err.message).trim().split("\n").slice(-1)[0]}`));
        try {
          resolve({ ...JSON.parse(stdout), cached: false });
        } catch (e) {
          reject(new Error(`unreadable answer: ${e}`));
        }
      });
    child.stdin?.end(JSON.stringify({ abs, virtual: b.path, question: b.question ?? "", solver: b.solver, solver_args: b.solver_args }));
  });
  uploadAnswers.set(key, p);
  p.catch(() => uploadAnswers.delete(key));
  return p;
}
/** Requests about an uploaded file, answered here (never forwarded: the API would refuse the path). */
async function handleUpload(req: Connect.IncomingMessage, res: http.ServerResponse, route: string, url: URL): Promise<boolean> {
  if (route === "/upload" && req.method === "POST") {
    try {
      const info = await saveUpload(url.searchParams.get("name") ?? "upload", await readBody(req), url.searchParams.get("style") ?? "");
      send(res, 200, info, "disk");
    } catch (e) {
      send(res, (e as { status?: number }).status ?? 500, { detail: (e as Error).message }, "disk");
    }
    return true;
  }
  if (route === "/files" && isUpload(url.searchParams.get("q"))) {
    const v = url.searchParams.get("q")!;
    send(res, 200, { files: uploadAbs(v) ? [uploadInfo(v)] : [] }, "disk");
    return true;
  }
  const p = url.searchParams.get("path");
  if (!isUpload(p) && !(route === "/ask" && req.method === "POST")) return false;
  if (route === "/file" && req.method === "GET") {
    const abs = uploadAbs(p!);
    if (!abs) return send(res, 404, { detail: "upload not found (uploads live in a temp folder)" }), true;
    res.setHeader("Content-Type", MIME[path.extname(abs).toLowerCase()] ?? "application/octet-stream");
    res.setHeader("X-Stoa-Backend", "disk");
    fs.createReadStream(abs).pipe(res);
    return true;
  }
  if (route === "/questions") return send(res, 200, { questions: [] }, "disk"), true; // the browser offers general ones
  if (route === "/kg") return send(res, 200, { path: p, nodes: [], checks: [], files: [] }, "disk"), true;
  if (route === "/rooms") return send(res, 404, { detail: "room graph: CubiCasa dataset plans only" }, "disk"), true;
  if (route === "/ask" && req.method === "POST") {
    const raw = await readBody(req);
    let b: { path?: string; question?: string; solver?: string; solver_args?: Record<string, unknown> } = {};
    try {
      b = JSON.parse(raw.toString() || "{}");
    } catch {
      /* empty */
    }
    if (!isUpload(b.path)) {
      (req as Connect.IncomingMessage & { stoaBody?: Buffer }).stoaBody = raw; // not ours: hand the body on
      return false;
    }
    const abs = uploadAbs(b.path!);
    if (!abs) return send(res, 404, { detail: "upload not found (uploads live in a temp folder): upload it again" }, "live"), true;
    try {
      send(res, 200, await askUpload(b as { path: string }, abs), "live");
    } catch (e) {
      send(res, 500, { detail: (e as Error).message }, "live");
    }
    return true;
  }
  return false;
}

let liveDownUntil = 0;
/** Forward to the live API. Resolves null when it is unreachable (→ mock). */
function forward(req: http.IncomingMessage, url: string, body: Buffer, waitMs = 600_000): Promise<{ status: number; headers: http.IncomingHttpHeaders; body: Buffer } | null> {
  if (Date.now() < liveDownUntil) return Promise.resolve(null);
  return new Promise((resolve) => {
    const u = new URL(url, LIVE);
    let late = false;
    const r = http.request(u, { method: req.method, headers: { "content-type": req.headers["content-type"] ?? "application/json" }, timeout: 600_000 }, (resp) => {
      const chunks: Buffer[] = [];
      resp.on("data", (c) => chunks.push(c));
      resp.on("end", () => resolve({ status: resp.statusCode ?? 500, headers: resp.headers, body: Buffer.concat(chunks) }));
    });
    r.on("error", () => {
      if (late) return; // we stopped waiting; the API itself is fine
      liveDownUntil = Date.now() + 5000;
      resolve(null);
    });
    // stop WAITING after waitMs (the request is left running, so the API still finishes and caches the answer)
    if (waitMs < 600_000) setTimeout(() => { late = true; resolve(null); }, waitMs);
    r.end(body);
  });
}

const liveUp = () => Date.now() >= liveDownUntil;

/** Hosted second opinions (NVIDIA, rate-limited and sometimes hanging for minutes, F 04:33): wait this long, then show
 * that model's recorded answer, labelled as such, instead of a spinner in front of the jury. */
const HOSTED_WAIT_MS = Number(process.env.STOA_HOSTED_TIMEOUT_S ?? 45) * 1000;
const isHosted = (b: { solver_args?: Record<string, unknown> }) => /nvidia|hosted|api/i.test(String(b.solver_args?.backend ?? ""));

async function handle(req: Connect.IncomingMessage, res: http.ServerResponse, next: Connect.NextFunction) {
  if (!req.url?.startsWith("/api/")) return next();
  const url = new URL(req.url, "http://x");
  const route = url.pathname.replace(/^\/api/, "");
  try {
    if (await handleUpload(req, res, route, url)) return;
    if (route === "/file" && req.method === "GET") {
      const abs = safeAbs(url.searchParams.get("path") ?? "");
      if (!abs) return send(res, 404, { detail: "file not found" });
      res.setHeader("Content-Type", MIME[path.extname(abs).toLowerCase()] ?? "application/octet-stream");
      res.setHeader("Cache-Control", "max-age=3600");
      res.setHeader("X-Stoa-Backend", "disk");
      fs.createReadStream(abs).pipe(res);
      return;
    }
    const stashed = (req as Connect.IncomingMessage & { stoaBody?: Buffer }).stoaBody;
    const body = req.method === "POST" ? stashed ?? await readBody(req) : Buffer.alloc(0);
    const askBody = route === "/ask" && req.method === "POST" ? (() => { try { return JSON.parse(body.toString() || "{}"); } catch { return {}; } })() : null;
    const hosted = !!askBody && isHosted(askBody);
    const live = route === "/bench" || route === "/rooms" ? null : await forward(req, route + url.search, body, hosted ? HOSTED_WAIT_MS : 600_000);
    if (hosted) {
      let ans: { value?: unknown } | null = null;
      try {
        ans = live && live.status === 200 ? JSON.parse(live.body.toString()) : null;
      } catch {
        ans = null;
      }
      if ((!ans || ans.value === null || ans.value === undefined) && liveUp()) {
        const r = mockAsk(askBody) as Record<string, unknown>;
        const why = !live ? `did not answer within ${HOSTED_WAIT_MS / 1000} s` : "returned no answer (rate-limited?)";
        if (r.value !== null && r.value !== undefined && r.recorded_at)
          return send(res, 200, { ...r, replayed: `hosted API busy: it ${why}; this is its answer recorded ${String(r.recorded_at)}. The live call keeps running and is cached when it lands.` }, "live");
        if (!live) // no recording to fall back on: say so (not the offline mock: the API itself is up)
          return send(res, 200, { value: null, unit: null, confidence: 0, evidence: [], solver: "vlm_direct",
            trace: [`backend=${String(askBody.solver_args?.backend)}`, `hosted model ${why}; the call keeps running on the API and is cached when it lands`],
            assumptions: [], missing: ["hosted model busy (rate limit): ask again in a minute"],
            cost: { llm_tokens_in: 0, llm_tokens_out: 0, gpu_seconds: 0, api_calls: 1, llm_calls: 0, wall_seconds: HOSTED_WAIT_MS / 1000 } }, "live");
      }
    }
    const optional = ["/questions", "/kg", "/files", "/health"].includes(route);
    if (live && route === "/kg" && live.status === 200) {
      // stoa.kg links only siblings for some sources (opening_design, cubicasa): add the drawing set by folder.
      try {
        const body = JSON.parse(live.body.toString()) as Record<string, unknown>;
        const hasPaths = Array.isArray(body.nodes) && (body.nodes as { path?: string }[]).some((n) => n.path);
        if ((!Array.isArray(body.files) || body.files.length === 0) && !hasPaths) body.files = kgFromDisk(url.searchParams.get("path") ?? "").files;
        return send(res, 200, body, "live");
      } catch {
        /* fall through: pass the body on unchanged */
      }
    }
    if (live && !(optional && (live.status === 404 || live.status === 405) && !String(live.body).includes("file"))) {
      res.statusCode = live.status;
      res.setHeader("Content-Type", String(live.headers["content-type"] ?? "application/json"));
      res.setHeader("X-Stoa-Backend", "live");
      return res.end(live.body);
    }
    // --- mock ---
    if (route === "/health") return send(res, 200, { ok: true, backend: "mock", data: fs.existsSync(DATA) });
    if (route === "/files") {
      const source = url.searchParams.get("source");
      const q = (url.searchParams.get("q") ?? "").toLowerCase();
      const limit = Number(url.searchParams.get("limit") ?? 50);
      const withQ = url.searchParams.get("with_questions") !== "false";
      const all = withQ ? [...DEMO, ...[...questionsByPath().keys()].filter((p) => !DEMO.includes(p))]
        : source && fs.existsSync(path.join(DATA, "data", source))
          ? fs.readdirSync(path.join(DATA, "data", source)).filter((f) => /\.(jpe?g|png|pdf|ifc)$/i.test(f)).sort().map((f) => `data/${source}/${f}`)
          : [];
      if (q.startsWith("data/") && safeAbs(url.searchParams.get("q")!) && !all.includes(url.searchParams.get("q")!))
        all.unshift(url.searchParams.get("q")!); // exact path lookup, even for files without questions
      const files = all.filter((p) => (!source || p.split("/")[1] === source) && (!q || p.toLowerCase().includes(q)) && safeAbs(p))
        .slice(0, limit).map(fileInfo);
      return send(res, 200, { files });
    }
    if (route === "/questions") {
      const p = url.searchParams.get("path") ?? "";
      const seen = new Set<string>();
      const fx = fixtures().filter((f) => f.path === p).map((f) => ({ question: f.question, type: "", unit: f.answer.unit, has_fixture: true }));
      const qs = (questionsByPath().get(p) ?? []).filter((q) => /\b(how many|what|which|is there|are there)\b/i.test(q.question)) // English twin
        .map((q) => ({ question: q.question, type: q.type, unit: q.unit, has_fixture: false }));
      const out = [...fx, ...qs].filter((q) => !seen.has(norm(q.question)) && seen.add(norm(q.question))).slice(0, 40);
      return send(res, 200, { questions: out });
    }
    if (route === "/bench") {
      const b = bench();
      return b ? send(res, 200, b, "kg") : send(res, 404, { detail: "no leaderboard and no fixtures/bench.json" });
    }
    if (route === "/rooms") {
      const rel = url.searchParams.get("path") ?? "";
      if (!/^data\/cubicasa5k\/[^/]+\.png$/i.test(rel) || !safeAbs(rel)) return send(res, 404, { detail: "room graph: CubiCasa plans only" });
      const g = await roomGraph(rel);
      if (g) return send(res, 200, g, "kg");
      // no Python env / no R1 cache here: the graph fixtures/record.py saved for the tour plans
      const rec = (() => { try { return JSON.parse(fs.readFileSync(ROOMS_REC, "utf8")) as Record<string, unknown>; } catch { return {}; } })()[rel];
      return rec ? send(res, 200, rec, "mock") : send(res, 404, { detail: "no cached CubiCasa5K segmentation for this plan" });
    }
    if (route === "/kg") {
      const rel = url.searchParams.get("path") ?? "";
      if (!safeAbs(rel)) return send(res, 404, { detail: "file not found" });
      const r = await kg(rel);
      return send(res, 200, r.body, r.backend);
    }
    if (route === "/ask" && req.method === "POST") {
      const b = JSON.parse(body.toString() || "{}");
      if (!safeAbs(b.path ?? "")) return send(res, 404, { detail: "file not found" });
      await new Promise((r) => setTimeout(r, 350)); // feel of a real call
      return send(res, 200, mockAsk(b));
    }
    return send(res, 404, { detail: `no mock for ${req.method} ${route}` });
  } catch (e) {
    return send(res, 500, { detail: String(e) });
  }
}

export function stoaApi(): Plugin {
  return {
    name: "stoa-api",
    configureServer(server) {
      server.middlewares.use(handle);
    },
    configurePreviewServer(server) {
      server.middlewares.use(handle);
    },
  };
}

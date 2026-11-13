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
 */
import fs from "node:fs";
import http from "node:http";
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

/** Linked sources (mock of W4's knowledge graph): the files of one building/project and how they relate. */
function kg(rel: string) {
  const nodes: { path: string; kind: string; label: string; relation: string }[] = [];
  const add = (p: string, relation: string) => {
    if (!nodes.some((n) => n.path === p))
      nodes.push({ path: p, kind: path.extname(p).slice(1), label: path.basename(p), relation });
  };
  const sib = siblings(rel);
  for (const [e, p] of Object.entries(sib)) {
    add(p, e === ".ifc" && rel.startsWith("data/ifc_models/") ? "model this sheet was cut from"
      : e === ".svg" ? "same sheet, vector with IFC GlobalIds" : e === ".dxf" ? "same drawing, CAD layers"
      : "same drawing, other format");
  }
  if (rel.startsWith("data/ifc_models/")) {
    const model = (sib[".ifc"] ?? rel).replace(/\.(ifc|pdf|svg)$/, "").replace(/_(plan|section|elevation)-.*$/, "");
    const base = path.basename(model);
    for (const f of fs.readdirSync(path.join(DATA, "data/ifc_models")))
      if (f.startsWith(base + "_") && f.endsWith(".pdf") && `data/ifc_models/${f}` !== rel)
        add(`data/ifc_models/${f}`, f.includes("_plan-") ? "other storey plan" : "section / elevation");
  }
  if (rel.startsWith("data/swiss_dwellings/")) {
    const site = path.basename(rel).split("_")[0];
    for (const f of fs.readdirSync(path.join(DATA, "data/swiss_dwellings")))
      if (f.startsWith(site + "_") && f.endsWith(".pdf") && `data/swiss_dwellings/${f}` !== rel)
        add(`data/swiss_dwellings/${f}`, "other floor of the same site");
  }
  if (rel.startsWith("data/opening_design/")) {
    const dir = path.dirname(rel);
    for (const f of fs.readdirSync(path.join(DATA, dir)).slice(0, 40))
      if (/\.(pdf|ifc)$/i.test(f) && `${dir}/${f}` !== rel) add(`${dir}/${f}`, "same drawing set");
  }
  return { path: rel, project: rel.split("/").slice(1, 3).join("/"), nodes: nodes.slice(0, 30), mock: true };
}

type Fixture = { path: string; question: string; answer: Record<string, unknown> };
function fixtures(): Fixture[] {
  try {
    return JSON.parse(fs.readFileSync(FIXTURES, "utf8")) as Fixture[];
  } catch {
    return [];
  }
}
const norm = (s: string) => s.trim().toLowerCase().replace(/\s+/g, " ");

function mockAsk(body: { path: string; question: string; solver?: string }) {
  const fx = fixtures().find((f) => f.path === body.path && norm(f.question) === norm(body.question));
  if (fx) return { ...fx.answer, trace: [...((fx.answer.trace as string[]) ?? []), "(mock API: precomputed fixture)"] };
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

let liveDownUntil = 0;
/** Forward to the live API. Resolves null when it is unreachable (→ mock). */
function forward(req: http.IncomingMessage, url: string, body: Buffer): Promise<{ status: number; headers: http.IncomingHttpHeaders; body: Buffer } | null> {
  if (Date.now() < liveDownUntil) return Promise.resolve(null);
  return new Promise((resolve) => {
    const u = new URL(url, LIVE);
    const r = http.request(u, { method: req.method, headers: { "content-type": req.headers["content-type"] ?? "application/json" }, timeout: 600_000 }, (resp) => {
      const chunks: Buffer[] = [];
      resp.on("data", (c) => chunks.push(c));
      resp.on("end", () => resolve({ status: resp.statusCode ?? 500, headers: resp.headers, body: Buffer.concat(chunks) }));
    });
    r.on("error", () => {
      liveDownUntil = Date.now() + 5000;
      resolve(null);
    });
    r.end(body);
  });
}

async function handle(req: Connect.IncomingMessage, res: http.ServerResponse, next: Connect.NextFunction) {
  if (!req.url?.startsWith("/api/")) return next();
  const url = new URL(req.url, "http://x");
  const route = url.pathname.replace(/^\/api/, "");
  try {
    if (route === "/file" && req.method === "GET") {
      const abs = safeAbs(url.searchParams.get("path") ?? "");
      if (!abs) return send(res, 404, { detail: "file not found" });
      res.setHeader("Content-Type", MIME[path.extname(abs).toLowerCase()] ?? "application/octet-stream");
      res.setHeader("Cache-Control", "max-age=3600");
      res.setHeader("X-Stoa-Backend", "disk");
      fs.createReadStream(abs).pipe(res);
      return;
    }
    const body = req.method === "POST" ? await readBody(req) : Buffer.alloc(0);
    const live = await forward(req, route + url.search, body);
    const optional = ["/questions", "/kg", "/files", "/health"].includes(route);
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
      const all = [...DEMO, ...[...questionsByPath().keys()].filter((p) => !DEMO.includes(p))];
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
    if (route === "/kg") return send(res, 200, kg(url.searchParams.get("path") ?? ""));
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

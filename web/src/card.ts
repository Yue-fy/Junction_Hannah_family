import type { Answer, Cost, Evidence } from "./types";

// Same rates as stoa/eval/runner.py:RATES (USD). Keep in sync.
const RATES = {
  gpu_usd_per_s: 0.0006, cpu_usd_per_s: 0.000014, api_usd_per_mtok_in: 0.4, api_usd_per_mtok_out: 1.6,
  local_usd_per_mtok_in: 0.05, local_usd_per_mtok_out: 0.2,
};
const EUR_PER_USD = 0.86; // display only; fixed rate, not live

// Local-LLM GPU time is billed from tokens at the shared server's measured throughput, as the eval does
// (stoa/eval/runner.py gpu_seconds_billed): reported HTTP latency includes queueing behind other jobs.
const PREFILL_TPS = 25_000;
const DECODE_TPS = 1_000;

export function gpuSecondsBilled(c: Cost): number {
  const g = (k: string) => Number(c[k] ?? 0);
  const localIn = Math.max(0, g("llm_tokens_in") - g("api_tokens_in"));
  const localOut = Math.max(0, g("llm_tokens_out") - g("api_tokens_out"));
  const gpu = g("gpu_seconds");
  return (localIn || localOut) && gpu ? Math.min(gpu, localIn / PREFILL_TPS + localOut / DECODE_TPS) : gpu;
}

export function costUsd(c: Cost): number {
  const g = (k: string) => Number(c[k] ?? 0);
  const localIn = Math.max(0, g("llm_tokens_in") - g("api_tokens_in"));
  const localOut = Math.max(0, g("llm_tokens_out") - g("api_tokens_out"));
  let usd = gpuSecondsBilled(c) * RATES.gpu_usd_per_s + g("wall_seconds") * RATES.cpu_usd_per_s;
  usd += (g("api_tokens_in") * RATES.api_usd_per_mtok_in + g("api_tokens_out") * RATES.api_usd_per_mtok_out) / 1e6;
  if (!g("gpu_seconds")) usd += (localIn * RATES.local_usd_per_mtok_in + localOut * RATES.local_usd_per_mtok_out) / 1e6;
  return usd;
}

export function costTier(c: Cost): "deterministic" | "local" | "api" {
  if ((c.api_calls ?? 0) > 0 || (c.api_tokens_in ?? 0) > 0) return "api";
  if ((c.llm_calls ?? 0) > 0 || (c.llm_tokens_in ?? 0) > 0 || (c.gpu_seconds ?? 0) > 0) return "local";
  return "deterministic";
}

const UNIT_LABEL: Record<string, string> = { m2: "m²", m3: "m³", ft2: "ft²", count: "", m: "m" };

const esc = (s: unknown) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

/** Per-question cost as "€X per 1,000 questions like this" (µ-euros per question mean nothing to a jury). */
function fmtEur(usd: number) {
  const per1k = usd * EUR_PER_USD * 1000;
  if (per1k === 0) return "€0 / 1k Qs";
  if (per1k < 0.01) return "< €0.01 / 1k Qs";
  return `€${per1k < 10 ? per1k.toFixed(2) : per1k.toFixed(0)} / 1k Qs`;
}

function fmtValue(a: Answer) {
  if (a.value === null || a.value === undefined) return "—";
  if (typeof a.value === "number") {
    const v = Number.isInteger(a.value) ? String(a.value) : a.value.toLocaleString("en", { maximumFractionDigits: 2 });
    return v;
  }
  return String(a.value);
}

/** "cross-check: … ✓/✗" lines from evidence notes and trace (D4: no contract change). */
export function crossChecks(a: Answer, asks: string[] = []): { text: string; ok: boolean }[] {
  // Compound answers prefix each evidence note with its part ("door: door 1; cross-check: answer 36 vs …").
  const parts = new Set(a.plan?.parts ?? []);
  const parse = (lines: string[]) => lines.flatMap((l) => {
    const m = l.match(/cross-?check:?\s*(.*)$/i);
    // a comparison with the training prior is a sanity note, not a second source: keep it in the trace only
    if (!m || /^vs\.? prior\b/i.test(m[1].trim())) return [];
    const part = l.match(/^([^:;]+):\s/)?.[1];
    const k = asks.length ? evStep(l, asks) : -1;
    const text = (k >= 0 ? `step ${k + 1}: ` : part && parts.has(part) ? `${part}: ` : "") + m[1].trim();
    return [{ text: text.replace(/\s*[✓✗]\s*/g, " ").trim(), ok: !/✗|≠|!=|disagree|differs?\b|mismatch|conflict/i.test(text) }];
  });
  // Evidence notes carry the specific check; the trace usually repeats it, so use the trace only as fallback.
  // Exception: boxes added by "Show where" (notes start with the locator's name) carry the locator's check only;
  // the solver's own check (e.g. "vlm_lora 4 = raster 4") is then in the trace, so keep it next to it.
  const fromEv = parse(a.evidence.map((e) => e.note ?? ""));
  const fromTrace = parse(a.trace ?? []);
  const located = a.evidence.some((e) => LOCATED_NOTE.test(e.note ?? ""));
  const key = (t: string) => t.split("→")[0].replace(/\s+/g, " ").trim().slice(0, 24);
  // "label reader (raster) finds 1 …" already says what the pipeline's "vlm_lora 0 ≠ raster 1" says: keep one line
  const same = (t: string) => fromEv.some((e) => {
    const m = e.text.match(/\((\w+)\) finds (\d+)/);
    return m && new RegExp(`\\b${m[1]} ${m[2]}\\b`).test(t);
  });
  const extra = located ? fromTrace.filter((t) => !same(t.text) && !fromEv.some((e) => t.text.startsWith(key(e.text)) || e.text.startsWith(key(t.text)))) : [];
  const out = fromEv.length ? [...fromEv, ...extra] : fromTrace;
  // a failed check is never the one cut off: failures first (stable), then the cap
  const uniq = out.filter((x, i) => out.findIndex((y) => y.text === x.text) === i);
  return [...uniq.filter((x) => !x.ok), ...uniq.filter((x) => x.ok)].slice(0, Math.max(2, parts.size));
}

/** One row per object: evidence items that share an ifc_guid (2D box + 3D element) are grouped. */
export function groupEvidence(ev: Evidence[]): { idx: number[]; first: number }[] {
  const groups: { idx: number[]; first: number }[] = [];
  const byGuid = new Map<string, { idx: number[]; first: number }>();
  ev.forEach((e, i) => {
    const g = e.ifc_guid ? byGuid.get(e.ifc_guid) : undefined;
    if (g) return void g.idx.push(i);
    const ng = { idx: [i], first: i };
    if (e.ifc_guid) byGuid.set(e.ifc_guid, ng);
    groups.push(ng);
  });
  return groups;
}

function evLabel(ev: Evidence[], g: { idx: number[]; first: number }, n: number, describe: (g: string) => string, asks: string[] = []) {
  const items = g.idx.map((i) => ev[i]);
  const has2D = items.some((e) => e.bbox);
  const has3D = items.some((e) => e.ifc_guid);
  const e = items.find((x) => x.bbox) ?? items[0];
  let note = items.map((x) => x.note).find((x) => x) || (e.ifc_guid ? describe(e.ifc_guid) : "evidence");
  // agent answers: "<sub-question> — KORIDOR 63.84 m²" → "step 2 · KORIDOR 63.84 m²"
  const stepNo = asks.length ? items.map((x) => evStep(x.note ?? "", asks)).find((k) => k >= 0) : undefined;
  let step = "";
  if (stepNo !== undefined && stepNo >= 0) {
    note = note.replace(/^.{10,60}? — /, "");
    step = `<span class="stepref" title="From reasoning step: ${esc(asks[stepNo])}">step ${stepNo + 1}</span>`;
  }
  const where = has2D && has3D ? "2D + 3D" : has3D ? "3D" : has2D ? "2D" : "";
  const projected = items.some((x) => /projected: not drawn/i.test(x.note ?? ""));
  const files = new Set(items.map((x) => x.file.split("/").pop()));
  return `<li class="ev-item" data-i="${g.idx.find((i) => ev[i].bbox) ?? g.first}" title="${esc([...files].join(" · "))}"><span class="n">${n}</span><span class="t">${step}${esc(note.replace(/\s*\|\s*projected: not drawn on this plan\s*$/i, ""))}${projected ? `<span class="proj" title="Not drawn on this plan (cut at 1.2 m): box = the element's footprint from the IFC model">projected</span>` : ""}</span><span class="w">${where}</span></li>`;
}

/** Long text answers (often "- item" lists from the model fact card): a compact list, folded after 8 lines. */
function richText(v: string) {
  const lines = v.split(/\n+/).map((l) => l.trim()).filter(Boolean);
  const isList = lines.length > 1 && lines.filter((l) => /^[-*•]\s/.test(l)).length >= lines.length * 0.6;
  const fmt = (l: string) => esc(l.replace(/^[-*•]\s+/, "")).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
  const block = (ls: string[]) => (isList ? `<ul>${ls.map((l) => `<li>${fmt(l)}</li>`).join("")}</ul>` : ls.map((l) => `<p>${fmt(l)}</p>`).join(""));
  const KEEP = 8;
  return block(lines.slice(0, KEEP)) + (lines.length > KEEP
    ? `<details class="more-lines"><summary>${lines.length - KEEP} more line${lines.length - KEEP > 1 ? "s" : ""}</summary>${block(lines.slice(KEEP))}</details>` : "");
}

/** Trace lines: "[solver] text" → tag + text; long traces show the first steps and fold the rest. */
function traceHtml(trace: string[], keep = 6) {
  const li = (full: string) => {
    const t = full.length > 260 ? `${full.slice(0, 240).replace(/\s*\n\s*/g, " ")} …` : full;
    const m = t.match(/^\[([\w:/-]+)\]\s*(.*)$/);
    const cc = /cross-?check/i.test(t) ? " class=\"cc\"" : /\d\s*[x×*/÷+−-]\s*\d[^=]*=\s*-?\d/.test(t) ? " class=\"calc\"" : "";
    return m ? `<li${cc}><span class="tag">${esc(m[1])}</span>${esc(m[2])}</li>` : `<li${cc}>${esc(t)}</li>`;
  };
  const head = trace.slice(0, keep).map(li).join("");
  const rest = trace.slice(keep);
  return `<ol class="trace">${head}</ol>` + (rest.length
    ? `<details class="more-steps"><summary>${rest.length} more step${rest.length > 1 ? "s" : ""}</summary><ol class="trace" start="${keep + 1}">${rest.map(li).join("")}</ol></details>`
    : "");
}

// --- general agent (stoa/router/agent.py): "think: <thought> → <tool>(<input>): <result>" / "think: … → answer <v> <unit>"
export interface AgentStep { tool: string; input: string; result: string; thought: string; conf?: number; by?: string }
export interface AgentRun { why?: string; calls?: number; steps: AgentStep[] }

export function agentRun(trace: string[] | undefined): AgentRun | null {
  const steps: AgentStep[] = [];
  let why: string | undefined;
  let calls: number | undefined;
  for (const l of trace ?? []) {
    const w = l.match(/^general agent first:\s*(.*)$/);
    if (w) { why = w[1]; continue; }
    const h = l.match(/^agent: general tool-using path \((\d+) steps?, (\d+) LLM calls?\)/);
    if (h) { calls = Number(h[2]); continue; }
    const a = l.match(/^think:\s*(.*?)\s*→\s*answer\s*(.*)$/);
    if (a) { steps.push({ tool: "answer", input: "", result: a[2].trim(), thought: a[1] }); continue; }
    const t = l.match(/^think:\s*(.*?)\s*→\s*(ask|table|find_text|look|calc)\(/);
    if (!t) continue;
    const rest = l.slice(t[0].length);
    const cut = rest.indexOf("): ");
    const input = cut >= 0 ? rest.slice(0, cut) : rest;
    let result = cut >= 0 ? rest.slice(cut + 3) : "";
    const s: AgentStep = { tool: t[2], input, result, thought: t[1] };
    const r = result.match(/^(.*?)\s*\(confidence ([\d.]+), by ([\w/.-]+)\)\s*$/);
    if (r) { result = r[1]; s.conf = Number(r[2]); s.by = r[3].replace(/^pipeline\//, ""); s.result = result; }
    steps.push(s);
  }
  return steps.length ? { why, calls, steps } : null;
}

const TOOL_LBL: Record<string, string> = { ask: "ask", calc: "calc", table: "table", find_text: "find text", look: "look", answer: "answer" };
const TOOL_TIP: Record<string, string> = {
  ask: "Asked a simple question to the solver cascade (rules / geometry first); its number and evidence come back",
  calc: "Arithmetic done in code (safe expression evaluator), never by the model",
  table: "Read the drawing's data table (rooms with areas, or the model's fact card)",
  find_text: "Searched the drawing's text layer; hits become evidence boxes",
  look: "Asked the vision model directly (unverified, low confidence)",
  answer: "Final answer; every number in it is traced back to a tool result",
};

/** The agent's chain: one row per tool call, the ask sub-questions clickable, arithmetic shown as code. */
function reasoningHtml(run: AgentRun, a: Answer) {
  const fmtRes = (s: string) => esc(s.replace(/\bm2\b/g, "m²").replace(/\bm3\b/g, "m³").replace(/\s+count\b/, ""))
    .replace(/^(-?\d+\.\d{3,})/, (m) => String(Math.round(Number(m) * 100) / 100));
  const evCount = (input: string) => (a.evidence ?? []).filter((e) => evStep(e.note ?? "", [input]) === 0).length;
  const li = (s: AgentStep, i: number) => {
    const n = `<span class="sn">${i + 1}</span>`;
    const tool = `<span class="tool t-${s.tool}" title="${esc(TOOL_TIP[s.tool] ?? s.tool)}">${esc(TOOL_LBL[s.tool] ?? s.tool)}</span>`;
    const th = s.thought ? `<div class="th">${esc(s.thought)}</div>` : "";
    if (s.tool === "ask") {
      const k = evCount(s.input);
      const meta = [s.conf !== undefined ? `${Math.round(s.conf * 100)}%` : "", s.by ?? "", k ? `${k} evidence` : ""].filter(Boolean).join(" · ");
      return `<li>${n}${tool}<span role="button" tabindex="0" class="subq" data-q="${esc(s.input)}" title="Ask this sub-question on its own">${esc(s.input)}</span><span class="res">→ <b>${fmtRes(s.result)}</b>${meta ? ` <small>${esc(meta)}</small>` : ""}</span>${th}</li>`;
    }
    if (s.tool === "calc") return `<li>${n}${tool}<code>${esc(s.input.replace(/\*/g, "×").replace(/\//g, "÷"))}</code><span class="res">= <b>${fmtRes(s.result)}</b></span>${th}</li>`;
    if (s.tool === "answer") return `<li class="fin">${n}${tool}<span class="res"><b>${fmtRes(s.result)}</b></span>${th}</li>`;
    return `<li>${n}${tool}<span class="inp">${esc(s.input)}</span><span class="res">→ ${fmtRes(s.result.slice(0, 160))}</span>${th}</li>`;
  };
  const head = run.why ? `<div class="why-agent">Not a known question template (${esc(run.why.replace(/;\s*not a known template$/, ""))}), so a small local model plans the steps; every number comes from a tool, never from the model.</div>` : "";
  return `${head}<ol class="steps">${run.steps.map(li).join("")}</ol>`;
}

/** Which ask step an agent evidence note came from: notes are "<ask input[:55]> — <note>". -1 = none. */
function evStep(note: string, inputs: string[]): number {
  const m = note.match(/^(.{10,60}?) — /);
  if (!m) return -1;
  const p = m[1].trim();
  return inputs.findIndex((q) => q.length > 0 && (q.startsWith(p) || p.startsWith(q.slice(0, 50))));
}

const LANG: Record<string, string> = { de: "German", fi: "Finnish", sv: "Swedish", fr: "French", it: "Italian", nl: "Dutch", et: "Estonian", es: "Spanish", da: "Danish", pl: "Polish" };
const OP: Record<string, string> = { sum: "sum of", diff: "difference of", argmax: "largest of", argmin: "smallest of", max: "max of", min: "min of", exists: "any of" };

/** "Understood as" (W4's intent) and, for compound questions, the plan of sub-questions answered one by one. */
function intentHtml(a: Answer, run: AgentRun | null) {
  const it = a.intent;
  if (!it && !a.plan && !run) return "";
  const bits: string[] = [];
  // "operator question (modifier share …)" + "<solver> (question as asked): …": the template intent was not used
  const op = !run && (a.trace ?? []).find((l) => /^operator question \(modifiers? /.test(l))?.match(/modifiers? ([\w+]+)/)?.[1];
  const raw = !run && (a.trace ?? []).find((l) => /^\w+ \(question as asked\):/.test(l))?.match(/^(\w+)/)?.[1];
  if (op && raw) {
    bits.push(op.split("+").map((m) => `<b>${esc(m.replace(/_/g, " "))}</b>`).join(" + "));
    bits.push(`not a template: ${esc(raw)} read the question itself and computed it in code`);
  } else if (run) {
    // the template intent was NOT used (it misreads operators); say what the agent did instead
    const mods = run.why?.match(/^modifiers?\s+([\w+]+)/)?.[1]?.split("+") ?? [];
    bits.push(mods.length ? mods.map((m) => `<b>${esc(m.replace(/_/g, " "))}</b>`).join(" + ") : "<b>open question</b>");
    const n = run.steps.filter((s) => s.tool !== "answer").length;
    bits.push(`reasoning agent · ${n} tool step${n === 1 ? "" : "s"}`);
  } else if (it) {
    bits.push(`<b>${esc(it.task)}</b>`);
    const target = a.plan?.parts?.length ? a.plan.parts.join(a.plan.op === "sum" ? " + " : ", ") : it.target;
    if (target && target !== it.task && target !== "unknown") bits.push(esc(target.replace(/_/g, " ")));
    const f = Object.entries(it.filters ?? {}).filter(([, v]) => v !== null && v !== "" && v !== false)
      .map(([k, v]) => `${esc(k.replace(/_/g, " "))} <i>${esc(v === true ? "yes" : v)}</i>`);
    bits.push(...(f.length ? f : it.scope ? [`scope <i>${esc(it.scope)}</i>`] : []));
    if (it.unit && it.unit !== "count") bits.push(`in ${esc(UNIT_LABEL[it.unit] ?? it.unit)}`);
  }
  const lang = it?.lang && it.lang !== "en" ? `<span class="lang" title="The question was parsed into the same language-neutral intent as its English twin">${esc(LANG[it.lang] ?? it.lang)}</span>` : "";
  const plan = a.plan && a.plan.sub_questions?.length
    ? `<details class="plan"><summary><b>${esc(OP[a.plan.op] ?? a.plan.op)}</b> ${a.plan.parts.map((p) => `<span class="part">${esc(p)}</span>`).join(a.plan.op === "sum" ? " + " : a.plan.op === "diff" ? " − " : ", ")}
        <small>${a.plan.sub_questions.length} sub-questions, arithmetic in code</small></summary>
        <ol>${a.plan.sub_questions.map((q) => `<li><span role="button" tabindex="0" class="subq" data-q="${esc(q)}" title="Ask this sub-question on its own">${esc(q)}</span></li>`).join("")}</ol></details>`
    : "";
  return `<div class="intent"><span class="lbl">Understood as</span>${bits.join(" · ")}${lang}${a.cached ? `<span class="cached" title="Same question answered before; served from the API cache">cached</span>` : ""}</div>${plan}`;
}

/** The ask inputs of an agent answer, aligned with its steps ("" for non-ask steps). */
export function agentAsks(a: Answer): string[] {
  const run = agentRun(a.trace);
  return run ? run.steps.map((s) => (s.tool === "ask" ? s.input : "")) : [];
}

// --- second opinion from the hosted model (button in the card; only for model-tier or unsure answers on images/PDFs)
function sameAnswer(a: Answer, b: Answer): boolean | null {
  if (a.value === null || a.value === undefined || b.value === null || b.value === undefined) return null;
  if (typeof a.value === "number") {
    const y = Number(b.value);
    if (!Number.isFinite(y)) return false;
    const x = a.value;
    return a.unit === "count" || (Number.isInteger(x) && Number.isInteger(y)) ? x === y : Math.abs(x - y) <= 0.02 * Math.abs(x);
  }
  const s = String(a.value).toLowerCase().trim();
  const t = String(b.value).toLowerCase().trim();
  return s === t || (t.length > 2 && s.includes(t)) || (s.length > 2 && t.includes(s));
}

function modelName(b: Answer) {
  const m = (b.trace ?? []).map((l) => l.match(/^(nvidia|local):(\S+)/)).find((x) => x);
  const id = m?.[2] ?? "";
  if (/nemotron-3\.5-super/i.test(id)) return "NVIDIA Nemotron 3.5 Super VL (hosted)";
  return id ? `${id.split("/").pop()} (${m![1] === "nvidia" ? "hosted" : "local"})` : "hosted model";
}

export function secondOpinionHtml(a: Answer, b: Answer, ms: number) {
  const same = sameAnswer(a, b);
  const unit = b.unit ? UNIT_LABEL[b.unit] ?? b.unit : "";
  const c: Cost = b.cost ?? {};
  const wall = c.wall_seconds && c.wall_seconds > 0 ? c.wall_seconds : ms / 1000;
  const raw = (b.trace ?? []).find((l) => /^raw:/.test(l))?.replace(/^raw:\s*/, "") ?? "";
  const verdict = b.value === null || b.value === undefined ? `<b>No answer</b> from ${esc(modelName(b))}`
    : `<b>${same ? "✓ Second opinion agrees" : "≠ Second opinion differs"}</b> ${esc(modelName(b))} says <b>${esc(fmtValue(b))}${unit ? ` ${esc(unit)}` : ""}</b>`;
  return `<div class="xcheck second ${same ? "ok" : "bad"}">${verdict}
    <small>${wall.toFixed(1)} s · ${((c.api_tokens_in ?? c.llm_tokens_in ?? 0) + (c.api_tokens_out ?? c.llm_tokens_out ?? 0)).toLocaleString()} tok · ${esc(fmtEur(costUsd({ ...c, wall_seconds: wall })))}</small>
    ${raw ? `<details><summary>its reasoning</summary><p>${esc(raw.replace(/\s*\|\s*/g, " ").slice(0, 900))}</p></details>` : ""}</div>`;
}

/** Who can mark what a CubiCasa count counted when the answer itself carries no boxes: room names → the label
 * reader (raster, local VLM, cached per drawing); symbols → R1's pretrained CubiCasa5K detector (cached, no GPU). */
const ROOM_TARGETS = new Set(["bedroom", "kitchen", "bathroom", "sauna", "wc_room", "balcony"]);
const SYMBOL_TARGETS = new Set(["window", "door", "wc", "sink"]);
export const LOCATED_NOTE = /^(label reader|CubiCasa5K detector): /;
export interface Locator { solver: string; name: string; button: string; title: string; noun: string }
const NOUNS: Record<string, string> = { window: "windows", door: "doors", wc: "WC seats", sink: "sinks", wc_room: "WC room labels" };
export function locatorFor(a: Answer, file: string): Locator | null {
  if (a.value === null || (a.evidence ?? []).length || !/^data\/cubicasa5k\/.*\.(png|jpe?g)$/i.test(file)) return null;
  const t = a.intent?.target ?? (a.trace ?? []).map((l) => l.match(/^intent: count (\w+)/)?.[1]).find((x) => x) ?? "";
  const noun = NOUNS[t] ?? (ROOM_TARGETS.has(t) ? `${t} labels` : "symbols");
  // the pipeline already asked the label reader and it found none: nothing to mark
  if (ROOM_TARGETS.has(t) && (a.trace ?? []).some((l) => /cross-check:.*\braster 0\b/.test(l))) return null;
  if (ROOM_TARGETS.has(t)) return { solver: "raster", name: "label reader", button: "Show where · read the room labels", noun,
    title: "Read the room labels on the drawing (local vision model, once per drawing, cached) and mark the ones this answer counts" };
  if (SYMBOL_TARGETS.has(t)) return { solver: "raster_cc5k", name: "CubiCasa5K detector", button: "Show where · symbol detector", noun,
    title: "Mark every symbol the pretrained CubiCasa5K model finds (Kalervo et al. 2019, weights CC BY-NC 4.0; cached, no GPU)" };
  return null;
}

export interface CardOpts {
  /** CubiCasa answers without located evidence: ask a locator (see locatorFor) to mark what was counted. */
  onLocate?: (loc: Locator) => Promise<void>;
  onSecondOpinion?: () => Promise<{ answer: Answer; ms: number }>;
  onAsk?: (question: string) => void;
  roundTripMs: number;
  onEvidence: (i: number) => void;
  describeGuid: (g: string) => string;
  currentFile: string;
  onOpenSheet: (path: string) => void;
}

/** Which files carry 2D evidence (model-wide answers box elements on several sheets). */
function sheetsHtml(ev: Evidence[], current: string) {
  const counts = new Map<string, number>();
  for (const e of ev) if (e.bbox) counts.set(e.file, (counts.get(e.file) ?? 0) + 1);
  if (counts.size === 0 || (counts.size === 1 && counts.has(current))) return "";
  const short = (p: string) => p.split("/").pop()!.replace(/^.*?_(plan|section|elevation)-/, "$1-").replace(/\.[^.]+$/, "");
  const chips = [...counts.entries()].sort((a, b) => (a[0] === current ? -1 : b[0] === current ? 1 : a[0].localeCompare(b[0])))
    .map(([f, n]) => `<button class="sheet ${f === current ? "on" : ""}" data-file="${esc(f)}" title="${esc(f)}">${esc(f === current ? "this sheet" : short(f))} <b>${n}</b></button>`).join("");
  return `<div class="sheets"><span>Evidence on ${counts.size} sheet${counts.size > 1 ? "s" : ""}:</span>${chips}</div>`;
}

const CASCADE: ["deterministic" | "local" | "api", string][] = [["deterministic", "rules / geometry"], ["local", "local model"], ["api", "hosted model"]];
function cascadeHtml(tier: "deterministic" | "local" | "api") {
  const reached = CASCADE.findIndex(([t]) => t === tier);
  return `<div class="cascade" title="Cost-aware cascade: the cheapest step that is sure enough answers">${CASCADE.map(([t, label], i) =>
    `<span class="${i < reached ? "passed" : i === reached ? `on ${t}` : ""}">${label}</span>`).join("<i>›</i>")}</div>`;
}

export function renderCard(el: HTMLElement, a: Answer, opts: CardOpts) {
  const c: Cost = a.cost ?? {};
  const tier = costTier(c);
  const wall = c.wall_seconds && c.wall_seconds > 0 ? c.wall_seconds : opts.roundTripMs / 1000;
  const tokens = (c.llm_tokens_in ?? 0) + (c.llm_tokens_out ?? 0);
  const conf = Math.round((a.confidence ?? 0) * 100);
  const confClass = conf >= 85 ? "hi" : conf >= 55 ? "mid" : "lo";
  const run = agentRun(a.trace);
  const asks = agentAsks(a);
  const checks = crossChecks(a, asks);
  const unit = a.unit ? UNIT_LABEL[a.unit] ?? a.unit : "";
  const isText = typeof a.value === "string";
  const rich = isText && (String(a.value).length > 120 || String(a.value).includes("\n"));
  const ev = a.evidence ?? [];
  const groups = groupEvidence(ev);
  const shown = groups.slice(0, 80);
  const loc = locatorFor(a, opts.currentFile);

  el.className = `card answer ${a.value === null ? "refused" : ""}`;
  el.innerHTML = `
    <div class="value-row${rich ? " rich" : ""}">
      ${rich ? `<span class="rich-lbl">Text answer · ${String(a.value).split(/\n+/).filter((l) => l.trim()).length} line(s)</span><div class="value text rich">${richText(String(a.value))}</div>`
        : `<div class="value ${isText ? "text" : ""} ${isText && String(a.value).length > 40 ? "long" : ""}">${esc(fmtValue(a))}${unit ? `<span class="unit">${esc(unit)}</span>` : ""}</div>`}
      <div class="conf ${confClass}" title="Calibrated confidence">
        <div class="conf-num">${conf}%</div><div class="conf-bar"><i style="width:${conf}%"></i></div><div class="conf-lbl">confidence</div>
      </div>
    </div>
    ${intentHtml(a, run)}
    ${checks.map((x) => `<div class="xcheck ${x.ok ? "ok" : "bad"}"><b>${x.ok ? "✓ Cross-checked" : "✗ Sources disagree"}</b> ${esc(x.text)}</div>`).join("")}
    ${cascadeHtml(tier)}
    ${opts.onLocate && loc ? `<div class="locate-slot"><button class="locate-btn" title="${esc(loc.title)}">${esc(loc.button)}</button></div>` : ""}
    ${opts.onSecondOpinion && /\.(png|jpe?g|pdf)$/i.test(opts.currentFile) && (tier !== "deterministic" || (a.confidence ?? 0) < 0.8)
      ? `<div class="second-slot"><button class="second-btn" title="Ask NVIDIA Nemotron 3.5 Super VL (hosted vision + reasoning model) the same question: one API call, only when you click">Second opinion · NVIDIA Nemotron</button></div>` : ""}
    <div class="cost">
      <span title="Wall time">⏱ ${wall < 1 ? `${Math.round(wall * 1000)} ms` : `${wall.toFixed(1)} s`}</span>
      <span title="LLM tokens in / out">${tokens ? `${(c.llm_tokens_in ?? 0).toLocaleString()} / ${(c.llm_tokens_out ?? 0).toLocaleString()} tok` : "0 tokens"}</span>
      <span title="Estimated cost of this answer with the eval's rates (stoa/eval/runner.py): €${(costUsd({ ...c, wall_seconds: wall }) * EUR_PER_USD).toPrecision(2)} per question, i.e. this much per 1,000 questions like it (EUR at ${EUR_PER_USD} €/$)">${((x) => (x.startsWith("<") ? x : `≈ ${x}`))(fmtEur(costUsd({ ...c, wall_seconds: wall })))}</span>
      <span class="solver" title="Solver">${esc(a.solver || "?")}</span>
    </div>
    ${run ? `<details class="sec reason" open><summary>Reasoning <small>${run.steps.length} steps${run.calls ? ` · ${run.calls} LLM calls (local)` : ""} · numbers from tools only</small></summary>
      ${reasoningHtml(run, a)}</details>`
    : `<details class="sec" open><summary>Why <small>${(a.trace ?? []).length} steps</small></summary>
      ${traceHtml(a.trace ?? [])}</details>`}
    ${(a.assumptions ?? []).length ? `<details class="sec" open><summary>Assumptions</summary><ul class="assume">${a.assumptions!.map((t) => `<li>${esc(t)}</li>`).join("")}</ul></details>` : ""}
    ${(a.missing ?? []).length ? `<details class="sec" open><summary>What would make it certain</summary><ul class="missing">${a.missing!.map((t) => `<li>${esc(t)}</li>`).join("")}</ul></details>` : ""}
    ${sheetsHtml(ev, opts.currentFile)}
    <details class="sec" open><summary>Evidence <small>${groups.length} item${groups.length === 1 ? "" : "s"}${groups.length < ev.length ? ` (${ev.length} boxes/elements)` : ""} · click to zoom</small></summary>
      <ul class="evidence">${shown.map((g, n) => evLabel(ev, g, n + 1, opts.describeGuid, asks)).join("")}${groups.length > shown.length ? `<li class="more">+ ${groups.length - shown.length} more</li>` : ""}</ul></details>
  `;
  el.querySelectorAll<HTMLElement>(".ev-item").forEach((li) => li.addEventListener("click", () => opts.onEvidence(Number(li.dataset.i))));
  el.querySelectorAll<HTMLElement>(".subq").forEach((b) => {
    b.addEventListener("click", () => opts.onAsk?.(b.dataset.q!));
    b.addEventListener("keydown", (e) => e.key === "Enter" && opts.onAsk?.(b.dataset.q!));
  });
  const lb = el.querySelector<HTMLButtonElement>(".locate-btn");
  if (lb && opts.onLocate && loc) {
    const go = opts.onLocate;
    lb.addEventListener("click", async () => {
      lb.disabled = true;
      lb.textContent = loc.solver === "raster" ? "Reading the labels…" : "Detecting symbols…";
      try {
        await go(loc);
      } catch (e) {
        lb.parentElement!.innerHTML = `<div class="xcheck bad"><b>${esc(loc.name)} failed</b> ${esc(e)}</div>`;
      }
    });
  }
  const sb = el.querySelector<HTMLButtonElement>(".second-btn");
  if (sb && opts.onSecondOpinion) {
    const go = opts.onSecondOpinion;
    sb.addEventListener("click", async () => {
      const slot = sb.parentElement!;
      sb.disabled = true;
      sb.textContent = "Asking NVIDIA Nemotron…";
      try {
        const r = await go();
        slot.innerHTML = secondOpinionHtml(a, r.answer, r.ms);
      } catch (e) {
        slot.innerHTML = `<div class="xcheck bad"><b>Second opinion failed</b> ${esc(e)}</div>`;
      }
    });
  }
  el.querySelectorAll<HTMLButtonElement>(".sheet").forEach((b) => b.addEventListener("click", () => b.dataset.file !== opts.currentFile && opts.onOpenSheet(b.dataset.file!)));
}

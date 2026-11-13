import type { Answer, Cost, Evidence } from "./types";

// Same rates as stoa/eval/runner.py:RATES (USD). Keep in sync.
const RATES = {
  gpu_usd_per_s: 0.0006, cpu_usd_per_s: 0.000014, api_usd_per_mtok_in: 0.4, api_usd_per_mtok_out: 1.6,
  local_usd_per_mtok_in: 0.05, local_usd_per_mtok_out: 0.2,
};
const EUR_PER_USD = 0.86; // display only; fixed rate, not live

export function costUsd(c: Cost): number {
  const g = (k: string) => Number(c[k] ?? 0);
  const localIn = Math.max(0, g("llm_tokens_in") - g("api_tokens_in"));
  const localOut = Math.max(0, g("llm_tokens_out") - g("api_tokens_out"));
  let usd = g("gpu_seconds") * RATES.gpu_usd_per_s + g("wall_seconds") * RATES.cpu_usd_per_s;
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
export function crossChecks(a: Answer): { text: string; ok: boolean }[] {
  // Compound answers prefix each evidence note with its part ("door: door 1; cross-check: answer 36 vs …").
  const parts = new Set(a.plan?.parts ?? []);
  const parse = (lines: string[]) => lines.flatMap((l) => {
    const m = l.match(/cross-?check:?\s*(.*)$/i);
    if (!m) return [];
    const part = l.match(/^([^:;]+):\s/)?.[1];
    const text = (part && parts.has(part) ? `${part}: ` : "") + m[1].trim();
    return [{ text: text.replace(/\s*[✓✗]\s*/g, " ").trim(), ok: !/✗|≠|!=|disagree|mismatch|conflict/i.test(text) }];
  });
  // Evidence notes carry the specific check; the trace usually repeats it, so use the trace only as fallback.
  const fromEv = parse(a.evidence.map((e) => e.note ?? ""));
  const out = fromEv.length ? fromEv : parse(a.trace ?? []);
  return out.filter((x, i) => out.findIndex((y) => y.text === x.text) === i).slice(0, Math.max(2, parts.size));
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

function evLabel(ev: Evidence[], g: { idx: number[]; first: number }, n: number, describe: (g: string) => string) {
  const items = g.idx.map((i) => ev[i]);
  const has2D = items.some((e) => e.bbox);
  const has3D = items.some((e) => e.ifc_guid);
  const e = items.find((x) => x.bbox) ?? items[0];
  const note = items.map((x) => x.note).find((x) => x) || (e.ifc_guid ? describe(e.ifc_guid) : "evidence");
  const where = has2D && has3D ? "2D + 3D" : has3D ? "3D" : has2D ? "2D" : "";
  const projected = items.some((x) => /projected: not drawn/i.test(x.note ?? ""));
  const files = new Set(items.map((x) => x.file.split("/").pop()));
  return `<li class="ev-item" data-i="${g.idx.find((i) => ev[i].bbox) ?? g.first}" title="${esc([...files].join(" · "))}"><span class="n">${n}</span><span class="t">${esc(note.replace(/\s*\|\s*projected: not drawn on this plan\s*$/i, ""))}${projected ? `<span class="proj" title="Not drawn on this plan (cut at 1.2 m): box = the element's footprint from the IFC model">projected</span>` : ""}</span><span class="w">${where}</span></li>`;
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
    const cc = /cross-?check/i.test(t) ? " class=\"cc\"" : "";
    return m ? `<li${cc}><span class="tag">${esc(m[1])}</span>${esc(m[2])}</li>` : `<li${cc}>${esc(t)}</li>`;
  };
  const head = trace.slice(0, keep).map(li).join("");
  const rest = trace.slice(keep);
  return `<ol class="trace">${head}</ol>` + (rest.length
    ? `<details class="more-steps"><summary>${rest.length} more step${rest.length > 1 ? "s" : ""}</summary><ol class="trace" start="${keep + 1}">${rest.map(li).join("")}</ol></details>`
    : "");
}

const LANG: Record<string, string> = { de: "German", fi: "Finnish", sv: "Swedish", fr: "French", it: "Italian", nl: "Dutch", et: "Estonian", es: "Spanish", da: "Danish", pl: "Polish" };
const OP: Record<string, string> = { sum: "sum of", diff: "difference of", argmax: "largest of", argmin: "smallest of", max: "max of", min: "min of", exists: "any of" };

/** "Understood as" (W4's intent) and, for compound questions, the plan of sub-questions answered one by one. */
function intentHtml(a: Answer) {
  const it = a.intent;
  if (!it && !a.plan) return "";
  const bits: string[] = [];
  if (it) {
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

export interface CardOpts {
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
  const checks = crossChecks(a);
  const unit = a.unit ? UNIT_LABEL[a.unit] ?? a.unit : "";
  const isText = typeof a.value === "string";
  const rich = isText && (String(a.value).length > 120 || String(a.value).includes("\n"));
  const ev = a.evidence ?? [];
  const groups = groupEvidence(ev);
  const shown = groups.slice(0, 80);

  el.className = `card answer ${a.value === null ? "refused" : ""}`;
  el.innerHTML = `
    <div class="value-row${rich ? " rich" : ""}">
      ${rich ? `<span class="rich-lbl">Text answer · ${String(a.value).split(/\n+/).filter((l) => l.trim()).length} line(s)</span><div class="value text rich">${richText(String(a.value))}</div>`
        : `<div class="value ${isText ? "text" : ""} ${isText && String(a.value).length > 40 ? "long" : ""}">${esc(fmtValue(a))}${unit ? `<span class="unit">${esc(unit)}</span>` : ""}</div>`}
      <div class="conf ${confClass}" title="Calibrated confidence">
        <div class="conf-num">${conf}%</div><div class="conf-bar"><i style="width:${conf}%"></i></div><div class="conf-lbl">confidence</div>
      </div>
    </div>
    ${intentHtml(a)}
    ${checks.map((x) => `<div class="xcheck ${x.ok ? "ok" : "bad"}"><b>${x.ok ? "✓ Cross-checked" : "✗ Sources disagree"}</b> ${esc(x.text)}</div>`).join("")}
    ${cascadeHtml(tier)}
    <div class="cost">
      <span title="Wall time">⏱ ${wall < 1 ? `${Math.round(wall * 1000)} ms` : `${wall.toFixed(1)} s`}</span>
      <span title="LLM tokens in / out">${tokens ? `${(c.llm_tokens_in ?? 0).toLocaleString()} / ${(c.llm_tokens_out ?? 0).toLocaleString()} tok` : "0 tokens"}</span>
      <span title="Estimated cost of this answer with the eval's rates (stoa/eval/runner.py): €${(costUsd({ ...c, wall_seconds: wall }) * EUR_PER_USD).toPrecision(2)} per question, i.e. this much per 1,000 questions like it (EUR at ${EUR_PER_USD} €/$)">${((x) => (x.startsWith("<") ? x : `≈ ${x}`))(fmtEur(costUsd({ ...c, wall_seconds: wall })))}</span>
      <span class="solver" title="Solver">${esc(a.solver || "?")}</span>
    </div>
    <details class="sec" open><summary>Why <small>${(a.trace ?? []).length} steps</small></summary>
      ${traceHtml(a.trace ?? [])}</details>
    ${(a.assumptions ?? []).length ? `<details class="sec" open><summary>Assumptions</summary><ul class="assume">${a.assumptions!.map((t) => `<li>${esc(t)}</li>`).join("")}</ul></details>` : ""}
    ${(a.missing ?? []).length ? `<details class="sec" open><summary>What would make it certain</summary><ul class="missing">${a.missing!.map((t) => `<li>${esc(t)}</li>`).join("")}</ul></details>` : ""}
    ${sheetsHtml(ev, opts.currentFile)}
    <details class="sec" open><summary>Evidence <small>${groups.length} item${groups.length === 1 ? "" : "s"}${groups.length < ev.length ? ` (${ev.length} boxes/elements)` : ""} · click to zoom</small></summary>
      <ul class="evidence">${shown.map((g, n) => evLabel(ev, g, n + 1, opts.describeGuid)).join("")}${groups.length > shown.length ? `<li class="more">+ ${groups.length - shown.length} more</li>` : ""}</ul></details>
  `;
  el.querySelectorAll<HTMLElement>(".ev-item").forEach((li) => li.addEventListener("click", () => opts.onEvidence(Number(li.dataset.i))));
  el.querySelectorAll<HTMLElement>(".subq").forEach((b) => {
    b.addEventListener("click", () => opts.onAsk?.(b.dataset.q!));
    b.addEventListener("keydown", (e) => e.key === "Enter" && opts.onAsk?.(b.dataset.q!));
  });
  el.querySelectorAll<HTMLButtonElement>(".sheet").forEach((b) => b.addEventListener("click", () => b.dataset.file !== opts.currentFile && opts.onOpenSheet(b.dataset.file!)));
}

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

function fmtEur(usd: number) {
  const eur = usd * EUR_PER_USD;
  if (eur === 0) return "€0";
  if (eur < 0.0001) return `€${(eur * 1e6).toFixed(1)}µ`;
  if (eur < 0.01) return `€${eur.toFixed(5)}`;
  return `€${eur.toFixed(3)}`;
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
  const parse = (lines: string[]) => lines.flatMap((l) => {
    const m = l.match(/cross-?check:?\s*(.*)$/i);
    if (!m) return [];
    const text = m[1].trim();
    return [{ text: text.replace(/\s*[✓✗]\s*/g, " ").trim(), ok: !/✗|≠|!=|disagree|mismatch|conflict/i.test(text) }];
  });
  // Evidence notes carry the specific check; the trace usually repeats it, so use the trace only as fallback.
  const fromEv = parse(a.evidence.map((e) => e.note ?? ""));
  const out = fromEv.length ? fromEv : parse(a.trace ?? []);
  return out.filter((x, i) => out.findIndex((y) => y.text === x.text) === i).slice(0, 2);
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
  const files = new Set(items.map((x) => x.file.split("/").pop()));
  return `<li class="ev-item" data-i="${g.idx.find((i) => ev[i].bbox) ?? g.first}" title="${esc([...files].join(" · "))}"><span class="n">${n}</span><span class="t">${esc(note)}</span><span class="w">${where}</span></li>`;
}

/** Trace lines: "[solver] text" → tag + text; long traces show the first steps and fold the rest. */
function traceHtml(trace: string[], keep = 6) {
  const li = (t: string) => {
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

export interface CardOpts {
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
  const ev = a.evidence ?? [];
  const groups = groupEvidence(ev);
  const shown = groups.slice(0, 80);

  el.className = `card answer ${a.value === null ? "refused" : ""}`;
  el.innerHTML = `
    <div class="value-row">
      <div class="value ${isText ? "text" : ""} ${isText && String(a.value).length > 40 ? "long" : ""}">${esc(fmtValue(a))}${unit ? `<span class="unit">${esc(unit)}</span>` : ""}</div>
      <div class="conf ${confClass}" title="Calibrated confidence">
        <div class="conf-num">${conf}%</div><div class="conf-bar"><i style="width:${conf}%"></i></div><div class="conf-lbl">confidence</div>
      </div>
    </div>
    ${checks.map((x) => `<div class="xcheck ${x.ok ? "ok" : "bad"}"><b>${x.ok ? "✓ Cross-checked" : "✗ Sources disagree"}</b> ${esc(x.text)}</div>`).join("")}
    ${cascadeHtml(tier)}
    <div class="cost">
      <span title="Wall time">⏱ ${wall < 1 ? `${Math.round(wall * 1000)} ms` : `${wall.toFixed(1)} s`}</span>
      <span title="LLM tokens in / out">${tokens ? `${(c.llm_tokens_in ?? 0).toLocaleString()} / ${(c.llm_tokens_out ?? 0).toLocaleString()} tok` : "0 tokens"}</span>
      <span title="Estimated cost with the eval's rates (stoa/eval/runner.py), shown in EUR at ${EUR_PER_USD} €/$">≈ ${fmtEur(costUsd({ ...c, wall_seconds: wall }))}</span>
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
  el.querySelectorAll<HTMLButtonElement>(".sheet").forEach((b) => b.addEventListener("click", () => b.dataset.file !== opts.currentFile && opts.onOpenSheet(b.dataset.file!)));
}

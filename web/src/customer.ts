/**
 * Customer view (default): for site engineers, project managers and estimators, not for the jury's engineers.
 * Projects instead of files, one big question box, the answer as the hero in plain words, a short numbered list of
 * where it comes from, the time it saves, and the drawing-vs-model differences of the project. Everything technical
 * (solvers, cost in tokens, trace, benchmark) stays one click away: "How we worked it out" and the Expert view.
 */
import { agentAsks, crossChecks, fmtValue, setAnswer, unitLabel } from "./card";
import { manualTime } from "./manual-time";
import { floorName, PROJECTS, projectOf, type Project } from "./projects";
import type { Answer, Kg } from "./types";

const esc = (s: unknown) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const CIRCLED = "①②③④⑤⑥⑦⑧⑨";
export const circled = (i: number) => CIRCLED[i] ?? `(${i + 1})`;

// ---------- view mode ----------
export type View = "customer" | "expert";
export function initialView(): View {
  const q = new URLSearchParams(location.search).get("view");
  if (q === "expert" || q === "customer") return q;
  try {
    return localStorage.getItem("be-view") === "expert" ? "expert" : "customer";
  } catch {
    return "customer";
  }
}
export function saveView(v: View) {
  try {
    localStorage.setItem("be-view", v);
  } catch {
    /* private window: the URL keeps it */
  }
}

// ---------- landing: project cards ----------
export function landingHtml(): string {
  const card = (p: Project) => `<button type="button" class="proj-card" data-project="${esc(p.id)}">
      <span class="pc-kind">${esc(KIND_LABEL[p.kind])}</span>
      <span class="pc-name">${esc(p.name)}</span>
      <span class="pc-place">${esc(p.place)}</span>
      <span class="pc-facts">${p.facts.map(esc).join(" · ")}</span>
      <span class="pc-contents">${esc(p.contents)}</span>
      <span class="pc-ask">“${esc(p.chips[0])}”</span>
    </button>`;
  return `<div class="landing-inner">
    <header class="landing-head">
      <div class="logo">B</div>
      <div><h1>Blueprint Evidence</h1><p>Ask your drawings and building models a question. Get the answer, and see exactly where it comes from.</p></div>
      <div class="landing-actions"><button type="button" class="tour" data-act="tour">Guided demo ▸</button><button type="button" class="view-toggle" data-act="expert">Expert view</button></div>
    </header>
    <h2>Choose a project</h2>
    <div class="proj-grid">${PROJECTS.map(card).join("")}
      <button type="button" class="proj-card own" data-project="upload">
        <span class="pc-kind">Your files</span>
        <span class="pc-name">＋ Your own drawing</span>
        <span class="pc-place">PDF, PNG, JPG or IFC model</span>
        <span class="pc-facts">Drop a plan and its 3D model together and they are linked</span>
        <span class="pc-contents">kept only on this computer</span>
      </button>
    </div>
    <p class="landing-foot">Drawings and models are public samples (credits under each project). Answers come with where they come from, so anyone can check them in seconds.</p>
  </div>`;
}
const KIND_LABEL: Record<Project["kind"], string> = {
  building: "Building · drawings + 3D", model: "Building · 3D model", floor: "Floor plan", schedule: "Drawing set", plan: "Floor plan", historic: "Historic drawing",
};

// ---------- the answer, in plain words ----------
const NOUN: Record<string, [string, string]> = {
  door: ["door", "doors"], window: ["window", "windows"], room: ["room", "rooms"], space: ["room", "rooms"],
  wall: ["wall", "walls"], column: ["column", "columns"], stair: ["staircase", "staircases"], bedroom: ["bedroom", "bedrooms"],
  bathroom: ["bathroom", "bathrooms"], kitchen: ["kitchen", "kitchens"], sauna: ["sauna", "saunas"], apartment: ["apartment", "apartments"],
  unit: ["apartment", "apartments"], storey: ["floor", "floors"], toilet: ["toilet", "toilets"], wc: ["toilet", "toilets"],
  sink: ["sink", "sinks"], slab: ["slab", "slabs"], beam: ["beam", "beams"], railing: ["railing", "railings"],
};

export interface HeroCtx {
  question: string;
  file: string;
  roundTripMs: number;
  /** the sheet label of a path in the current project ("Floor 2"), or "" */
  sheetLabel: (path: string) => string;
}

export function confidenceWords(c: number): { cls: string; word: string; hint: string } {
  if (c >= 0.9) return { cls: "sure", word: "Very sure", hint: "" };
  if (c >= 0.7) return { cls: "fair", word: "Fairly sure", hint: "check the marked spots" };
  return { cls: "est", word: "Best estimate", hint: "" };
}

/** Where the answer applies, in words: "on floor 2", "in the whole building", "on this floor". */
function wherePhrase(a: Answer, ctx: HeroCtx): string {
  const st = a.intent?.filters?.storey;
  if (st) return `on ${floorName(String(st))}`;
  if (a.intent?.scope === "model" || /\b(whole|entire) building\b|\bin (this|the) model\b/i.test(ctx.question)) return "in the whole building";
  const label = ctx.sheetLabel(ctx.file);
  if (/\.ifc$/i.test(ctx.file)) return "in the 3D model";
  if (/^floor \d|floor$/i.test(label)) return `on ${label.toLowerCase().replace(/^(\d)/, "the $1")}`;
  return /\.(png|jpe?g|pdf)$/i.test(ctx.file) ? "on this drawing" : "";
}

/** Big value + one plain sentence. Yes/no answers lead with Yes / No. */
function headline(a: Answer, ctx: HeroCtx): { big: string; unit: string; sentence: string; text?: string; name?: boolean; next?: string[] } {
  const v = a.value;
  if (v === null || v === undefined) return { big: "No answer", unit: "", sentence: (a.missing ?? [])[0] ?? "We could not find this on the drawing." };
  if (typeof v === "boolean") return { big: v ? "Yes" : "No", unit: "", sentence: "" };
  if (typeof v === "string") {
    const yn = v.match(/^\s*(yes|no)\b[\s,.:;-]*\(?(.*?)\)?\s*$/is);
    if (yn) return { big: yn[1][0].toUpperCase() + yn[1].slice(1).toLowerCase(), unit: "", sentence: plainify(yn[2]) };
    if (v.length <= 28 && !v.includes("\n")) return { big: v, unit: "", sentence: "", name: !/^\d/.test(v) && v.length > 10 };
    // a ranking ("Largest rooms (…):\n- KORIDOR (105) on 1.korrus: 78.40 m²\n…"): the first one is the answer
    const rows = v.split("\n").map((l) => l.match(/^\s*[-•]\s*(.+?)(?:\s+on\s+[^:]+)?:\s*([\d.,]+)\s*(m²|m2|m)/)).filter((m): m is RegExpMatchArray => !!m);
    const sup = ctx.question.match(/\b(biggest|largest|smallest|tallest|highest|lowest|most|least)\b/i);
    if (rows.length >= 1 && sup) {
      const u = rows[0][3].replace("m2", "m²");
      const where = wherePhrase(a, ctx);
      return { big: rows[0][1], unit: "", name: true, sentence: `the ${sup[1].toLowerCase()} ${a.intent?.target === "room" || /room/i.test(ctx.question) ? "room" : "one"}${where ? ` ${where}` : ""}: ${rows[0][2]} ${u}`,
        next: rows.slice(1, 5).map((r) => `${r[1]} · ${r[2]} ${r[3].replace("m2", "m²")}`) };
    }
    return { big: "", unit: "", sentence: "", text: plainify(v) };
  }
  const unit = unitLabel(a.unit);
  const t = a.intent?.target ?? "";
  const n = NOUN[t];
  const where = wherePhrase(a, ctx);
  if (a.unit === "count" || (!a.unit && Number.isInteger(v))) {
    const noun = n ? n[Number(v) === 1 ? 0 : 1] : "";
    return { big: fmtValue(a), unit: "", sentence: [noun, where].filter(Boolean).join(" ") };
  }
  if (unit === "€" || unit === "$") return { big: `${unit}${fmtValue(a)}`, unit: "", sentence: costSentence(ctx.question) };
  const room = a.intent?.filters?.room ? String(a.intent.filters.room) : "";
  const what = a.intent?.task === "area" ? (room ? `floor area of ${room}` : "floor area") : a.intent?.task === "length" ? "length" : a.intent?.task === "volume" ? "volume" : "";
  return { big: fmtValue(a), unit, sentence: [what, where].filter(Boolean).join(" ") };
}
const plainify = (s: string) => s.replace(/'?(\d+)\.korrus'?/g, (_, n) => `floor ${n}`).replace(/\bstorey\b/g, "floor").replace(/\bIFC model\b/g, "3D model").replace(/\bplan draws\b/g, "the drawing shows")
  .replace(/\bthe plan's\b/g, "the drawing's").trim();
function costSentence(q: string) {
  const m = q.match(/(\d[\d,.]*)\s*(euros?|eur|€|dollars?|usd|\$)/i);
  return m ? `in total, at ${m[1]} ${/^(e|€)/i.test(m[2]) ? "€" : "$"} each` : "in total";
}

/** Which kind of second source agreed, in words. */
function agreement(a: Answer, file: string): { ok: boolean; text: string; detail: string } | null {
  const xs = crossChecks(a, agentAsks(a)).filter((x) => !/^skipped\b/i.test(x.text));
  if (!xs.length) return null;
  const bad = xs.find((x) => !x.ok);
  if (bad) return { ok: false, text: "Two sources disagree: check the marked spots", detail: bad.text };
  const t = xs[0].text;
  const sheet = /\.(pdf|png|jpe?g)$/i.test(file);
  const text = /\bIFC\b|3D model|model:/i.test(t) && sheet ? "Drawing and 3D model agree"
    : /\bIFC\b|model/i.test(t) ? "Checked against the 3D model"
    : /\bDXF\b|CAD/i.test(t) ? "The drawing's CAD file agrees"
    : /sheet's own text labels/i.test(t) ? "The drawing's labels agree"
    : /segmentation|detector|reader|label/i.test(t) ? "A second reading of the drawing agrees"
    : /schedule/i.test(t) ? "The schedule agrees"
    : "Checked against a second source";
  return { ok: true, text, detail: t };
}

/** A short, human label for one piece of evidence. */
function evidenceLabel(note: string): string {
  let s = (note ?? "").split(/;\s*cross-?check:/i)[0].split(" | ")[0].trim();
  s = s.replace(/^(label reader|CubiCasa5K detector|door-swing reader):\s*/i, "")
    .replace(/^named in the answer:\s*/i, "").replace(/^sheet label '([^']+)'.*$/i, "$1")
    .replace(/\bIfc(Door|Window|Space|Wall|WallStandardCase|Slab|Column|Stair|Beam|Railing|SanitaryTerminal|FlowTerminal)\b/g, (_, k) => k === "WallStandardCase" ? "Wall" : k === "Space" ? "Room" : k)
    .replace(/\s*\(GlobalId[^)]*\)/i, "").replace(/\s+/g, " ");
  return s.length > 60 ? s.slice(0, 57).replace(/\s+\S*$/, "") + "…" : s || "marked spot";
}

export function heroLoadingHtml(q: string) {
  return `<div class="hero-loading"><div class="spinner"></div><div><b>Looking it up…</b><small>${esc(q)}</small><small class="elapsed"></small></div></div>`;
}

export function heroHtml(a: Answer, ctx: HeroCtx): string {
  const h = headline(a, ctx);
  const c = a.value === null ? { cls: "none", word: "No answer", hint: "" } : confidenceWords(a.confidence ?? 0);
  const assumption = c.cls === "est" ? (a.assumptions ?? [])[0] : "";
  const ag = agreement(a, ctx.file);
  const wall = a.cost?.wall_seconds && a.cost.wall_seconds > 0 ? a.cost.wall_seconds : ctx.roundTripMs / 1000;
  const mt = manualTime(a.intent?.task, a.intent?.scope, ctx.question);
  const set = typeof a.value === "string" ? setAnswer(a, ctx.file) : null;
  const ev = a.evidence ?? [];
  // the numbered list: the first few distinct places (the viewer numbers the same ones)
  const shown = numbered(ev);
  const more = numbered(ev, Infinity).length - shown.length;
  const place = (i: number) => {
    const e = ev[i];
    if (e.ifc_guid && !e.bbox) return "3D model";
    return ctx.sheetLabel(e.file) || (e.file === ctx.file ? "this drawing" : e.file.split("/").pop()!.replace(/\.[^.]+$/, ""));
  };
  const text = h.text && !set ? `<div class="hero-text">${esc(h.text).split(/\n+/).filter((l) => l.trim()).slice(0, 8).map((l) => `<div>${l}</div>`).join("")}</div>` : "";
  const setRows = set ? `<div class="hero-set">${set.head ? `<div class="hs-head">${esc(plainify(set.head))}</div>` : ""}${set.rows.slice(0, 8).map((r) =>
    `<button type="button" class="hs-row"${r.ev >= 0 ? ` data-ev="${r.ev}"` : ""}><span>${esc(r.name)}</span><b>${esc(r.detail)}</b></button>`).join("")}${set.rows.length > 8 ? `<div class="hs-more">+ ${set.rows.length - 8} more</div>` : ""}</div>` : "";
  return `
    ${h.big ? `<div class="hero-value"><span class="big${h.name ? " name" : ""}">${esc(h.big)}</span>${h.unit ? `<span class="unit">${esc(h.unit)}</span>` : ""}</div>` : ""}
    ${h.sentence ? `<div class="hero-sentence">${esc(h.sentence)}</div>` : ""}
    ${h.next?.length ? `<div class="hero-next"><span>Next:</span> ${h.next.map(esc).join(" &nbsp;·&nbsp; ")}</div>` : ""}
    ${text}${setRows}
    <div class="hero-badges">
      <span class="conf ${c.cls}" title="Our calibrated confidence: ${Math.round((a.confidence ?? 0) * 100)} %">${esc(c.word)}</span>${c.hint ? `<span class="conf-hint">${esc(c.hint)}</span>` : ""}
      ${ag ? `<span class="agree ${ag.ok ? "ok" : "bad"}" title="${esc(ag.detail)}">${ag.ok ? "✓" : "⚠"} ${esc(ag.text)}</span>` : ""}
    </div>
    ${assumption ? `<div class="hero-assume">Assumed: ${esc(assumption)}</div>` : ""}
    <div class="hero-value-strip" title="Manual time is our rough estimate for this kind of question (${esc(mt.work)}), not a measurement">
      <span>Answered in <b>${wall < 1 ? `${Math.max(0.1, wall).toFixed(1)} s` : `${wall.toFixed(1)} s`}</b></span>
      <span>about <b>${mt.minutes} min</b> by hand <small>(estimate)</small></span>
    </div>
    ${shown.length ? `<div class="hero-where"><div class="hw-title">Where it comes from</div>
      ${shown.map((i, k) => `<button type="button" class="hw-item" data-ev="${i}"><span class="num">${circled(k)}</span><span class="lbl">${esc(place(i))} · ${esc(evidenceLabel(ev[i].note ?? ""))}</span></button>`).join("")}
      ${more > 0 ? `<div class="hw-more">+ ${more} more, all marked ${ev.some((e) => e.bbox) ? "on the drawing" : "in the 3D model"}</div>` : ""}</div>` : ""}`;
}

/** The evidence items that get a number (①…⑤): the first ones with a place, one per element. */
export function numbered(ev: Answer["evidence"], max = 5): number[] {
  const out: number[] = [];
  const seen = new Set<string>();
  ev.forEach((e, i) => {
    if (out.length >= max || !(e.bbox || e.ifc_guid)) return;
    const k = e.ifc_guid ?? `${e.file}|${(e.bbox ?? []).join(",")}`;
    if (seen.has(k)) return;
    // a 2D box and its element's GlobalId are the same thing: number the box (it is what the plan shows)
    if (e.ifc_guid && !e.bbox && ev.some((x) => x.bbox && x.ifc_guid === e.ifc_guid)) return;
    seen.add(k);
    out.push(i);
  });
  return out;
}

// ---------- differences: drawing vs 3D model, every floor of the project ----------
export interface Difference {
  sheet: string;
  label: string;
  storey: string;
  kind: string;
  drawn: number;
  model: number;
  explained: number;
}
export async function projectDifferences(p: Project, kgOf: (path: string) => Promise<Kg | null>): Promise<Difference[]> {
  const sheets = p.sheets.filter((s) => /\.pdf$/i.test(s.path));
  const kgs = await Promise.all(sheets.map((s) => kgOf(s.path).catch(() => null)));
  const out: Difference[] = [];
  kgs.forEach((k, i) => {
    const st = (k as unknown as { storey?: { name?: string; cut?: Record<string, { model: number; drawn: number; model_cut?: number }> } } | null)?.storey;
    for (const [kind, c] of Object.entries(st?.cut ?? {})) {
      if (c.model === c.drawn) continue;
      out.push({ sheet: sheets[i].path, label: sheets[i].label, storey: st?.name ?? "", kind, drawn: c.drawn, model: c.model,
        explained: c.model_cut === c.drawn ? c.model - c.drawn : 0 });
    }
  });
  return out;
}
export function diffsHtml(d: Difference[], p: Project): string {
  if (!d.length) return "";
  const allExplained = d.every((x) => x.explained === x.model - x.drawn);
  return `<div class="diffs-head"><b>Differences found</b><span>${d.length}</span></div>
    <p class="diffs-sub">Drawings vs 3D model, checked floor by floor for ${esc(p.name)}.${allExplained ? " Each one is explained: those elements sit above or below the height where the floor plan is cut (normal for floor plans)." : ""}</p>
    ${d.map((x, i) => `<div class="diff"><div><b>${esc(x.label)}:</b> the drawing shows ${x.drawn} ${esc(x.kind)}, the 3D model has ${x.model}${x.explained ? ` <small>(${x.explained} above/below the cut)</small>` : ""}</div>
      <button type="button" class="diff-go" data-diff="${i}">Show me</button></div>`).join("")}`;
}
/** The question behind "Show me" (W5 cycle 7: checked end to end for windows on 4 projects). */
export const diffQuestion = (x: Difference) => `How many ${x.kind} on '${x.storey}' are in the model but not drawn on this plan?`;

export { projectOf, PROJECTS };

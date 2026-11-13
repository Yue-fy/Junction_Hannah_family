import "./style.css";
import { ask, benchmark, exampleQuestions, fileUrl, knowledgeGraph, listFiles, onBackend } from "./api";
import { renderBench } from "./bench";
import { crossChecks, renderCard } from "./card";
import { markAnswerCheck, renderKg } from "./kg";
import type { Answer, FileInfo, KgRoom } from "./types";
import { Viewer2D } from "./viewer2d";
import type { Viewer3D } from "./viewer3d"; // loaded lazily: web-ifc + three are ~4 MB

const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;

type Mode = "2d" | "3d" | "split";
const state: { file: FileInfo | null; answer: Answer | null; mode: Mode; files: FileInfo[]; ifc: string | null } = {
  file: null, answer: null, mode: "2d", files: [], ifc: null,
};

const v2d = new Viewer2D($("v2d"));
let v3d: Viewer3D | null = null;
async function viewer3d(): Promise<Viewer3D> {
  if (!v3d) {
    const { Viewer3D } = await import("./viewer3d");
    v3d ??= makeViewer3D(Viewer3D);
  }
  return v3d;
}

function makeViewer3D(Ctor: typeof Viewer3D) {
  const v = new Ctor($("v3d"));
  v.onPick = (guid, label, props) => {
    const pick = $("pick");
    pick.hidden = false;
    pick.innerHTML = `<b>${esc(label)}</b>` + Object.entries(props).filter(([, val]) => val)
      .map(([k, val]) => `<div><span>${esc(k)}</span>${esc(val)}</div>`).join("");
    if (v2d.hasGuid(guid)) {
      v2d.highlightGuids([guid], "picked");
      if (state.mode === "split") v2d.focusGuid(guid);
    }
    followUp(guid);
  };
  return v;
}

v2d.onPickGuid = (guid, label) => {
  v2d.highlightGuids([guid], "picked");
  if (v3d && state.ifc && v3d.hasGuid(guid)) {
    v3d.focusGuid(guid);
    const pick = $("pick");
    pick.hidden = false;
    pick.innerHTML = `<b>${esc(label)}</b><div><span>GlobalId</span>${esc(guid)}</div><div><span>picked on</span>drawing</div>`;
    followUp(guid);
  }
};

/** A one-click question about the picked element (room → area, door/window → count on its storey). */
function followUp(guid: string) {
  const info = v3d?.info(guid);
  if (!info) return;
  const t = info.type.toUpperCase();
  let q = "";
  if (t === "IFCSPACE") {
    const room = info.longName ? `${info.longName} (${info.name})` : info.name;
    q = `What is the net floor area of the room '${room}'${info.storey ? ` on '${info.storey}'` : ""}, in m²?`;
  } else if (/IFCDOOR|IFCWINDOW|IFCCOLUMN|IFCSTAIR/.test(t)) {
    const kind = t.includes("DOOR") ? "doors" : t.includes("WINDOW") ? "windows" : t.includes("COLUMN") ? "columns" : "stairs";
    q = info.storey ? `How many ${kind} are shown on the floor plan of '${info.storey}'?` : `How many ${kind} are there in the model?`;
  }
  if (!q) return;
  const b = document.createElement("button");
  b.className = "ask-this";
  b.textContent = `Ask: ${q}`;
  b.addEventListener("click", () => {
    $<HTMLTextAreaElement>("question").value = q;
    void runAsk();
  });
  $("pick").append(b);
}
v2d.onPickEvidence = (i) => focusEvidence(i);

export const esc = (s: unknown) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

// ---------------------------------------------------------------------------------------------------------
onBackend((b) => {
  const el = $("backend");
  el.textContent = b === "live" ? "API live" : b === "mock" ? "API mock" : "API ?";
  el.className = `badge ${b}`;
  el.title = b === "live" ? "Answers come from stoa.api on :8100" : "stoa.api on :8100 not reachable: precomputed fixture answers";
});

function setMode(mode: Mode) {
  state.mode = mode;
  $("views").dataset.mode = mode;
  document.querySelectorAll<HTMLButtonElement>("#modes button").forEach((b) => b.classList.toggle("on", b.dataset.mode === mode));
  if (mode !== "2d" && state.ifc) void ensure3D();
  setTimeout(() => window.dispatchEvent(new Event("resize")), 0);
}
document.querySelectorAll<HTMLButtonElement>("#modes button").forEach((b) => b.addEventListener("click", () => setMode(b.dataset.mode as Mode)));

let loading3D: Promise<void> | null = null;
async function ensure3D() {
  if (!state.ifc) return;
  const ifc = state.ifc;
  const label = $("load3d");
  if (!v3d) {
    label.textContent = "loading 3D engine…";
    label.hidden = false;
  }
  const v = await viewer3d();
  if (v.file === ifc) return loading3D ?? undefined;
  label.textContent = "loading model…";
  label.hidden = false;
  loading3D = v.load(ifc, fileUrl(ifc), (msg) => (label.textContent = msg)).then(() => {
    if (state.ifc !== ifc) return;
    label.hidden = true;
    fillStoreys();
    if (state.answer) applyEvidence3D(state.answer);
  }).catch((e) => {
    label.textContent = `could not load model: ${e}`;
  });
  return loading3D;
}

function fillStoreys() {
  const sel = $<HTMLSelectElement>("storey");
  const v = v3d;
  if (!v || !v.storeys.length) {
    sel.hidden = true;
    return;
  }
  sel.hidden = false;
  sel.innerHTML = `<option value="">All storeys</option>` + v.storeys.map((s) => `<option value="${s.id}">${esc(s.name)}</option>`).join("");
  // a plan sheet → its storey ("…_plan-01-1-korrus.pdf" ↔ "1.korrus")
  const m = state.file?.path.match(/_plan-\d+-(.*)\.pdf$/);
  const key = m?.[1].replace(/[^a-z0-9]/gi, "").toLowerCase();
  const s = key ? v.storeys.find((x) => x.name.replace(/[^a-z0-9]/gi, "").toLowerCase() === key) : undefined;
  sel.value = s ? String(s.id) : "";
  v.setStorey(s ? s.id : null);
}
$<HTMLSelectElement>("storey").addEventListener("change", (e) => {
  const val = (e.target as HTMLSelectElement).value;
  v3d?.setStorey(val ? Number(val) : null);
});

$("fitBtn").addEventListener("click", () => {
  v2d.frameEvidence();
  if (v3d && state.answer) applyEvidence3D(state.answer);
});

$("benchBtn").addEventListener("click", async () => {
  const el = $("bench");
  if (!el.hidden) return void (el.hidden = true);
  el.hidden = false;
  el.innerHTML = `<p class="bn-empty">Loading the leaderboard…</p>`;
  try {
    renderBench(el, await benchmark());
  } catch (e) {
    el.innerHTML = `<p class="bn-empty">No benchmark data (${esc(e)}).</p>`;
  }
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") $("bench").hidden = true;
});

// --- files --------------------------------------------------------------------------------------------------
// Demo files pinned on top (train split / demo-safe; see board W5). The live API lists alphabetically.
const DEMO = [
  "data/ifc_models/bsc-esplanades_1807-ep-ar-v18_plan-01-1-korrus.pdf",
  "data/swiss_dwellings/site1000_bldg2082_floor9385.pdf",
  "data/opening_design/Sports_Complex/Sheets - Current Set/A-801 - Door and Finish Schedules & Wall Types.pdf",
  "data/ifc_models/bsc-duplex_duplex-a-20110907.ifc",
  "data/cubicasa5k/colorful-10052.png",
];
let demoFiles: FileInfo[] | null = null;
const HISTORICAL = ["habs", "finna", "europeana", "wikimedia"];
// Scans have no dataset questions; Stoa says the hidden set may ask about them, so offer general ones.
const GENERIC_QUESTIONS = [
  "What kind of drawing is this (floor plan, elevation, section, site plan)?",
  "How many storeys does this building have?",
  "What is the scale of this drawing?",
  "How many windows are shown on this drawing?",
];

async function refreshFiles() {
  const source = $<HTMLSelectElement>("source").value;
  const q = $<HTMLInputElement>("search").value;
  const list = await listFiles(source, q, 80, !HISTORICAL.includes(source));
  if (!source && !q) {
    demoFiles ??= (await Promise.all(DEMO.map((p) => listFiles("", p, 3).then((r) => r.find((x) => x.path === p)).catch(() => undefined))))
      .filter((x): x is FileInfo => !!x);
    state.files = [...demoFiles, ...list.filter((f) => !DEMO.includes(f.path))];
  } else state.files = list;
  const ul = $("files");
  ul.innerHTML = state.files.map((f, i) => {
    const name = f.path.split("/").pop()!;
    const sib = Object.keys(f.siblings ?? {}).map((e) => `<span class="ext">${esc(e.slice(1))}</span>`).join("");
    return `<li data-i="${i}" class="${state.file?.path === f.path ? "on" : ""}"><span class="src ${esc(f.source)}">${esc(f.source.replace(/_.*/, ""))}</span>
      <span class="name" title="${esc(f.path)}">${esc(name)}</span><span class="meta">${f.n_questions} q ${sib}</span></li>`;
  }).join("") || `<li class="none">No files match.</li>`;
}
$("files").addEventListener("click", (e) => {
  const li = (e.target as HTMLElement).closest("li[data-i]") as HTMLElement | null;
  if (li) void openFile(state.files[Number(li.dataset.i)]);
});
let searchTimer = 0;
$("search").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = window.setTimeout(refreshFiles, 200);
});
$("source").addEventListener("change", refreshFiles);

/** Open a file. With `keep`, the current answer stays and its evidence on this file is drawn (multi-sheet). */
async function openFile(f: FileInfo, question = "", keep: Answer | null = null, focusIndex: number | null = null) {
  state.file = f;
  state.answer = null;
  const url = new URL(location.href);
  url.searchParams.set("file", f.path);
  url.searchParams.delete("q");
  history.replaceState(null, "", url);
  document.querySelectorAll("#files li").forEach((li) => li.classList.toggle("on", state.files[Number((li as HTMLElement).dataset.i)]?.path === f.path));
  $("fileTitle").textContent = f.path.split("/").pop()!;
  $("fileMeta").textContent = `${f.source} · ${f.n_questions} questions`;
  $("credit").innerHTML = creditLine(f);
  if (!keep) {
    markAnswerCheck($("linked"), undefined, undefined);
    $("xbanner").hidden = true;
    $("card").className = "card empty";
    $("card").innerHTML = `<p class="hint">Ask a question about this ${f.ext === ".ifc" ? "model" : "drawing"}.</p>`;
  }
  $("pick").hidden = true;
  $("bench").hidden = true;
  $<HTMLTextAreaElement>("question").value = question;

  const is3DOnly = f.ext === ".ifc";
  state.ifc = is3DOnly ? f.path : f.siblings?.[".ifc"] ?? null;
  $("pane2d").hidden = is3DOnly;
  document.querySelectorAll<HTMLButtonElement>("#modes button").forEach((b) => {
    b.disabled = (b.dataset.mode !== "2d" && !state.ifc) || (b.dataset.mode !== "3d" && is3DOnly);
  });
  $<HTMLSelectElement>("storey").hidden = true;
  if (v3d && state.ifc && v3d.file === state.ifc) fillStoreys(); // same model, other sheet: follow its storey
  if (!keep) setMode(is3DOnly ? "3d" : state.ifc ? "split" : "2d");
  else setMode(is3DOnly ? "3d" : state.mode === "3d" && state.ifc ? "split" : state.ifc ? state.mode : "2d");

  void loadExamples(f);
  void loadLinked(f);
  if (!is3DOnly) {
    const label = $("load2d");
    label.hidden = false;
    label.textContent = "rendering drawing…";
    try {
      await v2d.load(f.path, fileUrl(f.path));
      if (f.siblings?.[".svg"] && f.source === "ifc_models") {
        const n = await v2d.loadGuidLayer(fileUrl(f.siblings[".svg"]));
        $("fileMeta").textContent += ` · ${n} IFC elements linked on the sheet`;
      }
      label.hidden = true;
    } catch (e) {
      label.textContent = `could not render: ${e}`;
    }
  }
  if (keep && state.file?.path === f.path) {
    showAnswer(keep, 0);
    if (focusIndex !== null) focusEvidence(focusIndex);
  }
}

async function openSheet(path: string, focusIndex: number | null = null, keepAnswer = true) {
  const a = keepAnswer ? state.answer : null;
  const q = $<HTMLTextAreaElement>("question").value;
  const info = (await listFiles("", path, 5).catch(() => [])).find((x) => x.path === path)
    ?? (await listFiles(path.split("/")[1], path, 5, false).catch(() => [])).find((x) => x.path === path)
    ?? { path, source: path.split("/")[1], ext: "." + path.split(".").pop()!.toLowerCase(), siblings: siblingsGuess(path, []),
      n_questions: 0, license: state.file?.license ?? "", credit: state.file?.credit ?? "", title: "", source_url: "" };
  await openFile(info, keepAnswer ? q : "", a, focusIndex);
}

function creditLine(f: FileInfo) {
  const title = f.title ? `<b>${esc(f.title)}</b> · ` : "";
  const src = f.source_url ? ` · <a href="${esc(f.source_url)}" target="_blank" rel="noopener">source</a>` : "";
  return `${title}${esc(f.credit)} · licence <b>${esc(f.license)}</b>${src}`;
}

async function loadExamples(f: FileInfo) {
  const sel = $<HTMLSelectElement>("examples");
  sel.innerHTML = `<option value="">Example questions…</option>`;
  $("chips").innerHTML = "";
  try {
    const qs = await exampleQuestions(f.path);
    if (state.file?.path !== f.path) return;
    const chips = $("chips");
    const english = qs.filter((q) => /\b(how many|what|which|is there|are there)\b/i.test(q.question));
    // one question per template ('…' and numbers blanked), interleaved across answer types, fixtures first
    const tpl = (q: string) => q.replace(/'[^']*'/g, "''").replace(/\d+(\.\d+)?/g, "#");
    const uniq = english.filter((q, i, arr) => arr.findIndex((x) => tpl(x.question) === tpl(q.question)) === i);
    const byType = new Map<string, typeof uniq>();
    for (const q of uniq) byType.set(q.type || String(q.unit), [...(byType.get(q.type || String(q.unit)) ?? []), q]);
    const interleaved: typeof uniq = [];
    for (let k = 0; interleaved.length < uniq.length; k++)
      for (const l of byType.values()) if (l[k]) interleaved.push(l[k]);
    const pick = qs.length ? [...english.filter((q) => q.has_fixture), ...interleaved.filter((q) => !q.has_fixture)].slice(0, 4)
      : GENERIC_QUESTIONS.map((question) => ({ question, type: "", unit: null }));
    chips.innerHTML = pick.map((q) => `<button type="button" class="chip" title="${esc(q.question)}">${esc(q.question.length > 64 ? q.question.slice(0, 61) + "…" : q.question)}</button>`).join("");
    chips.querySelectorAll<HTMLButtonElement>(".chip").forEach((b, i) => b.addEventListener("click", () => {
      $<HTMLTextAreaElement>("question").value = pick[i].question;
      void runAsk();
    }));
    sel.innerHTML = `<option value="">More example questions (${qs.length})…</option>` + qs.map((q) =>
      `<option value="${esc(q.question)}">${q.has_fixture ? "★ " : ""}${esc(q.question.length > 110 ? q.question.slice(0, 107) + "…" : q.question)}</option>`).join("");
  } catch {
    /* keep empty */
  }
}
$("examples").addEventListener("change", (e) => {
  const v = (e.target as HTMLSelectElement).value;
  if (v) {
    $<HTMLTextAreaElement>("question").value = v;
    void runAsk();
  }
});

async function loadLinked(f: FileInfo) {
  const el = $("linked");
  el.innerHTML = "";
  try {
    const kg = await knowledgeGraph(f.path);
    if (state.file?.path !== f.path) return;
    renderKg(el, kg, {
      current: f.path,
      openPath: (p) => void openSheet(p, null, false),
      show3D: () => setMode(state.mode === "2d" ? "split" : state.mode),
      setStorey: (name) => void showStorey(name),
      focusRoom: (r, label) => void focusKgRoom(r, label),
      ask: (q) => {
        $<HTMLTextAreaElement>("question").value = q;
        void runAsk();
      },
    });
  } catch {
    /* no kg */
  }
}

/** Storey row in the knowledge-graph panel → show that storey in 3D. */
async function showStorey(name: string) {
  if (!state.ifc) return;
  if (state.mode === "2d") setMode("split");
  await ensure3D();
  const s = v3d?.storeys.find((x) => x.name === name);
  if (!s || !v3d) return;
  v3d.setStorey(s.id);
  $<HTMLSelectElement>("storey").value = String(s.id);
}

/** Room row in the knowledge-graph panel → outline it on the drawing (exact polygon via the GUID layer, else its box) and frame it in 3D. */
async function focusKgRoom(r: KgRoom, label: string) {
  const f = state.file;
  if (!f) return;
  if (r.guid && v2d.hasGuid(r.guid)) {
    v2d.markBox(null);
    v2d.highlightGuids([r.guid], "picked");
    v2d.focusGuid(r.guid);
  } else if (r.bbox_pt && f.ext !== ".ifc" && (!r.plan || r.plan === f.path)) {
    // swiss PNG = the PDF page at 150 dpi (KNOWLEDGE 00:23)
    if (f.ext === ".pdf") v2d.markBox(r.bbox_pt, label);
    else v2d.markBox(r.bbox_pt.map((v) => (v * 150) / 72), label, "image_px");
  }
  if (r.guid && state.ifc) {
    if (state.mode === "2d") setMode("split");
    await ensure3D();
    if (v3d?.hasGuid(r.guid)) {
      v3d.focusGuid(r.guid);
      const pick = $("pick");
      pick.hidden = false;
      pick.innerHTML = `<b>${esc(label)}</b><div><span>GlobalId</span>${esc(r.guid)}</div>` +
        (r.area_m2 !== undefined ? `<div><span>IFC area</span>${esc(r.area_m2.toFixed(2))} m²</div>` : "") +
        (r.drawn_area_m2 != null ? `<div><span>drawn area</span>${esc(r.drawn_area_m2.toFixed(2))} m² (${esc(r.plan_scale ?? "")})</div>` : "");
      followUp(r.guid);
    }
  }
}

function siblingsGuess(p: string, all: string[]) {
  const stem = p.replace(/\.[^.]+$/, "");
  const out: Record<string, string> = {};
  for (const x of all) if (x !== p && x.replace(/\.[^.]+$/, "") === stem) out["." + x.split(".").pop()] = x;
  const m = p.match(/^(.*?)_(plan|section|elevation)-/);
  if (m) out[".ifc"] = `${m[1]}.ifc`;
  if (p.startsWith("data/ifc_models/") && /\.pdf$/.test(p)) out[".svg"] = stem + ".svg";
  return out;
}

// --- ask -------------------------------------------------------------------------------------------------
$("askForm").addEventListener("submit", (e) => {
  e.preventDefault();
  void runAsk();
});
$("question").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    void runAsk();
  }
});

async function runAsk() {
  const f = state.file;
  const q = $<HTMLTextAreaElement>("question").value.trim();
  if (!f || !q) return;
  const url = new URL(location.href);
  url.searchParams.set("q", q);
  history.replaceState(null, "", url);
  const card = $("card");
  card.className = "card loading";
  card.innerHTML = `<div class="spinner"></div><p>Answering… <small>cheapest solver first (rules → local model → hosted model)</small></p>`;
  $<HTMLButtonElement>("askBtn").disabled = true;
  const t0 = performance.now();
  try {
    const a = await ask(f.path, q);
    if (state.file?.path !== f.path) return;
    await showAnswer(a, performance.now() - t0);
  } catch (e) {
    card.className = "card error";
    card.innerHTML = `<p><b>Request failed.</b> ${esc(e)}</p>`;
  } finally {
    $<HTMLButtonElement>("askBtn").disabled = false;
  }
}

async function showAnswer(a: Answer, roundTripMs: number) {
  state.answer = a;
  renderCard($("card"), a, {
    roundTripMs: roundTripMs || (a.cost?.wall_seconds ?? 0) * 1000, onEvidence: focusEvidence,
    describeGuid: (g) => v3d?.describe(g) ?? g, currentFile: state.file?.path ?? "", onOpenSheet: (p) => void openSheet(p),
    onAsk: (q) => {
      $<HTMLTextAreaElement>("question").value = q;
      void runAsk();
    },
  });
  v2d.setEvidence(a.evidence);
  v2d.frameEvidence();
  if (a.intent?.task === "count") markAnswerCheck($("linked"), a.intent.target, String(a.intent.filters?.storey ?? "") || undefined);
  else markAnswerCheck($("linked"), undefined, undefined);
  const xb = $("xbanner");
  const xcs = crossChecks(a);
  const xc = xcs[0];
  xb.hidden = !xc;
  if (xc) {
    const ok = xcs.every((x) => x.ok);
    xb.className = `xbanner ${ok ? "ok" : "bad"}`;
    xb.innerHTML = xcs.map((x) => `<b>${x.ok ? "✓" : "✗"}</b> ${esc(x.text)}`).join(" &nbsp;·&nbsp; ");
  }
  if (state.ifc && a.evidence.some((e) => e.ifc_guid)) {
    if (state.mode === "2d" && !v2d.hasGuid(a.evidence.find((e) => e.ifc_guid)!.ifc_guid!)) setMode("split");
    await ensure3D();
    applyEvidence3D(a);
  } else if (v3d && v3d.file === state.ifc) {
    applyEvidence3D(a); // clears the previous answer's highlight
  }
}

function applyEvidence3D(a: Answer) {
  const v = v3d;
  if (!v || v.file !== state.ifc) return;
  const guids = a.evidence.filter((e) => e.ifc_guid).map((e) => e.ifc_guid!);
  const storeyIds = new Set(guids.map((g) => v.storeyOfGuid(g)).filter((s): s is number => s !== null));
  const n = v.highlight(guids, true);
  if (storeyIds.size === 1) {
    const s = [...storeyIds][0];
    v.setStorey(s);
    $<HTMLSelectElement>("storey").value = String(s);
  } else if (storeyIds.size > 1) {
    v.setStorey(null); // model-wide evidence: show every storey it touches
    $<HTMLSelectElement>("storey").value = "";
  }
  const pane = $("pane3d");
  pane.dataset.found = String(n);
}

function focusEvidence(i: number) {
  const a = state.answer;
  if (!a) return;
  const ev = a.evidence[i];
  document.querySelectorAll("#card .ev-item").forEach((n) => n.classList.toggle("sel", (n as HTMLElement).dataset.i === String(i)));
  if (ev.bbox && ev.file === state.file?.path) {
    if (state.mode === "3d") setMode("split");
    v2d.focusEvidence(i);
  } else if (ev.ifc_guid && v2d.hasGuid(ev.ifc_guid)) {
    v2d.focusGuid(ev.ifc_guid);
  } else if (ev.bbox && ev.file !== state.file?.path) {
    void openSheet(ev.file, i); // evidence drawn on another sheet of the same project
    return;
  }
  if (ev.ifc_guid && v3d && state.ifc && v3d.file === state.ifc) {
    if (v3d.isStoreyGuid(ev.ifc_guid)) applyEvidence3D(a); // storey = context: show all evidence on it
    else v3d.focusGuid(ev.ifc_guid);
  }
}

// --- demo tour: five steps, each one sentence for the presenter ----------------------------------------
const TOUR: { file: string; q: string; note: string; bench?: boolean }[] = [
  { file: "data/ifc_models/bsc-esplanades_1807-ep-ar-v18_plan-01-1-korrus.pdf",
    q: "What is the net floor area of the room 'KORIDOR (119)' on '1.korrus', in m²?",
    note: "Area from the IFC model, shown on the drawing and in 3D: same room, same GlobalId." },
  { file: "data/ifc_models/bsc-esplanades_1807-ep-ar-v18_plan-01-1-korrus.pdf",
    q: "How many doors are shown on the floor plan of '1.korrus'?",
    note: "Count with one box per door. The drawing and the model agree (cross-check), no model call needed." },
  { file: "data/ifc_models/bsc-esplanades_1807-ep-ar-v18_plan-01-1-korrus.pdf",
    q: "How many doors are there in the model 'Maleva tänav 18 korterelamu (Esplanades example model)'?",
    note: "Model-wide question: evidence on five sheets. Click a sheet chip to open it." },
  { file: "data/swiss_dwellings/site1000_bldg2082_floor9385.pdf",
    q: "How many doors (interior doors and entrance doors together) are drawn on this floor plan?",
    note: "Vector drawing: doors counted on the CAD layer and mapped back onto the PDF." },
  { file: "data/swiss_dwellings/site1000_bldg2082_floor9385.pdf",
    q: "Wie viele Türen und Fenster sind insgesamt auf diesem Grundriss eingezeichnet?",
    note: "A German question that combines two counts: it is split into two sub-questions, each answered and cross-checked, and the sum is done in code." },
  { file: "data/habs/ak0003_sheet_00019.jpg",
    q: "What kind of drawing is this (floor plan, elevation, section, site plan)?",
    note: "Historical scan with no text layer: the cascade escalates to a local vision model and says how sure it is." },
  { file: "", q: "", bench: true,
    note: "Measured on held-out drawings: accuracy per source against two baselines, generality, and cost per 1,000 questions." },
];
let tourStep = -1;
let tourBack = false;
// presenter keys: → next step, ← previous step (not while typing a question)
document.addEventListener("keydown", (e) => {
  const t = e.target as HTMLElement;
  if (/^(TEXTAREA|INPUT|SELECT)$/.test(t.tagName) || e.altKey || e.ctrlKey || e.metaKey) return;
  if (e.key === "ArrowRight" || (e.key === "ArrowLeft" && tourStep > 0)) {
    e.preventDefault();
    tourBack = e.key === "ArrowLeft";
    $("tourBtn").click();
  }
});
$("tourBtn").addEventListener("click", async () => {
  tourStep = tourBack ? Math.max(0, tourStep - 1) : (tourStep + 1) % TOUR.length;
  tourBack = false;
  const t = TOUR[tourStep];
  $("tourBtn").textContent = `Demo ${tourStep + 1}/${TOUR.length} ▸`;
  const note = $("tourNote");
  note.hidden = false;
  note.innerHTML = `<b>${tourStep + 1}/${TOUR.length}</b> ${esc(t.note)}`;
  $("bench").hidden = true;
  if (t.bench) return $("benchBtn").click();
  if (state.file?.path !== t.file) {
    const src = t.file.split("/")[1];
    const f = state.files.find((x) => x.path === t.file) ?? (await listFiles("", t.file, 5)).find((x) => x.path === t.file)
      ?? (await listFiles(src, t.file, 5, false)).find((x) => x.path === t.file);
    if (!f) return;
    await openFile(f, t.q);
  } else $<HTMLTextAreaElement>("question").value = t.q;
  await runAsk();
});

// --- boot ---------------------------------------------------------------------------------------------------
(async () => {
  await refreshFiles();
  const params = new URLSearchParams(location.search);
  const want = params.get("file");
  let f = want ? state.files.find((x) => x.path === want) : state.files[0];
  if (want && !f) f = (await listFiles("", want, 5)).find((x) => x.path === want)
    ?? (await listFiles(want.split("/")[1], want, 5, false)).find((x) => x.path === want); // files without questions
  if (f) {
    await openFile(f, params.get("q") ?? "");
    if (params.get("q")) await runAsk();
  }
  (window as unknown as { __ready: boolean }).__ready = true;
})();

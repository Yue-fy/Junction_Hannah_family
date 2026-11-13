import "./style.css";
import { ask, exampleQuestions, fileUrl, knowledgeGraph, listFiles, onBackend } from "./api";
import { renderCard } from "./card";
import type { Answer, FileInfo } from "./types";
import { Viewer2D } from "./viewer2d";
import { Viewer3D } from "./viewer3d";

const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;

type Mode = "2d" | "3d" | "split";
const state: { file: FileInfo | null; answer: Answer | null; mode: Mode; files: FileInfo[]; ifc: string | null } = {
  file: null, answer: null, mode: "2d", files: [], ifc: null,
};

const v2d = new Viewer2D($("v2d"));
let v3d: Viewer3D | null = null;
const viewer3d = () => (v3d ??= makeViewer3D());

function makeViewer3D() {
  const v = new Viewer3D($("v3d"));
  v.onPick = (guid, label, props) => {
    const pick = $("pick");
    pick.hidden = false;
    pick.innerHTML = `<b>${esc(label)}</b>` + Object.entries(props).filter(([, val]) => val)
      .map(([k, val]) => `<div><span>${esc(k)}</span>${esc(val)}</div>`).join("");
    if (v2d.hasGuid(guid)) {
      v2d.highlightGuids([guid], "picked");
      if (state.mode === "split") v2d.focusGuid(guid);
    }
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
  }
};
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
  const v = viewer3d();
  if (v.file === ifc) return loading3D ?? undefined;
  const label = $("load3d");
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
  if (m) {
    const key = m[1].replace(/[^a-z0-9]/gi, "").toLowerCase();
    const s = v.storeys.find((x) => x.name.replace(/[^a-z0-9]/gi, "").toLowerCase() === key);
    if (s) {
      sel.value = String(s.id);
      v.setStorey(s.id);
    }
  }
}
$<HTMLSelectElement>("storey").addEventListener("change", (e) => {
  const val = (e.target as HTMLSelectElement).value;
  v3d?.setStorey(val ? Number(val) : null);
});

$("fitBtn").addEventListener("click", () => {
  v2d.frameEvidence();
  if (v3d && state.answer) applyEvidence3D(state.answer);
});

// --- files --------------------------------------------------------------------------------------------------
async function refreshFiles() {
  const source = $<HTMLSelectElement>("source").value;
  const q = $<HTMLInputElement>("search").value;
  state.files = await listFiles(source, q, 80);
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

async function openFile(f: FileInfo, question = "") {
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
  $("card").className = "card empty";
  $("card").innerHTML = `<p class="hint">Ask a question about this ${f.ext === ".ifc" ? "model" : "drawing"}.</p>`;
  $("pick").hidden = true;
  $<HTMLTextAreaElement>("question").value = question;

  const is3DOnly = f.ext === ".ifc";
  state.ifc = is3DOnly ? f.path : f.siblings?.[".ifc"] ?? null;
  $("pane2d").hidden = is3DOnly;
  document.querySelectorAll<HTMLButtonElement>("#modes button").forEach((b) => {
    b.disabled = (b.dataset.mode !== "2d" && !state.ifc) || (b.dataset.mode !== "3d" && is3DOnly);
  });
  $<HTMLSelectElement>("storey").hidden = true;
  setMode(is3DOnly ? "3d" : state.ifc ? "split" : "2d");

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
}

function creditLine(f: FileInfo) {
  const title = f.title ? `<b>${esc(f.title)}</b> · ` : "";
  const src = f.source_url ? ` · <a href="${esc(f.source_url)}" target="_blank" rel="noopener">source</a>` : "";
  return `${title}${esc(f.credit)} · licence <b>${esc(f.license)}</b>${src}`;
}

async function loadExamples(f: FileInfo) {
  const sel = $<HTMLSelectElement>("examples");
  sel.innerHTML = `<option value="">Example questions…</option>`;
  try {
    const qs = await exampleQuestions(f.path);
    if (state.file?.path !== f.path) return;
    sel.innerHTML = `<option value="">Example questions (${qs.length})…</option>` + qs.map((q) =>
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
    if (state.file?.path !== f.path || !kg.nodes.length) return;
    el.innerHTML = `<span class="lk-title">Linked sources${kg.mock ? "" : ""}</span>` + kg.nodes.map((n, i) =>
      `<button class="lk ${esc(n.kind)}" data-i="${i}" title="${esc(n.path)}"><span class="kind">${esc(n.kind)}</span>${esc(shortName(n.label, f.path))}<small>${esc(n.relation)}</small></button>`).join("");
    el.querySelectorAll<HTMLButtonElement>("button.lk").forEach((b) => b.addEventListener("click", () => {
      const n = kg.nodes[Number(b.dataset.i)];
      if (n.kind === "ifc" && state.ifc === n.path) return setMode("3d");
      const ext = "." + n.kind;
      if (![".pdf", ".png", ".jpg", ".ifc"].includes(ext)) return window.open(fileUrl(n.path), "_blank");
      void openFile({ path: n.path, source: n.path.split("/")[1], ext, siblings: siblingsGuess(n.path, kg.nodes.map((x) => x.path)),
        n_questions: 0, license: f.license, credit: f.credit, title: "", source_url: f.source_url });
    }));
  } catch {
    /* no kg */
  }
}

function shortName(label: string, current: string) {
  const stem = current.split("/").pop()!.replace(/\.[^.]+$/, "").replace(/_(plan|section|elevation)-.*$/, "");
  return label.startsWith(stem + "_") ? "…" + label.slice(stem.length) : label;
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
    state.answer = a;
    renderCard(card, a, { roundTripMs: performance.now() - t0, onEvidence: focusEvidence, describeGuid: (g) => v3d?.describe(g) ?? g });
    v2d.setEvidence(a.evidence);
    v2d.frameEvidence();
    if (state.ifc && a.evidence.some((e) => e.ifc_guid)) {
      if (state.mode === "2d" && !v2d.hasGuid(a.evidence.find((e) => e.ifc_guid)!.ifc_guid!)) setMode("split");
      await ensure3D();
      applyEvidence3D(a);
    }
  } catch (e) {
    card.className = "card error";
    card.innerHTML = `<p><b>Request failed.</b> ${esc(e)}</p>`;
  } finally {
    $<HTMLButtonElement>("askBtn").disabled = false;
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
    window.open(fileUrl(ev.file), "_blank");
  }
  if (ev.ifc_guid && v3d && state.ifc && v3d.file === state.ifc) {
    if (v3d.isStoreyGuid(ev.ifc_guid)) applyEvidence3D(a); // storey = context: show all evidence on it
    else v3d.focusGuid(ev.ifc_guid);
  }
}

// --- boot ---------------------------------------------------------------------------------------------------
(async () => {
  await refreshFiles();
  const params = new URLSearchParams(location.search);
  const want = params.get("file");
  let f = want ? state.files.find((x) => x.path === want) : state.files[0];
  if (want && !f) f = (await listFiles("", want, 5)).find((x) => x.path === want);
  if (f) {
    await openFile(f, params.get("q") ?? "");
    if (params.get("q")) await runAsk();
  }
  (window as unknown as { __ready: boolean }).__ready = true;
})();

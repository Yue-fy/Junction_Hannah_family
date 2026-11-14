import "./style.css";
import { ask, benchmark, exampleQuestions, fileUrl, knowledgeGraph, listFiles, onBackend, roomGraph, secondOpinion, upload, uploadSet } from "./api";
import { renderBench } from "./bench";
import { agentAsks, crossChecks, renderCard, roomKindsIn } from "./card";
import { markAnswerCheck, renderKg } from "./kg";
import type { Answer, FileInfo, KgRoom, RoomGraph } from "./types";
import { roomKind, roomName, roomShown, Viewer2D } from "./viewer2d";
import type { Viewer3D } from "./viewer3d"; // loaded lazily: web-ifc + three are ~4 MB
import tourSteps from "../fixtures/tour.json";
import tourCustomer from "../fixtures/tour-customer.json";
import { diffQuestion, diffsHtml, heroHtml, heroLoadingHtml, initialView, landingHtml, numbered, projectDifferences, projectOf, PROJECTS, saveView, type Difference, type View } from "./customer";
import type { Project } from "./projects";

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

// --- room graph on CubiCasa plans (R1, experiments/r1/room_graph): rooms + the doors that link them, drawn on the plan.
// Read from the cached pretrained-CubiCasa5K segmentation by the middleware (GET /api/rooms), no language model.
let roomsOn = false;
async function showRooms(on: boolean) {
  roomsOn = on;
  $("roomsBtn").classList.toggle("on", on);
  const leg = $("rgLegend");
  const f = state.file;
  if (!on || !f || f.source !== "cubicasa5k") {
    v2d.setRoomGraph(null);
    leg.hidden = true;
    return;
  }
  leg.hidden = false;
  leg.textContent = "Reading the rooms…";
  try {
    const g = await roomGraph(f.path);
    if (state.file?.path !== f.path || !roomsOn) return;
    v2d.setRoomGraph(g);
    leg.innerHTML = roomLegend(g);
    // open with the best-connected room's links lit (the hall, usually), so the graph reads without hovering
    const hub = leg.querySelector<HTMLElement>("[data-room]");
    if (hub) {
      v2d.focusRoom(hub.dataset.room!);
      hub.addEventListener("mouseenter", () => v2d.focusRoom(hub.dataset.room!));
    }
  } catch (e) {
    v2d.setRoomGraph(null);
    leg.textContent = `No room graph for this plan (${e}).`;
  }
}
function roomLegend(g: RoomGraph) {
  const byId = new Map(g.rooms.map((r) => [r.id, r]));
  const name = (id: string) => { const r = byId.get(id); return r ? roomName(r) : id; };
  const inside = g.rooms.filter((r) => r.cls !== "outdoor" && roomShown(r));
  const hub = [...inside].sort((a, b) => (b.door_to ?? []).filter((x) => x !== "outside").length - (a.door_to ?? []).filter((x) => x !== "outside").length)[0];
  const nHub = (hub?.door_to ?? []).filter((x) => x !== "outside").length;
  const entrances = g.doors.filter((d) => d.between.includes("outside")).length;
  const scale = g.scale?.assumptions?.[0];
  return `<b>Room graph</b> · ${inside.length} rooms · ${g.doors.length} doors${entrances ? ` (${entrances} to the outside)` : ""}`
    + `${hub && nHub >= 2 ? ` · <b class="rg-hub" data-room="${esc(hub.id)}">${esc(name(hub.id))}</b> leads to ${nHub} rooms` : ""} · hover a room for its links`
    + `<small>Rooms, doors and windows from the pretrained CubiCasa5K model (Kalervo et al. 2019, CC BY-NC 4.0) + geometry rules; no language model.`
    + `${scale ? ` ~m²: ${esc(scale)}` : ""}</small>`;
}
$("roomsBtn").addEventListener("click", () => void showRooms(!roomsOn));

/** "Show where · room graph": box the rooms a question names (by printed code when it gives one, e.g. '(OH)', else by
 *  kind) from R1's room graph, with a check line against the answer when the answer names a room or a number. */
async function locateRooms(a: Answer, path: string, question: string) {
  const t0 = performance.now();
  let g: RoomGraph;
  try {
    g = await roomGraph(path);
  } catch (e) {
    await showAnswer({ ...a, trace: [...(a.trace ?? []), `room graph: not available for this plan (${e})`] }, 0);
    return;
  }
  if (state.file?.path !== path) return;
  const kinds = new Set(roomKindsIn(question));
  const codes = [...question.matchAll(/\(([A-ZÄÖ.]{1,6})\)|'([A-ZÄÖ.]{1,6})'/g)].map((m) => (m[1] ?? m[2]).replace(/\./g, ""));
  const byCode = g.rooms.filter((r) => r.label && codes.includes(r.label.replace(/\./g, "")));
  const picked = (byCode.length ? byCode : g.rooms.filter((r) => kinds.has(r.cls) && roomShown(r)));
  const kindWord = [...kinds].map((k) => roomKind({ cls: k } as RoomGraph["rooms"][number])).join(" / ");
  const said = String(a.value ?? "").trim();
  const names = picked.flatMap((r) => [r.label ?? "", roomKind(r)]).filter(Boolean).map((x) => x.toLowerCase());
  // rooms a marked room's doors (or open sides) lead to: "which room is the sauna entered from?" → the sauna's door
  const linked = picked.flatMap((r) => [...(r.door_to ?? []), ...(r.open_to ?? [])]).map((id) => g.rooms.find((x) => x.id === id))
    .filter((r): r is RoomGraph["rooms"][number] => !!r);
  const said_ = said.toLowerCase();
  const via = linked.find((r) => (r.label ?? "").toLowerCase() === said_ || roomKind(r) === said_);
  const verdict = /^\d+(\.\d+)?$/.test(said) && a.intent?.task === "count" ? (Number(said) === picked.length ? " ✓" : ` ✗ (answer ${said})`)
    : names.includes(said_) ? ` ✓ (the answer names '${said}')`
    : via ? ` ✓ (its door leads to ${roomName(via)}, the answer)` : "";
  // only a verdict is a cross-check (✓/✗ line); plain marking stays in the evidence notes and the trace
  const check = picked.length
    ? `${verdict ? "cross-check: " : ""}room graph (CubiCasa5K segmentation) marks ${picked.length} ${picked.length === 1 ? "room" : "rooms"}: ${picked.map((r) => roomName(r)).join(", ")}${verdict}`
    : `room graph: no ${kindWord || "such"} room found on this plan`;
  const ev = picked.map((r, i) => ({
    file: path, page: 0, bbox: r.bbox, bbox_space: "image_px" as const,
    note: `room graph: ${roomName(r)}${r.m2 ? ` (~${r.m2} m²${r.m2_80 ? `, 80%: ${r.m2_80[0]}–${r.m2_80[1]}` : ""})` : ""}`
      + `${(r.door_to ?? []).length ? `, doors to ${r.door_to!.map((id) => { const o = g.rooms.find((x) => x.id === id); return o ? roomName(o) : id; }).join(", ")}` : ""}`
      + `${i === 0 ? `; ${check}` : ""}`,
  }));
  // the room the answer names through a door link is boxed too: both ends of the link are on screen
  if (via && !picked.includes(via)) ev.push({ file: path, page: 0, bbox: via.bbox, bbox_space: "image_px" as const,
    note: `room graph: ${roomName(via)} (the answer), linked by a door to ${picked.map((r) => roomName(r)).join(", ")}` });
  const a2: Answer = {
    ...a,
    evidence: ev.length ? ev : [{ file: path, note: check }],
    trace: [...(a.trace ?? []), `${check} — room graph, ${Math.round(performance.now() - t0)} ms (cached per drawing)`],
    missing: ev.length ? (a.missing ?? []).filter((m) => !/no located evidence/i.test(m)) : a.missing,
    assumptions: [...(a.assumptions ?? []), ...(ev.length ? [`marked from the room graph: ${byCode.length ? `rooms printed ${codes.join("/")}` : `every ${kindWord} region`} (pretrained CubiCasa5K segmentation; areas assume ${g.scale?.assumptions?.[0] ?? "no scale"})`] : [])],
  };
  await showAnswer(a2, 0);
  if (ev.length && !$("credit").textContent?.includes("weights")) $("credit").insertAdjacentHTML("beforeend", " · boxes: CubiCasa5K model (Kalervo et al. 2019), weights CC BY-NC 4.0");
}

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
// The text-grounded ones (title, scale, date) are answered from the scan's printed text (W3's text layer) with the
// cited line boxed on the sheet.
const GENERIC_QUESTIONS = [
  "What kind of drawing is this (floor plan, elevation, section, site plan)?",
  "What is the title of this sheet?",
  "What is the scale of this drawing?",
  "When was this drawing made?",
  "How many storeys does this building have?",
  "How many windows are shown on this drawing?",
];
// Your own file (upload): no dataset questions, no template; general questions by kind.
const UPLOAD_QUESTIONS = [
  "How many doors are shown on this floor plan?",
  "How many rooms are there?",
  "What is the total floor area in m²?",
  "What kind of drawing is this (floor plan, elevation, section, site plan)?",
  "What is the scale of this drawing?",
  "How many windows are shown on this floor plan?",
];
const APARTMENT_QUESTIONS = [
  "How many doors are shown on this floor plan?",
  "How many bedrooms are there?",
  "How many windows are shown on this floor plan?",
  "How many bathrooms are there?",
  "Is there a sauna?",
  "What is the total floor area in m²?",
];
// An uploaded sheet linked to the IFC model uploaded with it: the IFC rules answer about the sheet's own storey (W1 reads
// it from the sheet's title when the file name says nothing). W5 cycle 8: all six right on a renamed esplanades sheet
// (A102.pdf + house.ifc: 42 doors, 60 rooms, 156 walls, 3 rooms > 40 m², KORIDOR (202) 78.40 m², 60 windows).
const SHEET_MODEL_QUESTIONS = [
  "How many doors are on this floor plan?",
  "Which rooms on this floor plan are larger than 40 m²?",
  "How many rooms are on this floor plan?",
  "Which room on this floor plan is the largest?",
  "How many walls are shown on this floor plan?",
  "How many windows are on this floor plan?",
];
const IFC_QUESTIONS = [
  "How many doors are in this model?",
  "How many storeys does this building have?",
  "What is the total floor area of all rooms?",
  "Which storey has the most doors?",
  "How tall is the building?",
  "How many windows are in this model?",
];
// Harder question kinds (Stoa: the hidden set is harder than the dataset's templates), offered in the example menu.
// Only kinds checked end to end through the API (W5 cycle 7: 4 ifc_models projects, 3 Swiss floors, every answer
// right against the knowledge graph / the dataset's own counts): a set answer, plan-vs-model links, a given price,
// sums and differences of counts. {S} = the plan's storey from the knowledge graph.
const HARDER_IFC_PLAN = [
  "Which rooms on '{S}' are larger than 20 m²?",
  "Do the floor plan and the IFC model agree on the number of windows on '{S}'?",
  "How many windows on '{S}' are in the model but not drawn on this plan?",
  "If each door costs 450 euros, what do all the doors on '{S}' cost in total?",
  "How many doors and windows are there on '{S}' together?",
];
const HARDER_SWISS = [
  "How many more doors than windows are drawn on this floor plan?",
  "Wie viele Türen und Fenster sind insgesamt auf diesem Grundriss eingezeichnet?",
  "What is the total area of all rooms on this floor plan, in m²?",
];
async function harderQuestions(f: FileInfo): Promise<string[]> {
  if (f.source === "swiss_dwellings" && f.ext === ".pdf") return HARDER_SWISS;
  if (f.source !== "ifc_models" || f.ext !== ".pdf") return [];
  const s = (await knowledgeGraph(f.path).catch(() => null))?.storey?.name;
  return s ? HARDER_IFC_PLAN.map((q) => q.replace("{S}", s)) : [];
}
const uploads: FileInfo[] = [];

async function refreshFiles() {
  const source = $<HTMLSelectElement>("source").value;
  const q = $<HTMLInputElement>("search").value;
  const list = await listFiles(source, q, 80, !HISTORICAL.includes(source));
  if (!source && !q) {
    demoFiles ??= (await Promise.all(DEMO.map((p) => listFiles("", p, 3).then((r) => r.find((x) => x.path === p)).catch(() => undefined))))
      .filter((x): x is FileInfo => !!x);
    state.files = [...uploads, ...demoFiles, ...list.filter((f) => !DEMO.includes(f.path))];
  } else state.files = list;
  const ul = $("files");
  ul.innerHTML = state.files.map((f, i) => {
    const name = f.path.split("/").pop()!;
    const sib = Object.keys(f.siblings ?? {}).map((e) => `<span class="ext">${esc(e.slice(1))}</span>`).join("");
    const upl = f.source === "upload";
    return `<li data-i="${i}" class="${state.file?.path === f.path ? "on" : ""}"><span class="src ${esc(f.source)}">${upl ? "yours" : esc(f.source.replace(/_.*/, ""))}</span>
      <span class="name" title="${esc(upl ? `${name} (uploaded, kept on this machine)` : f.path)}">${esc(name)}</span><span class="meta">${upl ? "new" : `${f.n_questions} q`} ${upl && Object.keys(f.siblings ?? {}).length < 2 ? "" : sib}</span></li>`;
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

// --- your own drawing: upload (button or drop anywhere) → saved on this machine → asked like any other file ---
// Several files at once with an .ifc among them (a plan sheet + its model) are linked as one building (one folder).
const STYLE_NAMES: Record<string, string> = { cubicasa5k: "Nordic apartment plan", swiss_dwellings: "Swiss dwelling plan",
  ifc_models: "sheet drawn from a BIM model", scan: "historical scan" };
async function uploadFiles(files: File[]) {
  if (!files.length) return;
  const box = $("uploadBox");
  const msg = $("uploadMsg");
  box.classList.add("busy");
  box.classList.remove("err");
  const names = files.map((f) => f.name).join(" + ");
  msg.textContent = `uploading ${names} (${(files.reduce((n, f) => n + f.size, 0) / 1e6).toFixed(1)} MB)…`;
  try {
    const linked = files.length > 1 && files.some((f) => /\.ifc$/i.test(f.name));
    const style = $<HTMLSelectElement>("uploadStyle").value;
    let got: FileInfo[] = [];
    for (const file of files) got.push(await upload(file, /\.(png|jpe?g)$/i.test(file.name) ? (linked ? "none" : style) : ""));
    if (linked) got = await uploadSet(got.map((f) => f.path));
    for (const f of [...got].reverse()) if (!uploads.some((u) => u.path === f.path)) uploads.unshift(f);
    const first = got.find((f) => f.ext !== ".ifc" && f.siblings?.[".ifc"]) ?? got[0];
    const g = first.style_guess;
    msg.textContent = linked ? `${names} · linked as one building: ask below`
      : files.length > 1 ? `${files.length} files uploaded · ask below`
      : `${files[0].name}${g && first.style === g.style ? ` · looks like a ${STYLE_NAMES[g.style] ?? g.style}` : ""} · ask it anything below`;
    $<HTMLSelectElement>("source").value = "";
    $<HTMLInputElement>("search").value = "";
    await refreshFiles();
    $("landing").hidden = true; // an upload from the project page opens it right away
    await openFile(first);
    $("question").focus();
  } catch (e) {
    box.classList.add("err");
    msg.textContent = `could not upload: ${e}`;
  } finally {
    box.classList.remove("busy");
  }
}
$<HTMLInputElement>("uploadInput").addEventListener("change", (e) => {
  const input = e.target as HTMLInputElement;
  const files = [...(input.files ?? [])];
  input.value = "";
  void uploadFiles(files);
});
/** "your upload · Nordic apartment plan (guessed from the image, p 0.93) · linked to house.ifc · not in the dataset" */
function uploadMeta(f: FileInfo) {
  const g = f.style_guess;
  const style = f.style ? ` · ${STYLE_NAMES[f.style] ?? f.style}${g && g.style === f.style ? ` (guessed from the image, p ${g.p.toFixed(2)})` : ""}`
    : ""; // other guesses change nothing (W5 c8: 3 of 12 random CubiCasa plans came out 'scan' at p 0.92-0.98), so say nothing
  const model = f.ext !== ".ifc" ? f.siblings?.[".ifc"] : undefined;
  const others = (f.set ?? []).filter((p) => p !== f.path).map((p) => p.split("/").pop()!);
  const set = model ? ` · linked to ${model.split("/").pop()}` : others.length ? ` · uploaded with ${others.join(", ")}` : "";
  return `your upload${style}${set} · not in the dataset`;
}
/** Customer view: an upload, in plain words, before the first question. */
function uploadIntro(f: FileInfo) {
  const model = f.ext !== ".ifc" ? f.siblings?.[".ifc"]?.split("/").pop() : undefined;
  if (model) return `<b>Your drawing is linked to its 3D model (${esc(model)}).</b> Answers come from the model, for the floor this sheet shows, and the counted elements light up in 3D.`;
  if (f.ext === ".ifc") return `<b>Your 3D model is ready.</b> Ask about doors, rooms, floors or sizes: the answers are counted in the model and lit up in 3D.`;
  const style = f.style ? " It looks like a Nordic apartment plan, so the readers trained on such plans help." : "";
  return `<b>Your drawing is new to us:</b> no template and no 3D model behind it, so answers are a best estimate and say so.${style}`
    + (f.ext === ".pdf" ? ` <span class="tip">Tip: upload the sheet and its .ifc model together for exact answers from the model.</span>` : "");
}
/** What happens to an upload, said before the first question. */
function uploadHint(f: FileInfo) {
  const model = f.ext !== ".ifc" ? f.siblings?.[".ifc"]?.split("/").pop() : undefined;
  if (model)
    return `<p class="hint">This sheet is new to the system and came with its model <b>${esc(model)}</b> (the only IFC uploaded with it),
      so the IFC rules answer from the model, for the storey the sheet shows (read from its title when the file name says nothing),
      and the counted elements light up in 3D. No template, no cached answer.</p>`;
  const way = f.ext === ".ifc" ? "the IFC rules, then the reasoning agent"
    : f.ext === ".pdf" ? "the PDF's own lines and text, then the local vision model"
    : f.style ? "as a Nordic apartment plan: the counter fine-tuned on CubiCasa5K plans, with the pretrained symbol detector to mark what it counts"
    : "printed text and scale read from the image, then the local vision model";
  const tip = f.ext === ".pdf" ? `<p class="hint">Is it a sheet of a BIM model? Upload the sheet <b>and</b> its .ifc together (select both, or drop
      both at once): the answers then come from the model and show in 3D.</p>` : "";
  return `<p class="hint">This file is new to the system: no template, no CAD or IFC twin, nothing cached. It goes the general way (${way}),
      so expect lower confidence, said honestly, and a first answer that takes longer.</p>${tip}`;
}
let dragDepth = 0;
const hasFiles = (e: DragEvent) => [...(e.dataTransfer?.types ?? [])].includes("Files");
document.addEventListener("dragenter", (e) => {
  if (!hasFiles(e)) return;
  dragDepth++;
  $("dropHint").hidden = false;
});
document.addEventListener("dragleave", (e) => {
  if (!hasFiles(e)) return;
  dragDepth = Math.max(0, dragDepth - 1);
  if (!dragDepth) $("dropHint").hidden = true;
});
document.addEventListener("dragover", (e) => {
  if (hasFiles(e)) e.preventDefault();
});
document.addEventListener("drop", (e) => {
  if (!hasFiles(e)) return;
  e.preventDefault();
  dragDepth = 0;
  $("dropHint").hidden = true;
  void uploadFiles([...(e.dataTransfer?.files ?? [])]);
});

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
  $("fileMeta").textContent = f.source === "upload" ? uploadMeta(f) : `${f.source} · ${f.n_questions} questions`;
  $("credit").innerHTML = creditLine(f);
  projectChrome(f);
  if (!keep) {
    $("hero").hidden = !(isCustomer() && f.source === "upload");
    $("hero").innerHTML = isCustomer() && f.source === "upload" ? `<div class="hero-intro">${uploadIntro(f)}</div>` : "";
    document.body.classList.remove("answered");
    markAnswerCheck($("linked"), undefined, undefined);
    $("xbanner").hidden = true;
    $("elsewhere").hidden = true;
    $("card").className = "card empty";
    // the first thing a visitor reads: what every answer carries
    $("card").innerHTML = `<p class="hint">Ask about this ${f.ext === ".ifc" ? "model" : "drawing"} in any language, or pick an example. Every answer
      shows how sure we are, what it cost and how it was worked out, and points at where it came from (${f.ext === ".ifc" ? "elements in the 3D model" : "boxes on the drawing"}),
      checked against a second source when there is one.</p>${f.source === "upload" ? uploadHint(f) : ""}`;
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
  if (!keep) setMode(is3DOnly ? "3d" : state.ifc && !isCustomer() ? "split" : "2d");
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
  $("roomsBtn").hidden = f.source !== "cubicasa5k";
  if (state.file?.path === f.path) void showRooms(roomsOn);
  if (keep && state.file?.path === f.path) {
    showAnswer(keep, 0);
    if (focusIndex !== null) focusEvidence(focusIndex);
  }
}

/** The answer boxes elements only on OTHER sheets (a storey list asked on 1.korrus, a room on another floor): say so
 * on the drawing and offer those sheets, instead of an unmarked plan. */
function showElsewhere(a: Answer) {
  const el = $("elsewhere");
  const here = state.file?.path ?? "";
  const counts = new Map<string, number>();
  for (const e of a.evidence) if (e.bbox) counts.set(e.file, (counts.get(e.file) ?? 0) + 1);
  el.hidden = !counts.size || counts.has(here);
  if (el.hidden) return;
  const short = (p: string) => p.split("/").pop()!.replace(/^.*?_(plan|section|elevation)-\d*-?/, "$1 ").replace(/\.[^.]+$/, "");
  el.innerHTML = `<span>Not on this sheet. Drawn on:</span>`
    + [...counts.entries()].sort((x, y) => x[0].localeCompare(y[0])).slice(0, 8)
      .map(([f, n]) => `<button type="button" data-file="${esc(f)}" title="Open ${esc(f.split("/").pop()!)}">${esc(short(f))} <b>${n}</b></button>`).join("");
  el.querySelectorAll<HTMLButtonElement>("button").forEach((b) => b.addEventListener("click", () => void openSheet(b.dataset.file!)));
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
  if (f.source === "upload") return `<b>${esc(f.path.split("/").pop()!)}</b> · ${esc(f.credit)}`;
  const title = f.title ? `<b>${esc(f.title)}</b> · ` : "";
  const src = f.source_url ? ` · <a href="${esc(f.source_url)}" target="_blank" rel="noopener">source</a>` : "";
  return `${title}${esc(f.credit)} · licence <b>${esc(f.license)}</b>${src}`;
}

async function loadExamples(f: FileInfo) {
  const sel = $<HTMLSelectElement>("examples");
  sel.innerHTML = `<option value="">Example questions…</option>`;
  $("chips").innerHTML = "";
  try {
    const [qs, harder] = await Promise.all([exampleQuestions(f.path), harderQuestions(f).catch(() => [] as string[])]);
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
    const proj = isCustomer() ? projectOf(f.path) : undefined;
    const pchips = proj ? (f.ext === ".ifc" && proj.modelChips ? proj.modelChips : proj.chips) : [];
    if (proj) {
      chips.innerHTML = pchips.map((q) => `<button type="button" class="chip" title="${esc(q)}">${esc(q)}</button>`).join("");
      chips.querySelectorAll<HTMLButtonElement>(".chip").forEach((b, i) => b.addEventListener("click", () => {
        $<HTMLTextAreaElement>("question").value = pchips[i];
        void runAsk();
      }));
    }
    const general = f.source === "upload" ? (f.ext === ".ifc" ? IFC_QUESTIONS : f.siblings?.[".ifc"] ? SHEET_MODEL_QUESTIONS
      : f.style ? APARTMENT_QUESTIONS : UPLOAD_QUESTIONS) : GENERIC_QUESTIONS;
    const pick = qs.length ? [...english.filter((q) => q.has_fixture), ...interleaved.filter((q) => !q.has_fixture)].slice(0, 4)
      : general.map((question) => ({ question, type: "", unit: null }));
    if (isCustomer() && !proj) pick.splice(4); // 3–4 suggestions, not a menu
    if (!proj) chips.innerHTML = pick.map((q) => `<button type="button" class="chip" title="${esc(q.question)}">${esc(q.question.length > 64 ? q.question.slice(0, 61) + "…" : q.question)}</button>`).join("");
    if (!proj) chips.querySelectorAll<HTMLButtonElement>(".chip").forEach((b, i) => b.addEventListener("click", () => {
      $<HTMLTextAreaElement>("question").value = pick[i].question;
      void runAsk();
    }));
    // files without dataset questions (historical scans): the general questions, also in the menu (chips show ~2)
    const menu = qs.length ? qs : pick.map((q) => ({ ...q, has_fixture: false }));
    const opt = (q: string, star = false) => `<option value="${esc(q)}">${star ? "★ " : ""}${esc(q.length > 110 ? q.slice(0, 107) + "…" : q)}</option>`;
    const hard = harder.filter((q) => !menu.some((m) => m.question === q));
    sel.innerHTML = `<option value="">${qs.length ? "More example questions" : f.ext === ".ifc" ? "Questions for any model" : f.source === "upload" && f.siblings?.[".ifc"] ? "Questions for a sheet + its model" : "Questions for any drawing"} (${menu.length}${hard.length ? ` + ${hard.length} harder` : ""})…</option>`
      + (hard.length ? `<optgroup label="Harder: lists, plan vs model, prices, sums (no dataset template)">${hard.map((q) => opt(q)).join("")}</optgroup><optgroup label="From the dataset">` : "")
      + menu.map((q) => opt(q.question, q.has_fixture)).join("") + (hard.length ? "</optgroup>" : "");
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
  card.innerHTML = `<div class="spinner"></div><p>Answering… <b class="elapsed"></b> <small>cheapest solver first (rules → local model → hosted model)</small><small class="slow" hidden><br>Still working: no rule answers this directly, so the local vision model is reading the drawing or the reasoning agent is planning steps. The first read of a large scan can take a few minutes; after that it is cached.</small></p>`;
  $<HTMLButtonElement>("askBtn").disabled = true;
  $("hero").hidden = false;
  $("hero").innerHTML = heroLoadingHtml(q);
  fitQuestion();
  const t0 = performance.now();
  // a live question can take long (first text-layer read of a scan, the agent's steps): show it is still going
  const tick = window.setInterval(() => {
    const s = (performance.now() - t0) / 1000;
    const el = card.querySelector<HTMLElement>(".elapsed");
    if (!el) return window.clearInterval(tick);
    el.textContent = s >= 2 ? `${Math.floor(s)} s` : "";
    const he = $("hero").querySelector<HTMLElement>(".elapsed");
    if (he) he.textContent = s >= 2 ? `${Math.floor(s)} s${s >= 15 ? " · the first read of a new drawing takes longer" : ""}` : "";
    const slow = card.querySelector<HTMLElement>(".slow");
    if (slow && s >= 15) slow.hidden = false;
  }, 1000);
  try {
    const a = await ask(f.path, q);
    if (state.file?.path !== f.path) return;
    await showAnswer(a, performance.now() - t0);
  } catch (e) {
    card.className = "card error";
    card.innerHTML = `<p><b>Request failed.</b> ${esc(e)}</p>`;
    $("hero").innerHTML = `<div class="hero-error"><b>Sorry, that did not work.</b> <small>${esc(e)}</small></div>`;
  } finally {
    window.clearInterval(tick);
    $<HTMLButtonElement>("askBtn").disabled = false;
  }
}

async function showAnswer(a: Answer, roundTripMs: number) {
  state.answer = a;
  const askedPath = state.file?.path ?? "";
  const askedQ = $<HTMLTextAreaElement>("question").value.trim();
  renderCard($("card"), a, {
    roundTripMs: roundTripMs || (a.cost?.wall_seconds ?? 0) * 1000, onEvidence: focusEvidence,
    describeGuid: (g) => v3d?.describe(g) ?? g, currentFile: state.file?.path ?? "", currentQuestion: askedQ, onOpenSheet: (p) => void openSheet(p),
    onAsk: (q) => {
      $<HTMLTextAreaElement>("question").value = q;
      void runAsk();
    },
    onLocate: async (loc) => {
      if (loc.solver === "rooms") return locateRooms(a, askedPath, askedQ);
      // a second reader answers the same question; its boxes become the evidence, with a cross-check line
      const t0 = performance.now();
      const r = await ask(askedPath, askedQ, loc.solver, loc.args);
      if (state.file?.path !== askedPath) return;
      const same = r.value !== null && Number(r.value) === Number(a.value);
      const ev = (r.evidence ?? []).filter((e) => e.bbox);
      const what = Number(r.value) === 1 ? loc.noun.replace(/s$/, "") : loc.noun;
      const check = r.value === null ? `${loc.name}: no answer (${(r.missing ?? [])[0] ?? `nothing to mark for this question`})`
        : `cross-check: ${loc.name} (${loc.solver}) finds ${r.value} ${what} ${same ? "✓" : `✗ (answer ${a.value})`}`;
      const a2: Answer = {
        ...a, cached: a.cached,
        evidence: ev.map((e, i) => ({ ...e, note: `${loc.name}: ${e.note ?? ""}${i === 0 ? `; ${check}` : ""}` })),
        trace: [...(a.trace ?? []), `${check} — ${loc.solver}, ${Math.round(performance.now() - t0)} ms (cached per drawing)`,
          ...(r.trace ?? []).filter((l) => /CC BY|Kalervo/.test(l)).slice(0, 1)],
        missing: ev.length ? (a.missing ?? []).filter((m) => !/no located evidence/i.test(m)) : a.missing,
        // the extra reader's tokens/GPU count too (both are cached per drawing, so usually 0)
        cost: Object.fromEntries([...new Set([...Object.keys(a.cost ?? {}), ...Object.keys(r.cost ?? {})])].map((k) =>
          [k, k === "wall_seconds" ? a.cost?.[k] : (a.cost?.[k] ?? 0) + (r.cost?.[k] ?? 0)])),
        assumptions: [...(a.assumptions ?? []), ...(same ? [] : [`the marks show the ${loc.name}'s ${r.value ?? "?"}, not the answer's ${a.value}: compare them on the drawing`])],
      };
      if (!ev.length) a2.evidence = [{ file: askedPath, note: check } as Answer["evidence"][number]];
      await showAnswer(a2, 0);
      // the detector's weights have their own licence: credit them next to the drawing's credit while its boxes show
      const lic = (r.trace ?? []).find((l) => /CC BY/.test(l));
      if (lic && ev.length && !$("credit").textContent?.includes("weights")) $("credit").insertAdjacentHTML("beforeend", ` · boxes: ${esc(lic)}`);
    },
    onSecondOpinion: async () => {
      const t0 = performance.now();
      const answer = await secondOpinion(askedPath, askedQ);
      return { answer, ms: performance.now() - t0 };
    },
  });
  v2d.setEvidence(a.evidence);
  v2d.setNumbers(numbered(a.evidence));
  v2d.frameEvidence();
  showElsewhere(a);
  renderHero(a, roundTripMs);
  // only a storey-scoped count is the same fact as a drawing-vs-model pill (model-wide totals are not)
  const st = a.intent?.filters?.storey ? String(a.intent.filters.storey) : undefined;
  markAnswerCheck($("linked"), a.intent?.task === "count" && st ? a.intent.target : undefined, st);
  const xb = $("xbanner");
  const xcs = crossChecks(a, agentAsks(a));
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
  // A free-text answer about a model with no element evidence ("Toilet-Domestic-3D: 9 units, Urinal-Wall-3D: 4"):
  // find the element types it names in the loaded model (in the browser, no model call), highlight them and check
  // the counts it gives against the model.
  // Also when the solver did cite elements but its text lists counts per type (W1 rules: "Toilet-Domestic-3D: 9" …):
  // the browser's own IFC parser (web-ifc) recounts them, an independent second reading of the same model.
  const cited = a.evidence.some((e) => e.ifc_guid);
  const perType = typeof a.value === "string" ? (a.value.match(/[A-Za-z][^:\n]{2,80}:\s*\d+\b/g) ?? []).length : 0;
  // (never twice: the re-rendered answer carries `checked`, and a cited answer would otherwise qualify again forever)
  if (/\.ifc$/i.test(askedPath) && typeof a.value === "string" && !a.checked && (!cited || perType >= 2)) {
    await ensure3D();
    const v = v3d;
    if (state.answer !== a || !v || v.file !== askedPath) return;
    const named = v.findNamed(String(a.value), askedQ);
    if (!named.length) return;
    const said = named.filter((n) => !n.missed);
    const missed = named.filter((n) => n.missed);
    if (!said.length && !missed.length) return;
    const checks = said.filter((n) => n.said !== null).map((n) => `${n.name} ${n.guids.length}${n.said === n.guids.length ? " ✓" : ` ✗ (answer says ${n.said})`}`);
    // 3+ counted types that all match: one summary check line (the card shows two lines at most)
    const counted = said.filter((n) => n.said !== null);
    const allOk = counted.length >= 3 && counted.every((n) => n.said === n.guids.length);
    const ev = said.flatMap((n) => n.guids.map((g, i) => ({
      file: askedPath, ifc_guid: g,
      note: `named in the answer: ${n.name} (${i + 1} of ${n.guids.length})${i !== 0 || n.said === null ? ""
        : allOk ? (n === counted[0] ? `; cross-check: all ${counted.length} types the answer counts match the model: ${counted.map((c) => `${c.guids.length} '${c.name}'`).join(", ")} ✓` : "")
        : `; cross-check: the model has ${n.guids.length} '${n.name}', the answer says ${n.said} ${n.said === n.guids.length ? "✓" : "✗"}`}`,
    }) as Answer["evidence"][number]));
    // same kind of fixture in the model but not in the answer: shown as a ✗ check, its elements listed after the named ones
    const miss = missed.map((n) => `${n.name} ×${n.guids.length}`).join(", ");
    ev.push(...missed.flatMap((n) => n.guids.map((g, i) => ({
      file: askedPath, ifc_guid: g,
      note: `NOT in the answer: ${n.name} (${i + 1} of ${n.guids.length})${i === 0 && n === missed[0] ? `; cross-check: the model ${said.length ? "also " : ""}has ${miss} of ${said.length ? "the same kind" : "the kind the question asks about"} (purple in 3D), which the answer does not mention ✗` : ""}`,
    }) as Answer["evidence"][number])));
    // the solver cited its elements: keep its evidence; the browser's recount is a check line, not new evidence
    const recount = cited && counted.length ? [`cross-check: counted again in your browser with a second IFC parser (web-ifc): ${counted.length} type${counted.length > 1 ? "s" : ""}, ${counted.every((n) => n.said === n.guids.length) ? `${counted.reduce((t, n) => t + n.guids.length, 0)} elements, every count as the answer says ✓` : `${counted.filter((n) => n.said !== n.guids.length).map((n) => `'${n.name}' ${n.guids.length} vs ${n.said}`).join(", ")} ✗`}`] : [];
    await showAnswer({
      ...a, evidence: cited ? [...a.evidence, ...ev.filter((e) => /^NOT in the answer:/.test(e.note ?? ""))] : [...ev, ...a.evidence],
      checked: [...said.map((n) => ({ name: n.name, model: n.guids.length, said: n.said })),
        ...missed.map((n) => ({ name: n.name, model: n.guids.length, said: null, notInAnswer: true }))],
      trace: [...(a.trace ?? []), ...recount, `checked against the model by element name (in the browser, no model call): ${said.length ? `named in the answer ${said.map((n) => `${n.name} ×${n.guids.length}`).join(", ")}` : "the answer names no element type of the model"}${checks.length ? `; counts: ${checks.join(", ")}` : ""}${miss ? `; same kind, not named: ${miss}` : ""}`],
      missing: [...(a.missing ?? []), ...(miss ? [`the answer does not mention ${miss} (same kind of fixture in the model)`] : [])],
      assumptions: [...(a.assumptions ?? []), cited ? "the browser recounted the types the answer names by family/type name in the loaded model"
        : said.length ? "highlighted elements are matched by the family/type names the answer uses; the solver did not cite them"
        : "purple elements are the model's families of the kind the question asks about (matched by element name), not cited by the solver"],
    }, roundTripMs);
  }
}

function applyEvidence3D(a: Answer) {
  const v = v3d;
  if (!v || v.file !== state.ifc) return;
  const guids = a.evidence.filter((e) => e.ifc_guid).map((e) => e.ifc_guid!);
  const storeyIds = new Set(guids.map((g) => v.storeyOfGuid(g)).filter((s): s is number => s !== null));
  const contrast = new Set(a.evidence.filter((e) => e.ifc_guid && /^NOT in the answer:/.test(e.note ?? "")).map((e) => e.ifc_guid!));
  // whole-building answers (height = its highest element, W1 ifc): the one highlighted element only makes sense in the
  // context of the whole model, so show every storey and frame the model rather than zooming onto that element
  const whole = (a.assumptions ?? []).some((l) => /building height|whole (building|model)/i.test(l))
    || (guids.length > 0 && a.evidence.filter((e) => e.ifc_guid).every((e) => /\b(highest|lowest|topmost|tallest)\b/i.test(e.note ?? "")));
  const n = v.highlight(guids, !whole, contrast);
  if (whole) {
    v.setStorey(null);
    $<HTMLSelectElement>("storey").value = "";
    v.frameAll();
  } else if (storeyIds.size === 1) {
    const s = [...storeyIds][0];
    v.setStorey(s);
    $<HTMLSelectElement>("storey").value = String(s);
  } else if (storeyIds.size > 1) {
    v.setStorey(null); // model-wide evidence: show every storey it touches
    $<HTMLSelectElement>("storey").value = "";
  }
  const pane = $("pane3d");
  pane.dataset.found = String(n);
  // the same numbers as the answer's short list (customer view; CSS hides them in the expert view)
  v.setNumbers(numbered(a.evidence).map((i) => a.evidence[i].ifc_guid ?? ""));
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

// --- demo tour: one step per key press, each one sentence for the presenter ----------------------------------------
// Steps live in fixtures/tour.json (one source for this tour and fixtures/record.py, which pre-records its answers):
// {file, q, note, bench?, second? (ask NVIDIA Nemotron too), locate? (click "Show where")}. Add a step = add a line there.
const TOUR: { file: string; q: string; note: string; bench?: boolean; second?: boolean; locate?: boolean; rooms?: boolean }[] = tourSteps;
// the customer view tells the customer story (question → answer → where → differences → time saved → accuracy)
const TOUR_C: typeof TOUR = tourCustomer;
const tourList = () => (isCustomer() ? TOUR_C : TOUR);
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
  $("landing").hidden = true;
  tourStep = tourBack ? Math.max(0, tourStep - 1) : (tourStep + 1) % tourList().length;
  tourBack = false;
  const t = tourList()[tourStep];
  $("tourBtn").textContent = `Demo ${tourStep + 1}/${tourList().length} ▸`;
  const note = $("tourNote");
  note.hidden = false;
  note.innerHTML = `<b>${tourStep + 1}/${tourList().length}</b> ${esc(t.note)}`;
  $("bench").hidden = true;
  if (t.bench) return $("benchBtn").click();
  if (state.file?.path !== t.file) {
    const src = t.file.split("/")[1];
    const f = state.files.find((x) => x.path === t.file) ?? (await listFiles("", t.file, 5)).find((x) => x.path === t.file)
      ?? (await listFiles(src, t.file, 5, false)).find((x) => x.path === t.file);
    if (!f) return;
    roomsOn = !!t.rooms; // each step sets the room overlay itself; drawn as soon as the plan is loaded
    await openFile(f, t.q);
  } else $<HTMLTextAreaElement>("question").value = t.q;
  if (!!t.rooms !== roomsOn) await showRooms(!!t.rooms);
  if (t.q) await runAsk();
  if (t.second) document.querySelector<HTMLButtonElement>("#card .second-btn")?.click();
  if (t.locate) document.querySelector<HTMLButtonElement>("#card .locate-btn")?.click();
});

// --- customer view (default) / expert view ------------------------------------------------------------------
let view: View = initialView();
const isCustomer = () => view === "customer";
function applyView(v: View) {
  if (v !== view) tourStep = -1; // each view has its own tour
  view = v;
  saveView(v);
  document.body.dataset.view = v;
  $("viewToggle").textContent = v === "customer" ? "Expert view" : "Simple view";
  ($("how") as HTMLDetailsElement).open = v === "expert";
  const names: Record<string, [string, string]> = { "2d": ["Drawing", "Plan"], "3d": ["3D model", "3D"], split: ["Side by side", "Side by side"] };
  document.querySelectorAll<HTMLButtonElement>("#modes button").forEach((b) => (b.textContent = names[b.dataset.mode!][v === "customer" ? 1 : 0]));
  $<HTMLTextAreaElement>("question").placeholder = v === "customer" ? "Ask anything about this project…" : "e.g. How many doors are shown on the floor plan?";
  if (state.file) {
    projectChrome(state.file);
    void loadExamples(state.file);
  }
  if (state.answer) renderHero(state.answer, 0);
  const url = new URL(location.href);
  url.searchParams.set("view", v);
  history.replaceState(null, "", url);
}
$("viewToggle").addEventListener("click", () => {
  applyView(isCustomer() ? "expert" : "customer");
  if (isCustomer() && !state.file) showLanding(true);
  else if (!isCustomer()) showLanding(false);
});

function showLanding(on: boolean) {
  const el = $("landing");
  el.hidden = !on;
  if (!on) return;
  el.innerHTML = landingHtml();
  el.querySelector<HTMLButtonElement>("[data-act=tour]")?.addEventListener("click", () => {
    showLanding(false);
    $("tourBtn").click();
  });
  el.querySelector<HTMLButtonElement>("[data-act=expert]")?.addEventListener("click", () => {
    showLanding(false);
    applyView("expert");
    if (!state.file) void fileInfo(DEMO[0]).then((f) => f && openFile(f));
  });
  el.querySelectorAll<HTMLButtonElement>(".proj-card").forEach((b) => b.addEventListener("click", () => {
    if (b.dataset.project === "upload") return $<HTMLInputElement>("uploadInput").click();
    const p = PROJECTS.find((x) => x.id === b.dataset.project);
    if (p) void openProject(p);
  }));
}
$("projectsBtn").addEventListener("click", () => showLanding(true));
$("askMore").addEventListener("click", () => document.body.classList.remove("answered"));
/** Customer view: the question box grows with its text (a chip or a tour step can be long). */
function fitQuestion() {
  const ta = $<HTMLTextAreaElement>("question");
  ta.style.height = "";
  if (isCustomer() && ta.scrollHeight > ta.clientHeight) ta.style.height = `${ta.scrollHeight + 2}px`;
}
$("question").addEventListener("input", fitQuestion);

async function fileInfo(path: string): Promise<FileInfo | undefined> {
  return state.files.find((x) => x.path === path)
    ?? (await listFiles("", path, 5).catch(() => [])).find((x) => x.path === path)
    ?? (await listFiles(path.split("/")[1], path, 5, false).catch(() => [])).find((x) => x.path === path);
}
async function openProject(p: Project, sheet = 0, question = "") {
  const f = await fileInfo(p.sheets[sheet].path);
  if (!f) return;
  showLanding(false);
  await openFile(f, question);
  if (question) await runAsk();
}

/** Customer view chrome for the open file: project name, its sheets as tabs, the one-line credit, differences. */
let diffsFor = "";
let diffs: Difference[] = [];
function projectChrome(f: FileInfo) {
  const p = projectOf(f.path);
  $("projHead").hidden = !isCustomer();
  $("projName").textContent = p?.name ?? (f.source === "upload" ? "Your drawing" : f.title || f.path.split("/").pop()!);
  const files = (f.set?.length ? f.set : [f.path]).map((x) => x.split("/").pop()).join(" + ");
  $("projPlace").textContent = p ? `${p.place} · ${p.contents}` : f.source === "upload" ? `${files} · kept only on this computer` : "";
  const tabs = $("sheetTabs");
  tabs.hidden = !isCustomer() || !p || p.sheets.length < 2;
  tabs.innerHTML = p ? p.sheets.map((s) => `<button type="button" role="tab" class="${s.path === f.path ? "on" : ""}" data-path="${esc(s.path)}">${esc(s.label)}</button>`).join("") : "";
  tabs.querySelectorAll<HTMLButtonElement>("button").forEach((b) => b.addEventListener("click", () => {
    const i = p!.sheets.findIndex((s) => s.path === b.dataset.path);
    if (i >= 0 && b.dataset.path !== state.file?.path) void openProject(p!, i);
  }));
  $("credit").innerHTML = isCustomer() && p ? esc(p.credit) : creditLine(f);
  // differences: once per project (the knowledge graph of every floor plan, cached by the dev server)
  const el = $("diffs");
  if (!isCustomer() || !p) {
    el.hidden = true;
    return;
  }
  if (diffsFor === p.id) {
    el.hidden = !diffs.length;
    return;
  }
  diffsFor = p.id;
  diffs = [];
  el.hidden = true;
  void projectDifferences(p, (path) => knowledgeGraph(path).catch(() => null)).then((d) => {
    if (diffsFor !== p.id) return;
    diffs = d;
    el.innerHTML = diffsHtml(d, p);
    el.hidden = !d.length || !isCustomer();
    el.querySelectorAll<HTMLButtonElement>(".diff-go").forEach((b) => b.addEventListener("click", () => {
      const x = diffs[Number(b.dataset.diff)];
      const i = p.sheets.findIndex((s) => s.path === x.sheet);
      if (i >= 0) void openProject(p, i, diffQuestion(x));
    }));
  });
}

function renderHero(a: Answer, roundTripMs: number) {
  const el = $("hero");
  el.hidden = false;
  document.body.classList.add("answered");
  const p = state.file ? projectOf(state.file.path) : undefined;
  el.innerHTML = heroHtml(a, {
    question: $<HTMLTextAreaElement>("question").value.trim(), file: state.file?.path ?? "", roundTripMs,
    sheetLabel: (path) => p?.sheets.find((s) => s.path === path)?.label ?? "",
  });
  el.querySelectorAll<HTMLButtonElement>("[data-ev]").forEach((b) => {
    b.addEventListener("click", () => focusEvidence(Number(b.dataset.ev)));
    b.addEventListener("mouseenter", () => v2d.hoverEvidence(Number(b.dataset.ev)));
    b.addEventListener("mouseleave", () => v2d.hoverEvidence(null));
  });
}

// --- boot ---------------------------------------------------------------------------------------------------
(async () => {
  await refreshFiles();
  const params = new URLSearchParams(location.search);
  const want = params.get("file");
  applyView(view);
  if (isCustomer() && !want) {
    showLanding(true);
    (window as unknown as { __ready: boolean }).__ready = true;
    return;
  }
  let f = want ? state.files.find((x) => x.path === want) : state.files[0];
  if (want && !f) f = (await listFiles("", want, 5)).find((x) => x.path === want)
    ?? (await listFiles(want.split("/")[1], want, 5, false)).find((x) => x.path === want); // files without questions
  if (f) {
    await openFile(f, params.get("q") ?? "");
    if (params.get("q")) await runAsk();
  }
  (window as unknown as { __ready: boolean }).__ready = true;
})();

/**
 * Knowledge-graph panel under the viewer (Stoa point 4: "linking different data earns points").
 *
 * Renders W1's `stoa.kg.links(path)` (GET /kg): the files of one building and how they relate (IFC model,
 * plan sheets per storey, discipline models, the same building elsewhere; swiss PDF, DXF and PNG), the
 * drawing-vs-model cross-checks, and the rooms with their area from each source. Every row is clickable:
 * files open, rooms are outlined on the drawing and framed in 3D, counts and areas can be asked as questions.
 */
import type { Kg, KgCrossCheck, KgFile, KgRoom } from "./types";

const esc = (s: unknown) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const fmt = (n: number | null | undefined, d = 2) => (n === null || n === undefined || Number.isNaN(n) ? "–" : n.toFixed(d));

export interface KgOpts {
  current: string; // the open file
  openPath: (path: string) => void;
  show3D: () => void;
  setStorey: (name: string) => void;
  focusRoom: (room: KgRoom, label: string) => void;
  ask: (question: string) => void;
}

let expanded = false;

const KIND_LABEL: Record<string, string> = {
  model: "IFC model", "discipline-model": "discipline", plan: "plan", section: "section", elevation: "elevation",
  sibling: "same drawing", floor: "floor", sheet: "sheet",
};
const EXT_LABEL: Record<string, string> = { ".pdf": "PDF", ".dxf": "DXF (CAD)", ".png": "PNG", ".jpg": "JPG", ".svg": "SVG", ".ifc": "IFC" };

const base = (p: string) => p.split("/").pop() ?? p;
/** "bsc-duplex_duplex-electrical-20121207.ifc" → "duplex-electrical-20121207" (drop the project prefix). */
const shortFile = (p: string, project: string) => {
  const b = base(p).replace(/\.[^.]+$/, "");
  const pre = project.split("/").pop() ?? "";
  return pre && b.startsWith(pre + "_") ? b.slice(pre.length + 1) : b;
};

function roomLabel(r: KgRoom) {
  if (r.number) return `${r.number} ${r.name ?? ""}`.trim();
  return r.label ?? [r.long_name, r.name].filter(Boolean).join(" ");
}

/** The question the solvers already understand for this room's area (dataset phrasing). */
function roomQuestion(r: KgRoom, source: string) {
  if (source === "swiss_dwellings" && r.number) return `What is the net floor area of room ${r.number} ('${r.name}') in m²?`;
  const name = r.long_name ? `${r.long_name} (${r.name})` : r.name;
  return `What is the net floor area of the room '${name}'${r.storey_name ? ` on '${r.storey_name}'` : ""}, in m²?`;
}

const DXF_Q: Record<string, [string, string]> = {
  door: ["doors", "How many doors (interior doors and entrance doors together) are drawn on this floor plan?"],
  window: ["windows", "How many windows are drawn on this floor plan?"],
  toilet: ["toilets", "How many toilets (WC) are drawn on this floor plan?"],
  washbasin: ["washbasins", "How many washbasins are drawn on this floor plan?"],
  bathtub: ["bathtubs", "How many bathtubs are drawn on this floor plan?"],
  shower: ["showers", "How many showers are drawn on this floor plan?"],
};

function checkText(c: KgCrossCheck) {
  const sym = c.ok === null ? "?" : c.ok ? "✓" : "≠";
  if (c.storey) {
    const other = Object.entries(c.drawn_other ?? {}).map(([st, n]) => `+${n} of ${st}`).join(", ");
    const ifc = c.model_cut !== undefined && c.model_cut !== c.model ? `IFC ${c.model_cut} at the cut (${c.model} on storey)` : `IFC ${c.model}`;
    return { head: c.what, body: `plan ${c.drawn}${other ? ` ${other}` : ""} · ${ifc}`, sym };
  }
  return { head: c.what, body: `${c.drawn}/${c.model}`, sym };
}

/** W1's one-line explanation of a structured check (links()["checks"]), for tooltips. */
function checkSentence(kg: Kg, c: KgCrossCheck) {
  return (kg.checks ?? []).find((t) => c.storey && t.text.startsWith(`${c.what} on '${c.storey}'`))?.text;
}

/** Rooms that belong to what is open: the plan's storey, the whole model, or the swiss floor. */
function roomsInScope(kg: Kg): KgRoom[] {
  const rooms = kg.rooms ?? [];
  if (kg.source === "ifc_models" && kg.storey) return rooms.filter((r) => r.storey === kg.storey!.guid);
  return rooms;
}

export function renderKg(el: HTMLElement, kg: Kg, o: KgOpts) {
  const project = kg.group ?? kg.source;
  const files = (kg.files ?? []).filter((f) => f.path);
  const storeyName = new Map((kg.storeys ?? []).map((s) => [s.guid, s.name]));
  const modelLabel = (kg.graph?.nodes ?? kg.nodes)?.find((n) => n.type === "model")?.label;
  const rooms = roomsInScope(kg);
  const checks = kg.crosschecks ?? [];

  // ---- chips: the files linked to this one -------------------------------------------------------------
  type Chip = { kind: string; label: string; title: string; on: boolean; act: () => void };
  const chips: Chip[] = [];
  const isIfcProject = kg.source === "ifc_models" || kg.source === "ifc_bench";
  if (isIfcProject) {
    const order = ["model", "plan", "section", "elevation", "discipline-model"];
    const sorted = [...files].sort((a, b) => order.indexOf(a.kind) - order.indexOf(b.kind));
    for (const f of sorted) {
      const st = f.storey ? storeyName.get(f.storey) : null;
      const label = f.kind === "model" ? (modelLabel && modelLabel.length > 2 && !/^\d+$/.test(modelLabel) ? modelLabel : shortFile(f.path, project))
        : st ?? shortFile(f.path, project).replace(/^(plan|section|elevation)-\d+-/, "");
      chips.push({
        kind: KIND_LABEL[f.kind] ?? f.kind, label, title: f.path, on: f.path === o.current,
        act: () => (f.kind === "model" && kg.model === f.path && o.current !== f.path && /\.pdf$/.test(o.current) ? o.show3D() : o.openPath(f.path)),
      });
    }
    for (const p of kg.same_building ?? [])
      chips.push({ kind: "same building", label: base(p), title: `${p} — the same building, published in another dataset`, on: false, act: () => o.openPath(p) });
  } else {
    for (const [ext, p] of Object.entries(kg.siblings ?? {}))
      chips.push({ kind: EXT_LABEL[ext] ?? ext.slice(1), label: p === o.current ? "this file" : base(p), title: p, on: p === o.current,
        act: () => (/\.(pdf|png|jpe?g|ifc)$/i.test(p) ? o.openPath(p) : window.open(`/api/file?path=${encodeURIComponent(p)}`, "_blank")) });
    for (const p of kg.same_site ?? [])
      chips.push({ kind: "same site", label: base(p), title: p, on: false, act: () => o.openPath(p) });
    const seen = new Set([...Object.values(kg.siblings ?? {}), ...(kg.same_site ?? [])]);
    for (const n of kg.nodes ?? []) {
      const p = n.path;
      if (!p || seen.has(p) || p === o.current) continue; // older shape: graph nodes without a path
      seen.add(p);
      chips.push({ kind: n.kind ?? "", label: n.label, title: `${p}${n.relation ? ` — ${n.relation}` : ""}`, on: false,
        act: () => (/\.(pdf|png|jpe?g|ifc)$/i.test(p) ? o.openPath(p) : window.open(`/api/file?path=${encodeURIComponent(p)}`, "_blank")) });
    }
    for (const f of files.filter((f: KgFile) => !seen.has(f.path)))
      chips.push({ kind: KIND_LABEL[f.kind] ?? f.kind, label: base(f.path).replace(/\.(pdf|png|jpe?g)$/i, ""), title: `${f.path}${f.relation ? ` — ${f.relation}` : ""}`, on: false, act: () => o.openPath(f.path) });
  }
  if (chips.filter((c) => !c.on).length === 0 && !checks.length && !rooms.length) {
    el.innerHTML = "";
    return;
  }

  // ---- pills: cross-checks and facts from the linked source --------------------------------------------
  const pills: string[] = [];
  const scopeName = kg.storey?.name;
  const perStorey = !kg.storey && checks.some((c) => c.storey); // a model page: checks for every storey
  if (perStorey) {
    const nOk = checks.filter((c) => c.ok).length;
    const comparable = checks.filter((c) => c.ok !== null).length;
    const storeys = new Set(checks.map((c) => c.storey)).size;
    pills.push(`<span class="kg-pill ${nOk === comparable ? "ok" : "bad"}" title="Element counts per storey: IFC model vs symbols drawn on that storey's plan sheet. Open the details for the table.">${nOk}/${comparable} checks agree on ${storeys} storey plans</span>`);
  }
  if (!perStorey) checks.forEach((c, i) => {
    const t = checkText(c);
    pills.push(`<span class="kg-pill ${c.ok === null ? "info" : c.ok ? "ok" : "bad"}" data-check="${i}" title="${esc(checkSentence(kg, c) ? `${checkSentence(kg, c)}. ` : "")}${esc(c.reason ? `${c.reason}. ` : "")}${esc(c.storey
      ? `Storey '${c.storey}': ${c.model} in the IFC model, ${c.drawn} drawn on the plan sheet (IfcConvert SVG twin of the PDF). A difference means some elements of this storey are not drawn on this sheet.`
      : `${c.what}: ${c.drawn} of ${c.model} agree`)}">${esc(t.head)} <b>${esc(t.body)}</b> ${t.sym}</span>`);
  });
  if (!checks.length)
    for (const c of kg.checks ?? [])
      pills.push(`<span class="kg-pill ${c.ok ? "ok" : "bad"}">${esc(c.text)} ${c.ok ? "✓" : "≠"}</span>`);
  if (kg.counts_dxf) {
    pills.push(`<span class="kg-scope sub">DXF layer, click to ask:</span>`);
    for (const [k, n] of Object.entries(kg.counts_dxf)) {
      const q = DXF_Q[k];
      pills.push(`<button class="kg-pill fact" data-ask="${esc(q?.[1] ?? "")}" title="Counted on the DXF (CAD) layer of this floor. Click to ask, the answer boxes every one on the PDF.">${esc(n)} ${esc(q?.[0] ?? k)}</button>`);
    }
  }
  if (kg.transform)
    pills.unshift(`<span class="kg-pill info" title="DXF → PDF affine fitted on room numbers that occur in both (W2/R1). Every CAD element lands on the PDF and PNG with this error.">CAD-to-PDF fit ${fmt(kg.transform.rms_pt, 2)} pt${kg.transform.scale ? ` · ${esc(kg.transform.scale)}` : ""}</span>`);

  const nRooms = rooms.length;
  const summary = isIfcProject && kg.storeys?.length
    ? `${kg.storeys.length} storeys · ${(kg.rooms ?? []).length} rooms`
    : nRooms ? `${nRooms} rooms` : "";

  el.innerHTML = `
    <div class="kg-bar">
      <div class="kg-line">
        <span class="lk-title" title="${esc(kg.kg_error ? `stoa.kg not available (${kg.kg_error}); links from the file system only` : "stoa.kg: files, storeys, rooms and elements of one building, linked across formats")}">Knowledge graph${kg.kg_error ? " <i>files only</i>" : ""}</span>
        <div class="kg-chips">${chips.map((c, i) => `<button class="lk${c.on ? " on" : ""}" data-chip="${i}" title="${esc(c.title)}"><span class="kind">${esc(c.kind)}</span>${esc(c.label)}</button>`).join("")}</div>
        ${summary || rooms.length ? `<button class="kg-toggle" aria-expanded="${expanded}">${esc(summary || "details")} ${expanded ? "▴" : "▾"}</button>` : ""}
      </div>
      ${pills.length ? `<div class="kg-line checks kg-chips">${scopeName && checks.length ? `<span class="kg-scope">Drawing vs model, ${esc(scopeName)}:</span>` : `<span class="kg-scope">Cross-checks:</span>`}${pills.join("")}</div>` : ""}
    </div>
    <div class="kg-body" ${expanded ? "" : "hidden"}>${body(kg, rooms, checks, files, storeyName, o)}</div>`;

  el.querySelectorAll<HTMLButtonElement>("[data-chip]").forEach((b) => b.addEventListener("click", () => {
    const c = chips[Number(b.dataset.chip)];
    if (!c.on) c.act();
  }));
  el.querySelectorAll<HTMLElement>("[data-ask]").forEach((b) => b.addEventListener("click", (e) => {
    e.stopPropagation();
    if (b.dataset.ask) o.ask(b.dataset.ask);
  }));
  el.querySelector<HTMLButtonElement>(".kg-toggle")?.addEventListener("click", () => {
    expanded = !expanded;
    renderKg(el, kg, o);
    setTimeout(() => window.dispatchEvent(new Event("resize")), 0);
  });
  el.querySelectorAll<HTMLElement>("tr[data-room]").forEach((tr) => tr.addEventListener("click", () => {
    el.querySelectorAll("tr.sel").forEach((x) => x.classList.remove("sel"));
    tr.classList.add("sel");
    const r = rooms[Number(tr.dataset.room)];
    o.focusRoom(r, roomLabel(r));
  }));
  el.querySelectorAll<HTMLElement>("[data-storey]").forEach((b) => b.addEventListener("click", () => o.setStorey(b.dataset.storey!)));
  el.querySelectorAll<HTMLElement>("[data-open]").forEach((b) => b.addEventListener("click", (e) => {
    e.stopPropagation();
    o.openPath(b.dataset.open!);
  }));
}

/**
 * The building's graph as a small layered drawing: other models → IFC model → storeys → plan sheets → rooms.
 * The open file's path through it is highlighted; storeys, sheets and other models are clickable.
 */
function graphSvg(kg: Kg, files: KgFile[], current: string) {
  const storeys = [...(kg.storeys ?? [])].sort((a, b) => b.elevation - a.elevation); // top floor first
  if (!kg.model || !storeys.length) return "";
  const project = kg.group ?? kg.source;
  const plans = new Map(files.filter((f) => f.kind === "plan" && f.storey).map((f) => [f.storey!, f.path]));
  const roomsBy = new Map<string, number>();
  for (const r of kg.rooms ?? []) if (r.storey) roomsBy.set(r.storey, (roomsBy.get(r.storey) ?? 0) + 1);
  const others = [...files.filter((f) => f.kind === "discipline-model").map((f) => ({ path: f.path, label: shortFile(f.path, project), kind: "discipline" })),
    ...(kg.same_building ?? []).map((p) => ({ path: p, label: base(p), kind: "same building" }))].slice(0, 8);
  const ROW = 22;
  const H = Math.max(storeys.length, others.length, 3) * ROW + 26;
  const shift = others.length ? 0 : 156; // no other models: drop that column
  const X = { oth: 4, othR: 132, model: 160 - shift, modelW: 112, st: 318 - shift, stW: 92, plan: 448 - shift, planW: 70, room: 556 - shift };
  const W = 640 - shift;
  const y = (i: number, n: number) => 24 + (H - 24 - n * ROW) / 2 + i * ROW + ROW / 2;
  const modelY = 24 + (H - 24) / 2;
  const cur = kg.storey?.guid;
  const curve = (x1: number, y1: number, x2: number, y2: number, on: boolean) =>
    `<path class="${on ? "on" : ""}" d="M${x1},${y1} C${(x1 + x2) / 2},${y1} ${(x1 + x2) / 2},${y2} ${x2},${y2}"/>`;
  const edges: string[] = [];
  const nodes: string[] = [];
  const modelOn = kg.model === current || !!cur;
  others.forEach((o, i) => {
    const yy = y(i, others.length);
    edges.push(curve(X.othR + 4, yy, X.model, modelY, false));
    nodes.push(`<g class="kn other" data-open="${esc(o.path)}"><title>${esc(o.kind)}: ${esc(o.path)}</title><text x="${X.othR}" y="${yy + 4}" text-anchor="end">${esc(o.label.length > 18 ? o.label.slice(0, 17) + "…" : o.label)}</text></g>`);
  });
  const ml = (kg.graph?.nodes ?? kg.nodes)?.find((n) => n.type === "model")?.label;
  const modelLabel = ml && !/^\d+$/.test(ml) ? ml : shortFile(kg.model, project);
  nodes.push(`<g class="kn model${modelOn ? " on" : ""}"><title>${esc(kg.model)}</title><rect x="${X.model}" y="${modelY - 14}" width="${X.modelW}" height="28" rx="6"/>
    <text x="${X.model + X.modelW / 2}" y="${modelY + 4}" text-anchor="middle">${esc(modelLabel.length > 17 ? modelLabel.slice(0, 16) + "…" : modelLabel)}</text></g>`);
  storeys.forEach((st, i) => {
    const yy = y(i, storeys.length);
    const on = st.guid === cur;
    edges.push(curve(X.model + X.modelW, modelY, X.st, yy, on));
    nodes.push(`<g class="kn storey${on ? " on" : ""}" data-storey="${esc(st.name)}"><title>storey ${esc(st.name)}, elevation ${st.elevation.toFixed(2)} m</title>
      <rect x="${X.st}" y="${yy - 9}" width="${X.stW}" height="18" rx="9"/><text x="${X.st + X.stW / 2}" y="${yy + 4}" text-anchor="middle">${esc(st.name.length > 13 ? st.name.slice(0, 12) + "…" : st.name)}</text></g>`);
    const plan = plans.get(st.guid) ?? st.plan;
    if (plan) {
      const pOn = plan === current;
      edges.push(`<path class="${pOn ? "on" : ""}" d="M${X.st + X.stW},${yy} H${X.plan}"/>`);
      nodes.push(`<g class="kn plan${pOn ? " on" : ""}" data-open="${esc(plan)}"><title>plan sheet ${esc(plan)}</title><rect x="${X.plan}" y="${yy - 8}" width="${X.planW}" height="16" rx="3"/>
        <text x="${X.plan + X.planW / 2}" y="${yy + 4}" text-anchor="middle">plan ${esc((plan.match(/_plan-(\d+)/) ?? [])[1] ?? "")}</text></g>`);
    }
    const nr = roomsBy.get(st.guid);
    if (nr) {
      const from = plan ? X.plan + X.planW : X.st + X.stW;
      edges.push(`<path class="${on ? "on" : ""}" d="M${from},${yy} H${X.room}"/>`);
      nodes.push(`<g class="kn rooms${on ? " on" : ""}"><title>${nr} IfcSpace rooms on ${esc(st.name)}${plan ? ", each drawn on the plan sheet with its outline" : ""}</title><circle cx="${X.room + 7}" cy="${yy}" r="6"/><text x="${X.room + 17}" y="${yy + 4}">${nr} room${nr === 1 ? "" : "s"}</text></g>`);
    }
  });
  const head = (x: number, t: string, anchor = "start") => `<text class="kh" x="${x}" y="12" text-anchor="${anchor}">${t}</text>`;
  return `<svg class="kg-graph" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Knowledge graph of this building">
    ${others.length ? head(X.othR, "OTHER MODELS", "end") : ""}${head(X.model + X.modelW / 2, "IFC MODEL", "middle")}${head(X.st + X.stW / 2, "STOREYS", "middle")}
    ${storeys.some((st) => plans.get(st.guid) ?? st.plan) ? head(X.plan + X.planW / 2, "SHEETS", "middle") : ""}${roomsBy.size ? head(X.room, "ROOMS") : ""}
    <g class="ke">${edges.join("")}</g>${nodes.join("")}</svg>`;
}

function body(kg: Kg, rooms: KgRoom[], checks: KgCrossCheck[], files: KgFile[], storeyName: Map<string, string>, o: KgOpts) {
  const cols: string[] = [];
  const swiss = kg.source === "swiss_dwellings";
  if (rooms.length) {
    const hasB = rooms.some((r) => (swiss ? r.area_m2_printed : r.drawn_area_m2) != null);
    const head = swiss
      ? `<tr><th>Room</th><th>Apt</th><th title="Polygon area on the DXF room layer">DXF m²</th><th title="Area printed in the room label on the PDF">Printed m²</th><th></th><th></th></tr>`
      : `<tr><th>Room</th>${kg.storey ? "" : "<th>Storey</th>"}<th title="IfcSpace body geometry projected to the floor">IFC m²</th>${hasB ? `<th title="Area of the room polygon drawn on the plan sheet, at the fitted plan scale">Drawn m²</th><th></th>` : ""}<th></th></tr>`;
    const rows = rooms.map((r, i) => {
      const a = swiss ? r.area_m2_dxf : r.area_m2;
      const b = swiss ? r.area_m2_printed : r.drawn_area_m2;
      const ok = a !== undefined && b !== undefined && b !== null ? Math.abs(a - b) <= 0.02 * Math.max(a, 0.01) : null;
      const where = swiss ? `<td>${esc(r.apartment ?? "")}</td>` : kg.storey ? "" : `<td>${esc(r.storey_name ?? "")}</td>`;
      return `<tr data-room="${i}" title="${esc(r.guid ? `IfcSpace ${r.guid}` : "")}"><td>${esc(roomLabel(r))}</td>${where}<td class="num">${fmt(a)}</td>${swiss || hasB ? `<td class="num">${fmt(b)}</td>
        <td class="${ok === null ? "na" : ok ? "ok" : "bad"}">${ok === null ? "" : ok ? "✓" : "≠"}</td>` : ""}
        <td><button class="mini" data-ask="${esc(roomQuestion(r, kg.source))}" title="Ask for this room's area">ask</button></td></tr>`;
    }).join("");
    const where = swiss ? "this floor" : kg.storey ? `storey ${kg.storey.name}` : "the model";
    const agree = rooms.filter((r) => {
      const a = swiss ? r.area_m2_dxf : r.area_m2;
      const b = swiss ? r.area_m2_printed : r.drawn_area_m2;
      return a !== undefined && b !== undefined && b !== null && Math.abs(a - b) <= 0.02 * Math.max(a, 0.01);
    }).length;
    const both = rooms.filter((r) => (swiss ? r.area_m2_printed : r.drawn_area_m2) != null).length;
    cols.push(`<div class="kg-col wide"><h4>Rooms on ${esc(where)} <small>${both ? `${agree}/${both} areas agree across sources (±2%)` : ""} · click to locate</small></h4>
      <div class="kg-scroll"><table class="kg-table">${head}${rows}</table></div></div>`);
  }
  const g = graphSvg(kg, files, o.current);
  if (g) cols.push(`<div class="kg-col graph"><h4>Graph <small>model · storeys · sheets · rooms, click a node</small></h4><div class="kg-scroll">${g}</div></div>`);
  if (kg.storeys?.length && !g) {
    const plans = new Map(files.filter((f) => f.storey).map((f) => [f.storey!, f.path]));
    cols.push(`<div class="kg-col"><h4>Storeys <small>click to show in 3D</small></h4><div class="kg-scroll"><table class="kg-table">
      <tr><th>Storey</th><th>Elev. m</th><th>Rooms</th><th>Plan</th></tr>
      ${kg.storeys.map((s) => `<tr class="${kg.storey?.guid === s.guid ? "cur" : ""}" data-storey="${esc(s.name)}"><td>${esc(s.name)}</td><td class="num">${fmt(s.elevation, 2)}</td>
        <td class="num">${(kg.rooms ?? []).filter((r) => r.storey === s.guid).length || ""}</td>
        <td>${plans.get(s.guid) ?? s.plan ? `<button class="mini" data-open="${esc(plans.get(s.guid) ?? s.plan)}">open</button>` : ""}</td></tr>`).join("")}
      </table></div></div>`);
  }
  if (checks.length) {
    cols.push(`<div class="kg-col"><h4>Cross-checks <small>independent sources, same fact</small></h4><div class="kg-scroll"><table class="kg-table">
      <tr>${checks.some((c) => c.storey) && !kg.storey ? "<th>Storey</th>" : ""}<th>What</th><th>${checks.some((c) => c.storey) ? "Plan" : "Agree"}</th><th title="Elements of the storey that cross the plan's cut plane (floor + 1.2 m) / all elements of the storey">${checks.some((c) => c.storey) ? "IFC at cut / all" : "Of"}</th><th></th></tr>
      ${checks.map((c) => `<tr>${c.storey && !kg.storey ? `<td>${esc(c.storey)}</td>` : ""}<td>${esc(c.what)}</td><td class="num">${c.drawn}${Object.values(c.drawn_other ?? {}).reduce((a, n) => a + n, 0) ? ` <small>+${Object.values(c.drawn_other ?? {}).reduce((a, n) => a + n, 0)}</small>` : ""}</td><td class="num" title="${esc(checkSentence(kg, c) ?? "")}">${c.model_cut ?? c.model}${c.model_cut !== undefined && c.model_cut !== c.model ? ` <small>/ ${c.model}</small>` : ""}</td><td class="${c.ok === null ? "na" : c.ok ? "ok" : "bad"}" title="${esc(c.reason ?? "")}">${c.ok === null ? "?" : c.ok ? "✓" : "≠"}</td></tr>`).join("")}
      </table>${kg.storey ? `<p class="kg-note">Plan = elements drawn on this sheet; IFC = elements of storey ${esc(kg.storey.name)} that cross the sheet's cut plane (floor + 1.2 m) / all of the storey. A ≠ is a real difference between the documents, a ? means they cannot be compared (hover for why).</p>` : ""}</div></div>`);
  }
  if (!cols.length) cols.push(`<div class="kg-col"><p class="kg-note">${esc(o.current)} has no linked rooms or storeys.</p></div>`);
  return cols.join("");
}

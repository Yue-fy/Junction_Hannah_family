/**
 * 2D viewer: one PDF page (PDF.js) or one image, with an SVG overlay for Evidence boxes, pan/zoom, and
 * (for ifc_models sheets) a GUID layer from the IfcConvert `.svg` sibling so IFC elements can be
 * highlighted and picked on the drawing.
 *
 * Coordinates ("content px") = the rendered canvas pixels (PDF: viewport px; image: image px).
 *  - pdf_pt  (docs/CONTRACT.md): PyMuPDF unrotated page space, origin top-left, y down. PDF user space is
 *    y-up from the bottom-left of page.view, so  ux = x + view[0],  uy = view[3] - y, then the PDF.js
 *    viewport (which applies /Rotate) maps user space → content px.
 *  - image_px: pixels of the stored image, = content px.
 *  - IfcConvert sheet SVG: pdf_pt = (svg − viewBox origin) × 72/25.4 (KNOWLEDGE 00:20).
 */
import * as pdfjs from "pdfjs-dist";
import pdfWorker from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import type { Evidence, RoomGraph, RoomGraphRoom } from "./types";

pdfjs.GlobalWorkerOptions.workerSrc = pdfWorker;

const SVGNS = "http://www.w3.org/2000/svg";
const MM_TO_PT = 72 / 25.4;
const MAX_CANVAS_SIDE = 4200;

type Mat = [number, number, number, number, number, number];
const apply = (m: Mat, x: number, y: number): [number, number] => [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]];

/** Room-graph regions worth drawing: unlabelled regions with no door and no open link are segmentation fragments
 *  (a strip along a wall, the CubiCasa logo), not rooms of the graph. */
export const roomShown = (r: RoomGraphRoom) => !!r.label || (r.door_to ?? []).length > 0 || (r.open_to ?? []).length > 0;

export class Viewer2D {
  readonly el: HTMLElement;
  private stage: HTMLDivElement;
  private overlay: SVGSVGElement;
  private guidLayer: SVGGElement;
  private evLayer: SVGGElement;
  private kgLayer: SVGGElement;
  private roomLayer: SVGGElement;
  private w = 1;
  private h = 1;
  private z = 1;
  private tx = 0;
  private ty = 0;
  private pdfPtToContent: (x: number, y: number) => [number, number] = (x, y) => [x, y];
  private file = "";
  private guidEls = new Map<string, SVGGElement>();
  private loadToken = 0;
  onPickGuid: (guid: string, label: string) => void = () => {};
  onPickEvidence: (index: number) => void = () => {};
  private evidence: { ev: Evidence; i: number; rect: [number, number, number, number] }[] = [];

  constructor(el: HTMLElement) {
    this.el = el;
    el.classList.add("v2d");
    this.stage = document.createElement("div");
    this.stage.className = "v2d-stage";
    this.overlay = document.createElementNS(SVGNS, "svg");
    this.overlay.classList.add("v2d-overlay");
    this.guidLayer = document.createElementNS(SVGNS, "g");
    this.guidLayer.classList.add("guid-layer");
    this.evLayer = document.createElementNS(SVGNS, "g");
    this.kgLayer = document.createElementNS(SVGNS, "g");
    this.kgLayer.classList.add("kg-layer");
    this.roomLayer = document.createElementNS(SVGNS, "g");
    this.roomLayer.classList.add("room-layer");
    this.overlay.append(this.guidLayer, this.roomLayer, this.kgLayer, this.evLayer);
    el.append(this.stage);
    this.installPanZoom();
  }

  /** Show a PDF page or an image. Resolves when the drawing is visible. */
  async load(file: string, url: string, page = 0): Promise<void> {
    const token = ++this.loadToken;
    this.file = file;
    this.stage.replaceChildren();
    this.guidLayer.replaceChildren();
    this.evLayer.replaceChildren();
    this.kgLayer.replaceChildren();
    this.roomLayer.replaceChildren();
    this.guidEls.clear();
    this.el.dataset.state = "loading";
    if (/\.pdf$/i.test(file)) {
      const doc = await pdfjs.getDocument({ url }).promise;
      const p = await doc.getPage(page + 1);
      const base = p.getViewport({ scale: 1 });
      const scale = Math.min(MAX_CANVAS_SIDE / Math.max(base.width, base.height), 4);
      const vp = p.getViewport({ scale });
      const canvas = document.createElement("canvas");
      canvas.width = Math.ceil(vp.width);
      canvas.height = Math.ceil(vp.height);
      await p.render({ canvas, canvasContext: canvas.getContext("2d")!, viewport: vp }).promise;
      if (token !== this.loadToken) return;
      const view = p.view as number[];
      const m = vp.transform as Mat;
      this.pdfPtToContent = (x, y) => apply(m, x + view[0], view[3] - y);
      this.setContent(canvas, vp.width, vp.height);
    } else {
      const img = new Image();
      img.src = url;
      await img.decode();
      if (token !== this.loadToken) return;
      this.pdfPtToContent = (x, y) => [x, y];
      this.setContent(img, img.naturalWidth, img.naturalHeight);
    }
    this.el.dataset.state = "ready";
    this.fit();
  }

  private setContent(node: HTMLElement, w: number, h: number) {
    this.w = w;
    this.h = h;
    node.classList.add("v2d-content");
    node.style.width = `${w}px`;
    node.style.height = `${h}px`;
    this.overlay.setAttribute("viewBox", `0 0 ${w} ${h}`);
    this.overlay.setAttribute("width", String(w));
    this.overlay.setAttribute("height", String(h));
    this.stage.append(node, this.overlay);
  }

  /** Overlay the IfcConvert sheet SVG (same sheet as the PDF) as an invisible, pickable GUID layer. */
  async loadGuidLayer(svgUrl: string): Promise<number> {
    const token = this.loadToken;
    const text = await (await fetch(svgUrl)).text();
    if (token !== this.loadToken) return 0;
    const doc = new DOMParser().parseFromString(text, "image/svg+xml");
    const vb = (doc.documentElement.getAttribute("viewBox") ?? "0 0 1 1").split(/\s+/).map(Number);
    // affine svg → content px from three points (handles any page rotation)
    const f = (x: number, y: number) => this.pdfPtToContent((x - vb[0]) * MM_TO_PT, (y - vb[1]) * MM_TO_PT);
    const [o, ex, ey] = [f(0, 0), f(1, 0), f(0, 1)];
    const g = document.createElementNS(SVGNS, "g");
    g.setAttribute("transform", `matrix(${ex[0] - o[0]} ${ex[1] - o[1]} ${ey[0] - o[0]} ${ey[1] - o[1]} ${o[0]} ${o[1]})`);
    for (const src of Array.from(doc.querySelectorAll("g[data-guid]"))) {
      const el = document.importNode(src, true) as SVGGElement;
      el.removeAttribute("fill");
      el.removeAttribute("stroke");
      el.removeAttribute("id");
      const cls = (src.getAttribute("class") ?? "").split(/\s+/).pop() ?? "";
      el.setAttribute("class", `guid ${cls}`);
      const label = `${cls.replace(/^Ifc/, "")}${src.getAttribute("data-name") ? " " + src.getAttribute("data-name") : ""}`;
      const title = document.createElementNS(SVGNS, "title");
      title.textContent = `${label} · ${src.getAttribute("data-guid")}`;
      el.prepend(title);
      el.addEventListener("click", (e) => {
        if ((e as MouseEvent).defaultPrevented) return;
        this.onPickGuid(src.getAttribute("data-guid")!, label);
      });
      this.guidEls.set(src.getAttribute("data-guid")!, el);
      g.append(el);
    }
    this.guidLayer.append(g);
    return this.guidEls.size;
  }

  hasGuid(guid: string) {
    return this.guidEls.has(guid);
  }

  highlightGuids(guids: Iterable<string>, cls = "hl") {
    for (const el of this.guidEls.values()) el.classList.remove(cls);
    for (const gid of guids) this.guidEls.get(gid)?.classList.add(cls);
  }

  /** Outline one knowledge-graph item (a room's pdf_pt box) and zoom to it; `null` clears the mark. */
  markBox(bbox: number[] | null, label = "", space: "pdf_pt" | "image_px" = "pdf_pt") {
    this.kgLayer.replaceChildren();
    if (!bbox) return false;
    const r = this.toContent({ file: this.file, bbox, bbox_space: space });
    if (!r) return false;
    const pad = Math.max(this.w, this.h) * 0.002;
    const rect = document.createElementNS(SVGNS, "rect");
    rect.setAttribute("x", String(r[0] - pad));
    rect.setAttribute("y", String(r[1] - pad));
    rect.setAttribute("width", String(r[2] - r[0] + 2 * pad));
    rect.setAttribute("height", String(r[3] - r[1] + 2 * pad));
    const text = document.createElementNS(SVGNS, "text");
    text.setAttribute("x", String(r[0]));
    text.setAttribute("y", String(r[1] - pad * 2));
    text.setAttribute("font-size", String(Math.min(Math.max(this.w, this.h) * 0.007, Math.max((r[3] - r[1]) * 0.12, Math.max(this.w, this.h) * 0.0025))));
    text.textContent = label;
    this.kgLayer.append(rect, text);
    return this.zoomTo(r, 0.8);
  }

  /**
   * R1's room graph of a CubiCasa plan (image px): each room tinted by kind with its printed label and ~m², each
   * door as a small box, and every door drawn as a link room → door → room (dashed: open-plan links, no door).
   * `null` clears it. Hovering a room lights up its links. Returns the number of rooms drawn.
   */
  /** Light up one room of the room graph and its links (null: all equal). */
  focusRoom: (id: string | null) => void = () => {};

  setRoomGraph(g: RoomGraph | null) {
    this.roomLayer.replaceChildren();
    this.roomLayer.classList.remove("focus");
    if (!g) return 0;
    const side = Math.max(this.w, this.h);
    const el = (tag: string, attrs: Record<string, string | number>, parent: SVGElement = this.roomLayer) => {
      const n = document.createElementNS(SVGNS, tag);
      for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, String(v));
      parent.append(n);
      return n;
    };
    const byId = new Map(g.rooms.map((r) => [r.id, r]));
    const name = (r: RoomGraphRoom) => r.label || r.cls;
    const rooms = el("g", { class: "rg-rooms" });
    const links = el("g", { class: "rg-links" });
    const doors = el("g", { class: "rg-doors" });
    const labels = el("g", { class: "rg-labels" });
    const linkEls = new Map<string, SVGElement[]>();
    const boxes = new Map<string, SVGElement>();
    this.focusRoom = (id) => {
      this.roomLayer.querySelectorAll(".on").forEach((n) => n.classList.remove("on"));
      this.roomLayer.classList.toggle("focus", !!id);
      if (!id) return;
      boxes.get(id)?.classList.add("on");
      (linkEls.get(id) ?? []).forEach((n) => n.classList.add("on"));
    };
    const addLink = (n: SVGElement, ...ids: string[]) => ids.forEach((id) => linkEls.set(id, [...(linkEls.get(id) ?? []), n]));
    for (const d of g.doors) {
      const c = [(d.box[0] + d.box[2]) / 2, (d.box[1] + d.box[3]) / 2];
      const ends = d.between.map((id) => byId.get(id)).filter((r): r is RoomGraphRoom => !!r);
      if (ends.length) {
        const pts = ends.length === 2 ? [ends[0].centroid, c, ends[1].centroid] : [ends[0].centroid, c];
        const pl = el("polyline", { points: pts.map((p) => p.join(",")).join(" "), class: `rg-link${ends.length === 1 ? " out" : ""}` }, links);
        addLink(pl, ...ends.map((r) => r.id));
      }
      const r = el("rect", { x: d.box[0], y: d.box[1], width: d.box[2] - d.box[0], height: d.box[3] - d.box[1], class: "rg-door" }, doors);
      el("title", {}, r).textContent = `door ${d.id}: ${d.between.map((id) => (byId.get(id) ? name(byId.get(id)!) : id)).join(" ↔ ")}`;
    }
    const seen = new Set<string>();
    for (const r of g.rooms) for (const o of r.open_to ?? []) {
      const k = [r.id, o].sort().join("|");
      const b = byId.get(o);
      if (seen.has(k) || !b) continue;
      seen.add(k);
      const ln = el("line", { x1: r.centroid[0], y1: r.centroid[1], x2: b.centroid[0], y2: b.centroid[1], class: "rg-link open" }, links);
      addLink(ln, r.id, b.id);
    }
    const fs = side * 0.018;
    for (const r of g.rooms.filter(roomShown)) {
      const [x0, y0, x1, y1] = r.bbox;
      const box = el("rect", { x: x0, y: y0, width: x1 - x0, height: y1 - y0, class: `rg-room k-${r.cls}` }, rooms);
      const to = (r.door_to ?? []).map((id) => (byId.get(id) ? name(byId.get(id)!) : id));
      el("title", {}, box).textContent = `${name(r)} (${r.cls})${r.m2 ? ` · ~${r.m2} m²${r.m2_80 ? ` (80%: ${r.m2_80[0]}–${r.m2_80[1]})` : ""}` : ""}`
        + `${to.length ? ` · doors to: ${to.join(", ")}` : ""}${(r.open_to ?? []).length ? ` · open to: ${r.open_to!.map((id) => (byId.get(id) ? name(byId.get(id)!) : id)).join(", ")}` : ""}`
        + `${(r.windows ?? []).length ? ` · ${r.windows!.length} window${r.windows!.length > 1 ? "s" : ""}` : ""}`;
      boxes.set(r.id, box);
      box.addEventListener("mouseenter", () => this.focusRoom(r.id));
      box.addEventListener("mouseleave", () => this.focusRoom(null));
      if (r.cls === "outdoor" && !r.label) continue;
      const t = el("text", { x: r.centroid[0], y: r.centroid[1] - fs * 0.15, "font-size": fs, class: "rg-label" }, labels);
      t.textContent = name(r);
      if (r.m2) {
        const m = el("text", { x: r.centroid[0], y: r.centroid[1] + fs * 0.95, "font-size": fs * 0.72, class: "rg-label sub" }, labels);
        m.textContent = `~${r.m2} m²`;
      }
    }
    return g.rooms.filter(roomShown).length;
  }

  /** Draw evidence that lives on this file (bbox), plus GUID highlights for ifc_guid evidence. */
  setEvidence(evidence: Evidence[]) {
    this.kgLayer.replaceChildren();
    this.evLayer.replaceChildren();
    this.evidence = [];
    const guids: string[] = [];
    evidence.forEach((ev, i) => {
      if (ev.ifc_guid && this.guidEls.has(ev.ifc_guid)) guids.push(ev.ifc_guid);
      if (!ev.bbox || ev.file !== this.file) return;
      const r = this.toContent(ev);
      if (!r) return;
      this.evidence.push({ ev, i, rect: r });
      const pad = Math.max(this.w, this.h) * 0.003;
      const isPoint = r[2] - r[0] < 1 && r[3] - r[1] < 1;
      const g = document.createElementNS(SVGNS, "g");
      g.classList.add("ev");
      // W1: elements the plan cut does not draw (slabs, high beams) are boxed from the model footprint
      if (/projected: not drawn/i.test(ev.note ?? "")) g.classList.add("projected");
      g.dataset.index = String(i);
      const shape = document.createElementNS(SVGNS, isPoint ? "circle" : "rect");
      if (isPoint) {
        shape.setAttribute("cx", String(r[0]));
        shape.setAttribute("cy", String(r[1]));
        shape.setAttribute("r", String(pad * 3));
      } else {
        shape.setAttribute("x", String(r[0] - pad));
        shape.setAttribute("y", String(r[1] - pad));
        shape.setAttribute("width", String(r[2] - r[0] + 2 * pad));
        shape.setAttribute("height", String(r[3] - r[1] + 2 * pad));
        shape.setAttribute("rx", String(pad));
      }
      const label = document.createElementNS(SVGNS, "text");
      label.setAttribute("x", String(r[0] - pad));
      label.setAttribute("y", String(r[1] - pad * 1.6));
      const side = Math.max(this.w, this.h);
      label.setAttribute("font-size", String(Math.min(Math.max((r[3] - r[1]) * 0.9, side * 0.004), side * 0.009)));
      label.textContent = String(this.evidence.length);
      const title = document.createElementNS(SVGNS, "title");
      title.textContent = ev.note ?? "";
      g.append(title, shape, label);
      g.addEventListener("click", (e) => {
        e.preventDefault();
        this.onPickEvidence(i);
      });
      this.evLayer.append(g);
    });
    this.highlightGuids(guids);
    this.overlay.classList.toggle("has-guid-hl", guids.length > 0);
  }

  private toContent(ev: Evidence): [number, number, number, number] | null {
    const b = ev.bbox as number[];
    if (!b || b.length < 4) return null;
    const pts = ev.bbox_space === "image_px"
      ? [[b[0], b[1]], [b[2], b[3]]]
      : [this.pdfPtToContent(b[0], b[1]), this.pdfPtToContent(b[2], b[3])];
    return [Math.min(pts[0][0], pts[1][0]), Math.min(pts[0][1], pts[1][1]), Math.max(pts[0][0], pts[1][0]), Math.max(pts[0][1], pts[1][1])];
  }

  /** Select one evidence item (by its index in Answer.evidence) and zoom to it. */
  focusEvidence(index: number) {
    this.evLayer.querySelectorAll(".ev").forEach((n) => n.classList.toggle("sel", (n as SVGGElement).dataset.index === String(index)));
    const item = this.evidence.find((e) => e.i === index);
    if (item) return this.zoomTo(item.rect);
    return false;
  }

  focusGuid(guid: string) {
    const el = this.guidEls.get(guid);
    if (!el) return false;
    this.guidLayer.querySelectorAll(".sel").forEach((n) => n.classList.remove("sel"));
    el.classList.add("sel");
    const bb = el.getBBox();
    const ctm = (el.parentNode as SVGGElement).transform.baseVal.consolidate()?.matrix;
    if (!ctm) return false;
    const p0 = [ctm.a * bb.x + ctm.c * bb.y + ctm.e, ctm.b * bb.x + ctm.d * bb.y + ctm.f];
    const p1 = [ctm.a * (bb.x + bb.width) + ctm.c * (bb.y + bb.height) + ctm.e, ctm.b * (bb.x + bb.width) + ctm.d * (bb.y + bb.height) + ctm.f];
    return this.zoomTo([Math.min(p0[0], p1[0]), Math.min(p0[1], p1[1]), Math.max(p0[0], p1[0]), Math.max(p0[1], p1[1])]);
  }

  /** Zoom to the union of all drawn evidence (or fit the page when there is none). */
  frameEvidence() {
    if (!this.evidence.length) {
      const hl = [...this.guidLayer.querySelectorAll(".hl")];
      if (hl.length === 1) return this.focusGuid((hl[0] as SVGGElement).dataset.guid ?? "");
      return this.fit();
    }
    const r = this.evidence.reduce<[number, number, number, number]>((a, e) =>
      [Math.min(a[0], e.rect[0]), Math.min(a[1], e.rect[1]), Math.max(a[2], e.rect[2]), Math.max(a[3], e.rect[3])],
    [Infinity, Infinity, -Infinity, -Infinity]);
    // at least ~1/5 of the sheet, so a single small box (one room label) is shown with its room around it
    const minW = this.w * 0.18;
    const minH = this.h * 0.18;
    const cx = (r[0] + r[2]) / 2;
    const cy = (r[1] + r[3]) / 2;
    const w = Math.max(r[2] - r[0], minW) / 2;
    const h = Math.max(r[3] - r[1], minH) / 2;
    return this.zoomTo([cx - w, cy - h, cx + w, cy + h], 0.2);
  }

  /** The last framing request, replayed when the pane is resized (e.g. side-by-side toggles). */
  private lastView: () => boolean = () => this.fit();

  fit() {
    this.lastView = () => this.fit();
    const W = this.el.clientWidth || 800;
    const H = this.el.clientHeight || 600;
    this.z = Math.min(W / this.w, H / this.h) * 0.96;
    this.tx = (W - this.w * this.z) / 2;
    this.ty = (H - this.h * this.z) / 2;
    this.apply(true);
    return true;
  }

  zoomTo(r: [number, number, number, number], margin = 1.5) {
    this.lastView = () => this.zoomTo(r, margin);
    const W = this.el.clientWidth || 800;
    const H = this.el.clientHeight || 600;
    const rw = Math.max(r[2] - r[0], this.w * 0.03);
    const rh = Math.max(r[3] - r[1], this.h * 0.03);
    const fitZ = Math.min(W / this.w, H / this.h);
    this.z = Math.max(fitZ * 0.96, Math.min(W / (rw * (1 + 2 * margin)), H / (rh * (1 + 2 * margin)), fitZ * 40));
    const cx = (r[0] + r[2]) / 2;
    const cy = (r[1] + r[3]) / 2;
    this.tx = W / 2 - cx * this.z;
    this.ty = H / 2 - cy * this.z;
    this.apply(true);
    return true;
  }

  private apply(animate = false) {
    this.stage.style.transition = animate ? "transform 450ms cubic-bezier(.2,.7,.2,1)" : "none";
    this.stage.style.transform = `translate(${this.tx}px, ${this.ty}px) scale(${this.z})`;
    this.el.style.setProperty("--z", String(this.z));
  }

  private installPanZoom() {
    this.el.addEventListener("wheel", (e) => {
      e.preventDefault();
      const rect = this.el.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const k = Math.exp(-e.deltaY * 0.0015);
      const nz = Math.min(Math.max(this.z * k, 0.02), 60);
      this.tx = mx - ((mx - this.tx) * nz) / this.z;
      this.ty = my - ((my - this.ty) * nz) / this.z;
      this.z = nz;
      this.lastView = () => false;
      this.apply();
    }, { passive: false });
    let drag: { x: number; y: number; tx: number; ty: number; moved: boolean } | null = null;
    this.el.addEventListener("pointerdown", (e) => {
      drag = { x: e.clientX, y: e.clientY, tx: this.tx, ty: this.ty, moved: false };
    });
    window.addEventListener("pointermove", (e) => {
      if (!drag) return;
      const dx = e.clientX - drag.x;
      const dy = e.clientY - drag.y;
      if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
      if (!drag.moved) return;
      this.el.classList.add("dragging");
      this.tx = drag.tx + dx;
      this.ty = drag.ty + dy;
      this.lastView = () => false;
      this.apply();
    });
    window.addEventListener("pointerup", () => {
      if (drag?.moved) {
        // swallow the click that ends a drag
        const stop = (ev: Event) => ev.stopPropagation();
        this.el.addEventListener("click", stop, { capture: true, once: true });
        setTimeout(() => this.el.removeEventListener("click", stop, { capture: true }), 0);
      }
      drag = null;
      this.el.classList.remove("dragging");
    });
    this.el.addEventListener("dblclick", () => this.fit());
    new ResizeObserver(() => this.el.dataset.state === "ready" && this.lastView()).observe(this.el);
  }
}

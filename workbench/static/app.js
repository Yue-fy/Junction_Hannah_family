"use strict";
// Expert workbench front end: plain JS, no build step.

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const SVGNS = "http://www.w3.org/2000/svg";

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  let body;
  try { body = await r.json(); } catch { body = { error: r.statusText }; }
  if (!r.ok) throw new Error(body.detail || body.error || r.statusText);
  return body;
}

function flash(msg = "Saved ✓") {
  const f = $("#saved-flash");
  f.textContent = msg; f.hidden = false;
  clearTimeout(flash._t); flash._t = setTimeout(() => (f.hidden = true), 1600);
  counts();
}

function confWords(c) {
  if (c == null) return "";
  const p = Math.round(c * 100);
  const w = c >= 0.8 ? "high" : c >= 0.5 ? "medium" : "low";
  return `confidence ${p}% (${w})`;
}

// ---------------------------------------------------------------------------------------------------------
// Zoom/pan viewer with an SVG overlay in image-pixel coordinates.
class Viewer {
  constructor(el) {
    this.el = el;
    el.innerHTML = `<div class="stage"><img alt="drawing"><svg></svg></div>
      <div class="zoombar"><button data-z="in" title="Zoom in">+</button><button data-z="out" title="Zoom out">−</button>
      <button data-z="fit" title="Fit to window">⤢</button></div><div class="empty" hidden></div><div class="loading" hidden>Loading drawing…</div>`;
    this.stage = $(".stage", el); this.img = $("img", el); this.svg = $("svg", el);
    this.emptyEl = $(".empty", el); this.loadingEl = $(".loading", el);
    this.s = 1; this.tx = 0; this.ty = 0; this.w = 1; this.h = 1;
    this.boxes = []; this.marks = []; this.marking = false; this.onMarks = null;
    $$(".zoombar button", el).forEach((b) => b.addEventListener("click", (e) => {
      e.stopPropagation();
      const z = b.dataset.z;
      if (z === "fit") this.fit(); else this.zoomAt(this.el.clientWidth / 2, this.el.clientHeight / 2, z === "in" ? 1.5 : 1 / 1.5);
    }));
    el.addEventListener("wheel", (e) => {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      this.zoomAt(e.clientX - r.left, e.clientY - r.top, Math.exp(-e.deltaY * 0.0015));
    }, { passive: false });
    let drag = null;
    el.addEventListener("pointerdown", (e) => {
      if (e.target.closest(".zoombar")) return;
      el.setPointerCapture(e.pointerId);
      const r = el.getBoundingClientRect();
      if (this.marking) {
        const p = this.toImg(e.clientX - r.left, e.clientY - r.top);
        drag = { mark: true, x0: p.x, y0: p.y, rect: this._rect([p.x, p.y, p.x, p.y], "mine-box") };
      } else {
        drag = { x: e.clientX, y: e.clientY, tx: this.tx, ty: this.ty };
        el.classList.add("dragging");
      }
    });
    el.addEventListener("pointermove", (e) => {
      if (!drag) return;
      if (drag.mark) {
        const r = el.getBoundingClientRect();
        const p = this.toImg(e.clientX - r.left, e.clientY - r.top);
        this._setRect(drag.rect, [Math.min(drag.x0, p.x), Math.min(drag.y0, p.y), Math.max(drag.x0, p.x), Math.max(drag.y0, p.y)]);
      } else {
        this.tx = drag.tx + (e.clientX - drag.x); this.ty = drag.ty + (e.clientY - drag.y); this.apply();
      }
    });
    const end = (e) => {
      if (!drag) return;
      if (drag.mark) {
        const r = el.getBoundingClientRect();
        const p = this.toImg(e.clientX - r.left, e.clientY - r.top);
        const b = [Math.min(drag.x0, p.x), Math.min(drag.y0, p.y), Math.max(drag.x0, p.x), Math.max(drag.y0, p.y)].map((v) => Math.round(v));
        drag.rect.remove();
        if (b[2] - b[0] > 3 && b[3] - b[1] > 3) { this.marks.push(b); this.drawMarks(); this.onMarks && this.onMarks(this.marks); }
      }
      drag = null; el.classList.remove("dragging");
    };
    el.addEventListener("pointerup", end); el.addEventListener("pointercancel", end);
    window.addEventListener("resize", () => this.loaded && this.fit());
  }
  toImg(cx, cy) { return { x: (cx - this.tx) / this.s, y: (cy - this.ty) / this.s }; }
  apply() { this.stage.style.transform = `translate(${this.tx}px, ${this.ty}px) scale(${this.s})`; this._labels(); }
  zoomAt(cx, cy, f) {
    const s2 = Math.min(Math.max(this.s * f, this.minS * 0.5), 12);
    f = s2 / this.s;
    this.tx = cx - (cx - this.tx) * f; this.ty = cy - (cy - this.ty) * f; this.s = s2; this.apply();
  }
  fit() {
    const W = this.el.clientWidth, H = this.el.clientHeight;
    this.s = this.minS = Math.min(W / this.w, H / this.h) * 0.97;
    this.tx = (W - this.w * this.s) / 2; this.ty = (H - this.h * this.s) / 2; this.apply();
  }
  focusBox(b) {
    const W = this.el.clientWidth, H = this.el.clientHeight;
    const bw = Math.max(b[2] - b[0], 40), bh = Math.max(b[3] - b[1], 40);
    this.s = Math.min(Math.min(W / (bw * 4), H / (bh * 4)), 6, Math.max(this.minS * 3, this.minS));
    if (this.s < this.minS) this.s = this.minS;
    const cx = (b[0] + b[2]) / 2, cy = (b[1] + b[3]) / 2;
    this.tx = W / 2 - cx * this.s; this.ty = H / 2 - cy * this.s; this.apply();
  }
  empty(msg) {
    this.loaded = false; this.stage.hidden = true; this.emptyEl.hidden = false; this.emptyEl.innerHTML = msg;
    $(".zoombar", this.el).hidden = true; this.loadingEl.hidden = true;
  }
  load(view, marks = []) {
    return new Promise((res) => {
      this.emptyEl.hidden = true; this.stage.hidden = false; $(".zoombar", this.el).hidden = false;
      this.loadingEl.hidden = false;
      this.w = view.w; this.h = view.h; this.view = view;
      this.img.width = view.w; this.img.height = view.h;
      this.svg.setAttribute("width", view.w); this.svg.setAttribute("height", view.h);
      this.svg.setAttribute("viewBox", `0 0 ${view.w} ${view.h}`);
      this.boxes = view.boxes || []; this.marks = marks.slice();
      this.img.onload = this.img.onerror = () => { this.loadingEl.hidden = true; res(); };
      this.img.src = view.img;
      this.loaded = true; this.fit(); this.draw();
    });
  }
  _rect(b, cls) {
    const r = document.createElementNS(SVGNS, "rect");
    r.setAttribute("class", cls); this._setRect(r, b); this.svg.appendChild(r); return r;
  }
  _setRect(r, b) {
    r.setAttribute("x", b[0]); r.setAttribute("y", b[1]);
    r.setAttribute("width", Math.max(b[2] - b[0], 0)); r.setAttribute("height", Math.max(b[3] - b[1], 0));
  }
  draw(focusI = null) {
    this.svg.innerHTML = "";
    this.boxes.forEach((bx, k) => {
      const b = bx.box;
      const n = k + 1;
      if (bx.point) {
        const c = document.createElementNS(SVGNS, "circle");
        c.setAttribute("cx", b[0]); c.setAttribute("cy", b[1]); c.setAttribute("class", "ev-pt");
        c.dataset.r = 7; this.svg.appendChild(c);
      } else {
        const pad = 2;
        const r = this._rect([b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad], "ev-box" + (focusI === bx.i ? " focus" : ""));
        r.dataset.i = bx.i;
      }
      const t = document.createElementNS(SVGNS, "text");
      t.setAttribute("class", "ev-lbl"); t.setAttribute("x", b[0]); t.setAttribute("y", b[1]); t.textContent = n;
      this.svg.appendChild(t);
    });
    this.drawMarks(); this._labels();
  }
  drawMarks() {
    $$(".mine-box", this.svg).forEach((r) => r.remove());
    this.marks.forEach((b) => this._rect(b, "mine-box"));
  }
  _labels() {  // keep labels and point markers a constant size on screen
    const k = 1 / this.s;
    $$("text.ev-lbl", this.svg).forEach((t) => { t.setAttribute("font-size", 15 * k); t.setAttribute("dy", -4 * k); });
    $$("circle.ev-pt", this.svg).forEach((c) => c.setAttribute("r", 7 * k));
  }
  setMarking(on) { this.marking = on; this.el.classList.toggle("marking", on); }
}

// ---------------------------------------------------------------------------------------------------------
// Tabs
$$(".tab").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
function showTab(name) {
  $$(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  $$(".tabpane").forEach((p) => (p.hidden = p.id !== `tab-${name}`));
  try { localStorage.setItem("wb-tab", name); } catch {}
  if (name === "audit") audit.viewer.loaded && audit.viewer.fit();
  if (name === "ask") { asker.init(); asker.viewer.loaded && asker.viewer.fit(); }
  if (name === "rules") rules.load();
}

// Evidence list shared by tab 1 and tab 2
function renderEvidence(listEl, views, other, viewer, onPickView) {
  listEl.innerHTML = "";
  let n = 0;
  views.forEach((v, vi) => v.boxes.forEach((bx, k) => {
    n++;
    const li = document.createElement("li");
    li.value = k + 1;
    li.innerHTML = `${views.length > 1 ? `<small>[${esc(v.name)}${v.n_pages > 1 ? ` p.${v.page + 1}` : ""}]</small> ` : ""}${esc(bx.note || "(no note)")}`;
    li.addEventListener("click", async () => {
      if (viewer.view !== v) await onPickView(vi);
      $$("li", listEl).forEach((x) => x.classList.remove("focus")); li.classList.add("focus");
      viewer.draw(bx.i); viewer.focusBox(bx.box);
    });
    listEl.appendChild(li);
  }));
  const MAX = 40;
  other.slice(0, MAX).forEach((e) => {
    n++;
    const li = document.createElement("li");
    li.className = "nodraw";
    const where = e.ifc_guid ? `IFC element ${esc(e.ifc_guid)}` : esc(e.file || "");
    li.innerHTML = `${esc(e.note || "(no note)")} <small>— ${where} (not drawable on this sheet)</small>`;
    listEl.appendChild(li);
  });
  if (other.length > MAX) {
    const li = document.createElement("li"); li.className = "nodraw";
    li.textContent = `… and ${other.length - MAX} more model elements`; listEl.appendChild(li);
  }
  return n;
}

function renderNotes(el, assumptions, missing) {
  let h = "";
  if (assumptions && assumptions.length) h += `<div class="h">Assumptions</div><ul>${assumptions.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>`;
  if (missing && missing.length) h += `<div class="h">What would make it certain</div><ul>${missing.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>`;
  el.innerHTML = h;
}

function viewTabs(el, views, cur, pick) {
  el.innerHTML = "";
  if (views.length <= 1) return;
  views.forEach((v, i) => {
    const b = document.createElement("button");
    b.textContent = `${v.name.slice(0, 40)}${v.n_pages > 1 ? ` · page ${v.page + 1}` : ""} (${v.boxes.length})`;
    b.classList.toggle("active", i === cur);
    b.addEventListener("click", () => pick(i));
    el.appendChild(b);
  });
}

// ---------------------------------------------------------------------------------------------------------
// Tab 1: audit
const audit = {
  viewer: new Viewer($("#audit-viewer")), items: [], idx: 0, cur: null, cache: new Map(),
  async init() {
    const r = await api("api/audit/items");
    this.items = r.items;
    if (!this.items.length) {
      $("#audit-question").textContent = "No items to check yet.";
      this.viewer.empty("The audit sample has not been prepared yet.");
      return;
    }
    const first = this.items.findIndex((it) => !it.verdict);
    this.idx = first >= 0 ? first : 0;
    this.progress();
    await this.show();
  },
  progress() {
    const done = this.items.filter((it) => it.verdict).length;
    $("#audit-progress").textContent = `${done} / ${this.items.length} checked`;
    $("#audit-bar").style.width = `${(100 * done) / this.items.length}%`;
  },
  async get(id) {
    if (!this.cache.has(id)) this.cache.set(id, api(`api/audit/item/${encodeURIComponent(id)}`));
    return this.cache.get(id);
  },
  async show() {
    const it = this.items[this.idx];
    let d;
    try { d = await this.get(it.item_id); } catch (e) { this.viewer.empty(`Could not load: ${esc(e.message)}`); return; }
    this.cur = d;
    $("#audit-meta").textContent = `Item ${this.idx + 1} of ${this.items.length} · ${d.source} · ${d.type} · ${d.drawing_name}`;
    $("#audit-question").textContent = d.question;
    $("#audit-answer").textContent = d.answer;
    $("#audit-conf").textContent = confWords(d.confidence);
    $("#audit-ref").textContent = d.reference;
    $("#audit-match").textContent = d.matches_reference === true ? "our answer matches it" :
      d.matches_reference === false ? "our answer differs" : "free-text answer: please compare";
    renderNotes($("#audit-assumptions"), d.assumptions, d.missing);
    $("#audit-trace").innerHTML = d.trace.map((t) => `<li>${esc(t)}</li>`).join("");
    $("#audit-comment").value = "";
    $$(".verdicts .v").forEach((b) => b.classList.toggle("chosen", !!(d.last && d.last.verdict === b.dataset.v)));
    $("#audit-last").textContent = d.last ? `Already checked: ${d.last.verdict.replace("_", " ")}${d.last.comment ? ` — “${d.last.comment}”` : ""}. Press a button again to change it.` : "";
    $("#audit-credit").textContent = `Drawing: ${d.drawing_name} — ${d.credit}`;
    const pick = async (vi) => {
      this.vi = vi;
      viewTabs($("#audit-views"), d.views, vi, pick);
      const v = d.views[vi];
      $("#audit-credit").textContent = `Drawing: ${v.name} — ${v.credit}`;
      await this.viewer.load(v);
    };
    if (d.views.length) await pick(0);
    else {
      $("#audit-views").innerHTML = "";
      this.viewer.empty(d.path.endsWith(".ifc") ?
        `This question is about a <b>3D building model (IFC)</b>, not a drawing.<br>The evidence is a list of model elements on the right.` :
        "No drawing to show for this question.");
    }
    const n = renderEvidence($("#audit-evidence"), d.views, d.other_evidence, this.viewer, pick);
    $("#audit-ev-n").textContent = n;
    if (!n) $("#audit-evidence").innerHTML = `<li class="nodraw">Our system gave no evidence for this answer.</li>`;
    // prefetch the next item
    const nx = this.items[this.idx + 1];
    if (nx) this.get(nx.item_id).then((nd) => nd.views.forEach((v) => { const im = new Image(); im.src = v.img; })).catch(() => {});
  },
  async verdict(v) {
    if (!this.cur) return;
    const comment = $("#audit-comment").value;
    try {
      await api("api/audit", { method: "POST", body: JSON.stringify({ item_id: this.cur.item_id, verdict: v, comment }) });
    } catch (e) { alert(`Could not save: ${e.message}`); return; }
    this.items[this.idx].verdict = v;
    this.cache.delete(this.cur.item_id);
    flash(); this.progress();
    if (this.items.every((it) => it.verdict)) {
      flash("All items checked — thank you!");
    }
    const nxt = this.items.findIndex((it, i) => i > this.idx && !it.verdict);
    this.idx = nxt >= 0 ? nxt : Math.min(this.idx + 1, this.items.length - 1);
    await this.show();
  },
  move(d) { const j = this.idx + d; if (j >= 0 && j < this.items.length) { this.idx = j; this.show(); } },
};
$$(".verdicts .v").forEach((b) => b.addEventListener("click", () => audit.verdict(b.dataset.v)));
$("#audit-prev").addEventListener("click", () => audit.move(-1));
$("#audit-next").addEventListener("click", () => audit.move(1));
document.addEventListener("keydown", (e) => {
  if ($("#tab-audit").hidden || e.target.matches("textarea, input") || e.ctrlKey || e.metaKey || e.altKey) return;
  const v = { 1: "supports", 2: "wrong", 3: "cant_tell" }[e.key];
  if (v) { e.preventDefault(); audit.verdict(v); }
  if (e.key === "ArrowRight") audit.move(1);
  if (e.key === "ArrowLeft") audit.move(-1);
});

// ---------------------------------------------------------------------------------------------------------
// Tab 2: add a hard question
const asker = {
  viewer: new Viewer($("#ask-viewer")), started: false, path: null, page: 0, nPages: 1, system: null, view: null,
  async init() {
    if (this.started) return;
    this.started = true;
    await this.groups();
    this.listMine();
  },
  async groups(q = "") {
    const box = $("#pick-groups");
    box.innerHTML = `<p class="hint">Loading drawings…</p>`;
    let r;
    try { r = await api(`api/catalog${q ? `?q=${encodeURIComponent(q)}` : ""}`); } catch (e) { box.textContent = e.message; return; }
    box.innerHTML = "";
    $("#pick-jump").innerHTML = r.groups.length > 1 ? "Jump to: " + r.groups.map((g) =>
      `<button data-g="grp-${esc(g.source)}">${esc(g.label.replace(/ \(.*\)$/, ""))}</button>`).join("") : "";
    $$("#pick-jump button").forEach((b) => b.addEventListener("click", () => document.getElementById(b.dataset.g).scrollIntoView({ behavior: "smooth" })));
    r.groups.forEach((g) => {
      const div = document.createElement("div"); div.className = "group"; div.id = `grp-${g.source}`;
      div.innerHTML = `<h3>${esc(g.label)}${g.historical ? `<span class="tag">historical, no questions yet</span>` : ""}</h3><div class="cards"></div>`;
      const cards = $(".cards", div);
      if (!g.drawings.length) cards.innerHTML = `<p class="hint">Nothing found.</p>`;
      g.drawings.forEach((d) => {
        const c = document.createElement("button"); c.className = "dcard"; c.title = d.path;
        c.innerHTML = `<img loading="lazy" alt="" src="api/img?path=${encodeURIComponent(d.path)}&page=0&max=360">
          <div class="nm">${esc(d.name)}</div><div class="nq">${d.n_questions ? `${d.n_questions} dataset questions` : "no dataset questions"}</div>`;
        c.addEventListener("click", () => this.open(d.path));
        cards.appendChild(c);
      });
      box.appendChild(div);
    });
  },
  async open(path, page = 0) {
    this.path = path; this.page = page; this.system = null;
    $("#picker").hidden = true; $("#asker").hidden = false; $("#q-result").hidden = true;
    let v;
    try { v = await api(`api/view?path=${encodeURIComponent(path)}&page=${page}`); } catch (e) { this.viewer.empty(esc(e.message)); return; }
    this.view = v; this.nPages = v.n_pages;
    $("#ask-name").textContent = v.name; $("#ask-name").title = v.name;
    $("#ask-credit").textContent = `Drawing: ${v.name} — ${v.credit}`;
    const pg = $("#ask-pages");
    pg.innerHTML = v.n_pages > 1 ? `Page <select id="ask-page">${Array.from({ length: v.n_pages }, (_, i) => `<option value="${i}" ${i === page ? "selected" : ""}>${i + 1}</option>`).join("")}</select> of ${v.n_pages}` : "";
    if (v.n_pages > 1) $("#ask-page").addEventListener("change", (e) => this.open(this.path, +e.target.value));
    await this.viewer.load(v, []);
  },
  async ask() {
    const question = $("#q-text").value.trim();
    if (!question) { alert("Please write a question first."); return; }
    const res = $("#q-result"); res.hidden = false; res.className = "result";
    res.innerHTML = `Our system is working on it… (usually a few seconds, up to a minute)`;
    $("#q-ask").disabled = true;
    try {
      const r = await api("api/ask", { method: "POST", body: JSON.stringify({ path: this.path, question }) });
      this.system = r;
      if (!r.ok) { res.className = "result err"; res.innerHTML = `Our system failed: ${esc(r.error)}`; return; }
      const mine = $("#q-answer").value.trim();
      const cost = r.cost || {};
      res.innerHTML = `<div class="lbl">Our system says</div><div class="big">${esc(r.answer)}</div>
        <div>${confWords(r.confidence)} · ${esc(r.solver)} · ${cost.wall_seconds ?? "?"} s${cost.llm_calls ? ` · ${cost.llm_calls} model call(s)` : ""}</div>
        ${mine ? `<div>Your answer: <b>${esc(mine)} ${esc($("#q-unit").value)}</b></div>` : ""}
        <div class="notes" id="q-notes"></div>
        <details open><summary>Evidence (<span id="q-ev-n">0</span>)</summary><ol id="q-evidence" class="evlist"></ol></details>
        <details><summary>How our system worked it out</summary><ol class="trace">${(r.trace || []).map((t) => `<li>${esc(t)}</li>`).join("")}</ol></details>`;
      renderNotes($("#q-notes"), r.assumptions, r.missing);
      // show our boxes on the page she is looking at (or the first view with boxes)
      const views = r.views || [];
      let vi = views.findIndex((v) => v.path === this.path && v.page === this.page);
      if (vi < 0 || !views[vi].boxes.length) vi = views.findIndex((v) => v.boxes.length);
      const pick = async (i) => {
        const v = views[i];
        if (v.path !== this.path || v.page !== this.page) { await this.open(v.path, v.page); this.system = r; res.hidden = false; }
        this.viewer.boxes = v.boxes; this.viewer.view = v; this.viewer.draw();
      };
      if (vi >= 0) await pick(vi);
      $("#q-ev-n").textContent = renderEvidence($("#q-evidence"), views, r.other_evidence || [], this.viewer, pick);
    } catch (e) {
      res.className = "result err"; res.innerHTML = `Could not ask: ${esc(e.message)}`;
    } finally { $("#q-ask").disabled = false; }
  },
  async save() {
    const question = $("#q-text").value.trim();
    if (!question) { alert("Please write a question first."); return; }
    const type = $("#q-type").value, ans = $("#q-answer").value.trim();
    if (type !== "text" && ans && !/^\s*[-+]?\d+(?:[.,]\d+)?\s*%?\s*$/.test(ans) &&
        !confirm(`"${ans}" is not a single number, so it cannot be scored automatically. Save anyway? (Tip: choose "Text" for several numbers.)`)) return;
    const body = {
      path: this.path, page: this.page, question, answer: ans, unit: $("#q-unit").value, type,
      method: $("#q-method").value, sureness: ($("input[name=sure]:checked") || {}).value || "",
      marks: this.viewer.marks, system: this.system,
    };
    try {
      const r = await api("api/questions", { method: "POST", body: JSON.stringify(body) });
      flash(`Saved ✓ (${r.n} questions so far)`);
      $("#q-text").value = ""; $("#q-answer").value = ""; $("#q-method").value = "";
      this.system = null; $("#q-result").hidden = true;
      this.viewer.marks = []; this.viewer.boxes = []; this.viewer.draw();
      this.listMine();
    } catch (e) { alert(`Could not save: ${e.message}`); }
  },
  async listMine() {
    const r = await api("api/questions");
    $("#q-count").textContent = r.questions.length;
    $("#q-list").innerHTML = r.questions.map((q) => `<li><b>${esc(q.question)}</b> → ${esc(q.answer || "?")} ${esc(q.unit || "")}
      ${q.system ? `<small>(ours: ${esc(q.system.value)} ${esc(q.system.unit || "")})</small>` : ""}</li>`).join("");
  },
};
$("#pick-search-btn").addEventListener("click", () => asker.groups($("#pick-search").value.trim()));
$("#pick-search").addEventListener("keydown", (e) => { if (e.key === "Enter") asker.groups(e.target.value.trim()); });
$("#pick-reset").addEventListener("click", () => { $("#pick-search").value = ""; asker.groups(); });
$("#ask-change").addEventListener("click", () => { $("#asker").hidden = true; $("#picker").hidden = false; });
$("#q-ask").addEventListener("click", () => asker.ask());
$("#q-save").addEventListener("click", () => asker.save());
$("#ask-mark").addEventListener("click", (e) => {
  const on = !asker.viewer.marking; asker.viewer.setMarking(on); e.target.classList.toggle("on", on);
  e.target.textContent = on ? "✎ Marking: drag a box (click to stop)" : "✎ Mark on drawing";
});
const DEFAULT_UNIT = { count: "count", area: "m2", length: "m", volume: "m3", ratio: "%", text: "" };
$("#q-type").addEventListener("change", (e) => { $("#q-unit").value = DEFAULT_UNIT[e.target.value] ?? ""; });
$("#ask-clear").addEventListener("click", () => { asker.viewer.marks = []; asker.viewer.drawMarks(); });

// ---------------------------------------------------------------------------------------------------------
// Tab 3: rules
const rules = {
  async load() {
    const r = await api("api/rules");
    $("#rule-count").textContent = r.rules.length;
    $("#rule-table tbody").innerHTML = r.rules.map((x) => `<tr><td>${esc(x.what || "—")}</td>
      <td>${x.min != null || x.max != null ? `${esc(x.min ?? "?")} – ${esc(x.max ?? "?")} ${esc(x.unit || "")}` : "—"}</td>
      <td>${esc(x.why || "")}${x.uncertainty ? `<br><i>${esc(x.uncertainty)}</i>` : ""}</td></tr>`).join("");
  },
};
$("#rule-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const body = Object.fromEntries(new FormData(e.target).entries());
  try {
    await api("api/rules", { method: "POST", body: JSON.stringify(body) });
    e.target.reset(); flash(); rules.load();
  } catch (err) { alert(`Could not save: ${err.message}`); }
});

async function counts() {
  try {
    const h = await api("api/health");
    $("#cnt-audit").textContent = h.items ? `(${h.audited}/${h.items})` : "";
    $("#cnt-ask").textContent = h.questions ? `(${h.questions})` : "";
    $("#cnt-rules").textContent = h.rules ? `(${h.rules})` : "";
  } catch {}
}

// ---------------------------------------------------------------------------------------------------------
counts();
audit.init();
let startTab = "audit";
try { startTab = localStorage.getItem("wb-tab") || "audit"; } catch {}
showTab(["audit", "ask", "rules"].includes(startTab) ? startTab : "audit");

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

function costWords(c) {
  // what the answer cost us (Stoa scores cost): language-model tokens and time
  if (!c) return "";
  const tok = (c.llm_tokens_in || 0) + (c.llm_tokens_out || 0);
  const t = c.latency_s ?? c.wall_seconds;
  const bits = [tok ? `${tok.toLocaleString("en")} model tokens` : "no language model", t != null ? `${(+t).toFixed(1)} s` : ""];
  return "cost: " + bits.filter(Boolean).join(", ");
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
    el.addEventListener("pointermove", (e) => {
      if (drag || !this.onHover) return;
      const r = el.getBoundingClientRect();
      this.onHover(this.toImg(e.clientX - r.left, e.clientY - r.top));
    });
    const end = (e) => {
      if (!drag) return;
      if (!drag.mark && this.onClick && Math.hypot(e.clientX - drag.x, e.clientY - drag.y) < 5) {
        const r = el.getBoundingClientRect();
        this.onClick(this.toImg(e.clientX - r.left, e.clientY - r.top), e);
      }
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
    if (!W || !H) { this.needFit = true; return; }  // hidden tab: fit when shown
    this.needFit = false;
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
    this.drawMarks(); this.onDraw && this.onDraw(this.svg); this._labels();
  }
  drawMarks() {
    $$(".mine-box", this.svg).forEach((r) => r.remove());
    this.marks.forEach((b) => this._rect(b, "mine-box"));
  }
  _labels() {  // keep labels and point markers a constant size on screen
    if (!(this.s > 0) || !isFinite(this.s)) return;
    const k = 1 / this.s;
    $$("text.ev-lbl", this.svg).forEach((t) => { t.setAttribute("font-size", 15 * k); t.setAttribute("dy", -4 * k); });
    $$("circle.ev-pt", this.svg).forEach((c) => c.setAttribute("r", 7 * k));
    this.onZoom && this.onZoom(k);
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
    this.items = r.items; this.moreN = r.more_available || 0;
    this.batches(r.batches || []);
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
  batches(list) {
    // new batches (e.g. Stoa's example questions) are offered at once, not only when the current sample is done
    const el = $("#audit-batches");
    el.hidden = !list.length;
    el.innerHTML = list.map((b) => `<div>New to check: <button class="primary" data-batch="${esc(b.name)}">Load ${b.n} items: ${esc(b.label)}</button>
      ${b.n_ref < b.n ? `<div class="small">${b.n - b.n_ref} of them have no reference answer yet: your judgement (and the right answer, if you know it) becomes the reference.</div>` : ""}</div>`).join("");
    $$("button[data-batch]", el).forEach((btn) => btn.addEventListener("click", () => this.load(btn.dataset.batch)));
  },
  async load(name) {
    let r;
    try { r = await api(`api/audit/more?name=${encodeURIComponent(name)}`, { method: "POST" }); } catch (e) { alert(e.message); return; }
    flash(`${r.added} new items`);
    await this.init();
    const j = r.first ? this.items.findIndex((it) => it.item_id === r.first) : -1;
    if (j >= 0) { this.idx = j; this.progress(); await this.show(); }
  },
  progress() {
    const done = this.items.filter((it) => it.verdict).length;
    $("#audit-more").hidden = !(this.moreN && done === this.items.length);
    $("#audit-more-n").textContent = this.moreN;
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
    this.shownAt = performance.now(); this.hiddenMs = 0;
    $("#audit-meta").innerHTML = `Item ${this.idx + 1} of ${this.items.length} · ${esc(d.source)} · ${esc(d.type)} · ${esc(d.drawing_name)}` +
      (d.split && d.split !== "dev" ? `<span class="split-tag" title="reference answer made by our agents">harder · ${esc(d.recipe || d.split)}</span>` : "");
    $("#audit-ref").previousElementSibling.textContent = d.ref_label ? `Reference answer (${d.ref_label})` :
      d.batch ? "Reference answer" :
      d.split && d.split !== "dev" ? "Reference answer (made by our agents)" : "Reference answer (dataset)";
    if (d.batch_label) $("#audit-meta").innerHTML += ` <span class="split-tag">${esc(d.batch_label)}</span>`;
    $("#audit-question").textContent = d.question;
    $("#audit-answer").textContent = d.answer;
    $("#audit-answer").classList.toggle("long", String(d.answer).length > 30);
    $("#audit-ref").classList.toggle("long", String(d.reference).length > 30);
    $("#audit-conf").textContent = confWords(d.confidence);
    $("#audit-cost").textContent = costWords(d.cost);
    $("#audit-ref").textContent = d.reference ?? "none yet";
    $("#audit-match").textContent = d.reference == null ? "no reference: please judge from the drawing, and type the right answer below if you know it" :
      d.matches_reference === true ? "our answer matches it" :
      d.matches_reference === false ? "our answer differs" :
      d.text_match === true ? "free text: looks the same, please compare" :
      d.text_match === false ? "free text: looks different, please compare" : "free-text answer: please compare";
    renderNotes($("#audit-assumptions"), d.assumptions, d.missing);
    $("#audit-trace").innerHTML = d.trace.map((t) => `<li>${esc(t)}</li>`).join("");
    $("#audit-comment").value = ""; $("#audit-correct").value = "";
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
      const els = d.other_evidence.slice(0, 150).map((e) => `<li>${esc(e.note || "(no note)")}${e.ifc_guid ? ` <small>· ${esc(e.ifc_guid)}</small>` : ""}</li>`).join("");
      this.viewer.empty(d.path.endsWith(".ifc") ?
        `<div class="msg"><h3>This question is about a 3D building model (IFC), not a drawing.</h3>
         <div>Our evidence is the list of model elements below (${d.other_evidence.length}${d.other_evidence.length > 150 ? ", first 150 shown" : ""}).
         Each line is one element with its IFC GlobalId.</div>${els ? `<ol>${els}</ol>` : "<p>No elements were cited.</p>"}</div>` :
        `<div class="msg">No drawing to show for this question.</div>`);
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
    const comment = $("#audit-comment").value, correct_value = $("#audit-correct").value;
    // time to verify = item shown -> verdict, minus the time the page was hidden (another tab, laptop asleep)
    const seconds = this.shownAt ? Math.max(0, Math.round((performance.now() - this.shownAt - this.hiddenMs) / 100) / 10) : null;
    try {
      await api("api/audit", { method: "POST", body: JSON.stringify({ item_id: this.cur.item_id, verdict: v, comment, correct_value, seconds }) });
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
let hiddenSince = null;
document.addEventListener("visibilitychange", () => {
  if (document.hidden) hiddenSince = performance.now();
  else if (hiddenSince !== null) { audit.hiddenMs = (audit.hiddenMs || 0) + performance.now() - hiddenSince; hiddenSince = null; }
});
$("#audit-more-btn").addEventListener("click", async () => {
  try { const r = await api("api/audit/more", { method: "POST" }); flash(`${r.added} new items`); } catch (e) { alert(e.message); return; }
  await audit.init();
});
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
    measure.reset(v);
    if (this.dsPath !== path && !this.editQid) {
      $("#q-text").value = ""; $("#q-answer").value = ""; $("#q-method").value = "";
      this.loadDraft();
    }
    if (this.dsPath !== path) {
      this.dsPath = path;
      $("#ds-n").textContent = "…"; $("#ds-list").innerHTML = "";
      api(`api/dataset-questions?path=${encodeURIComponent(path)}`).then((d) => {
        $("#ds-n").textContent = d.n;
        $("#ds-list").innerHTML = d.questions.map((q) => `<li>${esc(q.question)} <small>→ ${esc(q.answer)}</small></li>`).join("") ||
          "<li>None: this drawing has no dataset questions yet.</li>";
      }).catch(() => { $("#ds-n").textContent = "?"; });
    }
  },
  async ask() {
    const question = $("#q-text").value.trim();
    if (!question) { alert("Please write a question first."); return; }
    const res = $("#q-result"); res.hidden = false; res.className = "result";
    res.innerHTML = `Our system is working on it… (usually a few seconds, up to a minute)`;
    $("#q-ask").disabled = true;
    try {
      const r = await api("api/ask", { method: "POST", body: JSON.stringify({ path: this.path, question }) });
      r.fresh = true;
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
  draftKey() { return this.path ? `wb-draft|${this.path}` : ""; },
  saveDraft() {
    if (!this.path || this.editQid) return;
    const d = { q: $("#q-text").value, a: $("#q-answer").value, u: $("#q-unit").value, t: $("#q-type").value, m: $("#q-method").value };
    try { if (d.q || d.a || d.m) localStorage.setItem(this.draftKey(), JSON.stringify(d)); else localStorage.removeItem(this.draftKey()); } catch {}
  },
  loadDraft() {
    let d = null;
    try { d = JSON.parse(localStorage.getItem(this.draftKey()) || "null"); } catch {}
    if (!d) return;
    $("#q-text").value = d.q || ""; $("#q-answer").value = d.a || ""; $("#q-method").value = d.m || "";
    if (d.t) $("#q-type").value = d.t;
    $("#q-unit").value = d.u ?? $("#q-unit").value;
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
      marks: this.viewer.marks, qid: this.editQid || "",
      // an old answer of ours only stays attached if the question text is unchanged (or she asked again)
      system: this.system && (this.system.fresh || !this.editQid || question === this.editOrigQ) ? this.system : null,
    };
    try {
      const r = await api("api/questions", { method: "POST", body: JSON.stringify(body) });
      flash(`Saved ✓ (${r.n} questions so far)`);
      this.edit(null);
      try { localStorage.removeItem(this.draftKey()); } catch {}
      $("#q-text").value = ""; $("#q-answer").value = ""; $("#q-method").value = "";
      this.system = null; $("#q-result").hidden = true;
      this.viewer.marks = []; this.viewer.boxes = []; this.viewer.draw();
      this.listMine();
    } catch (e) { alert(`Could not save: ${e.message}`); }
  },
  edit(q) {
    this.editQid = q ? q.qid : null;
    $("#q-save").textContent = q ? "Save changes" : "Save question";
    $("#q-editing").hidden = !q;
  },
  async listMine() {
    const r = await api("api/questions");
    this.mine = r.questions;
    $("#q-count").textContent = r.questions.length;
    $("#q-list").innerHTML = r.questions.map((q, i) => `<li><b>${esc(q.question)}</b> → ${esc(q.answer || "?")} ${esc(q.unit || "")}
      ${q.system ? `<small>(ours: ${esc(q.system.value)} ${esc(q.system.unit || "")}${q.agree === true ? " ✓ same" : q.agree === false ? " — <b>we disagree: a hard one!</b>" : ""})</small>` : ""}
      <button class="mini" data-edit="${i}">Edit</button><button class="mini" data-del="${i}">Delete</button></li>`).join("");
    $$("#q-list [data-edit]").forEach((b) => b.addEventListener("click", async () => {
      const q = this.mine[+b.dataset.edit];
      await this.open(q.path, q.page || 0);
      $("#q-text").value = q.question || ""; $("#q-answer").value = q.answer || ""; $("#q-unit").value = q.unit || "";
      if (q.type) $("#q-type").value = q.type;
      $("#q-method").value = q.method || "";
      const s = $(`input[name=sure][value="${q.sureness}"]`); if (s) s.checked = true;
      this.viewer.marks = (q.marks || []).slice(); this.viewer.drawMarks();
      this.edit(q);
      this.system = q.system ? { ok: true, ...q.system } : null;  // keep our earlier answer unless she asks again
      this.editOrigQ = q.question;
      $("#q-text").focus();
    }));
    $$("#q-list [data-del]").forEach((b) => b.addEventListener("click", async () => {
      const q = this.mine[+b.dataset.del];
      if (!confirm(`Delete this question?\n\n${q.question}`)) return;
      try { await api("api/questions/delete", { method: "POST", body: JSON.stringify({ qid: q.qid }) }); flash("Deleted"); }
      catch (e) { alert(`Could not delete: ${e.message}`); }
      if (this.editQid === q.qid) this.edit(null);
      this.listMine();
    }));
  },
};
$("#pick-search-btn").addEventListener("click", () => asker.groups($("#pick-search").value.trim()));
$("#pick-upload-btn").addEventListener("click", () => $("#pick-upload").click());
$("#pick-upload").addEventListener("change", async (e) => {
  const f = e.target.files[0]; e.target.value = "";
  if (!f) return;
  const msg = $("#pick-upload-msg"); msg.hidden = false; msg.textContent = `Uploading ${f.name}…`;
  let r;
  try {
    r = await api(`api/upload?name=${encodeURIComponent(f.name)}`, { method: "POST", body: f, headers: { "Content-Type": "application/octet-stream" } });
  } catch (err) { msg.textContent = `Could not add ${f.name}: ${err.message}`; return; }
  msg.textContent = `Added “${r.card.name}”. It is listed under “Added drawings”.`;
  await asker.groups();
  await asker.open(r.path);
});
$("#pick-search").addEventListener("keydown", (e) => { if (e.key === "Enter") asker.groups(e.target.value.trim()); });
$("#pick-reset").addEventListener("click", () => { $("#pick-search").value = ""; asker.groups(); });
$("#ask-change").addEventListener("click", () => { $("#asker").hidden = true; $("#picker").hidden = false; asker.edit(null); });
$("#q-cancel-edit").addEventListener("click", () => {
  asker.edit(null); $("#q-text").value = ""; $("#q-answer").value = ""; $("#q-method").value = "";
  asker.viewer.marks = []; asker.viewer.drawMarks();
});
$("#q-ask").addEventListener("click", () => asker.ask());
["#q-text", "#q-answer", "#q-unit", "#q-method", "#q-type"].forEach((s) => $(s).addEventListener("input", () => asker.saveDraft()));
$("#q-save").addEventListener("click", () => asker.save());
$("#ask-mark").addEventListener("click", (e) => {
  const on = !asker.viewer.marking;
  if (on && measure.mode) measure.setMode(measure.mode); asker.viewer.setMarking(on); e.target.classList.toggle("on", on);
  e.target.textContent = on ? "✎ Marking: drag a box (click to stop)" : "✎ Mark on drawing";
});
const DEFAULT_UNIT = { count: "count", area: "m2", length: "m", volume: "m3", ratio: "%", text: "" };
$("#q-type").addEventListener("change", (e) => { $("#q-unit").value = DEFAULT_UNIT[e.target.value] ?? ""; });
$("#ask-clear").addEventListener("click", () => { asker.viewer.marks = []; asker.viewer.drawMarks(); });

// Measuring tool (tab 2): scale from two clicks (or the printed 1:N scale of a vector PDF), then lengths/areas
const UNIT_RE = /^\s*([0-9]+(?:[.,][0-9]+)?)\s*(mm|cm|m|km|ft|feet|foot|in|inch|inches|'|")?\s*$/i;
const measure = {
  v: asker.viewer, mode: null, pts: [], hov: null, closed: false, scale: null, view: null,
  key() { return this.view ? `wb-scale|${this.view.path}|${this.view.page}` : ""; },
  reset(view) {
    this.view = view; this.mode = null; this.pts = []; this.closed = false; this.hov = null; this.scale = null;
    try { const s = localStorage.getItem(this.key()); if (s) this.scale = JSON.parse(s); } catch {}
    $("#m-printed").hidden = view.kind !== "vector";
    this.buttons(); this.render();
  },
  setMode(m) {
    if (this.v.marking) $("#ask-mark").click();
    this.mode = this.mode === m ? null : m; this.pts = []; this.closed = false; this.hov = null;
    if ((m === "length" || m === "area") && !this.scale && this.mode) {
      this.mode = "scale";
    }
    this.buttons(); this.render();
  },
  buttons() {
    $("#m-scale").classList.toggle("on", this.mode === "scale");
    $("#m-length").classList.toggle("on", this.mode === "length");
    $("#m-area").classList.toggle("on", this.mode === "area");
    this.v.el.classList.toggle("measuring", !!this.mode);
  },
  click(p) {
    if (!this.mode) return;
    if (this.mode === "scale") {
      this.pts.push(p);
      if (this.pts.length === 2) {
        const dpx = Math.hypot(this.pts[1].x - this.pts[0].x, this.pts[1].y - this.pts[0].y);
        const ans = prompt("How long is this in reality? (e.g. 5 m, 1200 mm, 10 ft)", "1 m");
        const m = ans && ans.match(UNIT_RE);
        if (m && dpx > 0) {
          const L = parseFloat(m[1].replace(",", ".")), u = this.normUnit(m[2] || "m");
          this.setScale({ k: L / dpx, unit: u, desc: `${L} ${u} over ${dpx.toFixed(0)} px (two clicks)` });
        } else if (ans !== null) alert("Please write a number and a unit, e.g. 5 m");
        this.mode = null; this.pts = [];
      }
    } else if (this.mode === "length") {
      this.pts.push(p);
    } else if (this.mode === "area") {
      if (this.closed) { this.pts = []; this.closed = false; }
      const f = this.pts[0];
      if (this.pts.length >= 3 && Math.hypot(p.x - f.x, p.y - f.y) * this.v.s < 12) this.closed = true;
      else this.pts.push(p);
    }
    this.buttons(); this.render();
  },
  normUnit(u) {
    u = u.toLowerCase();
    return { feet: "ft", foot: "ft", "'": "ft", inch: "in", inches: "in", '"': "in" }[u] || u;
  },
  setScale(sc) {
    this.scale = sc;
    try { localStorage.setItem(this.key(), JSON.stringify(sc)); } catch {}
  },
  printed() {
    const n = prompt("Printed scale 1 : N — what is N? (only valid if the PDF is to scale, e.g. 'Echelle 1:200' on an A3 sheet)", "100");
    const N = n && parseFloat(n.replace(",", "."));
    if (!N || !this.view || !this.view.zoom) return;
    // 1 PDF point = 0.3527778 mm on paper; the rendered image has `zoom` px per point
    this.setScale({ k: (0.3527778e-3 * N) / this.view.zoom, unit: "m", desc: `printed scale 1:${N} (PDF assumed to scale)` });
    this.buttons(); this.render();
  },
  value() {
    if (!this.scale || this.pts.length < 2) return null;
    const pts = this.hov && !this.closed && this.mode ? [...this.pts, this.hov] : this.pts;
    const k = this.scale.k, u = this.scale.unit;
    if (this.mode === "length" || (!this.mode && !this.closed && this.lastMode === "length")) {
      let d = 0;
      for (let i = 1; i < pts.length; i++) d += Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y);
      return { kind: "length", v: d * k, unit: u, n: pts.length };
    }
    if (this.mode === "area" && pts.length >= 3) {
      let a = 0;
      for (let i = 0; i < pts.length; i++) { const p = pts[i], q = pts[(i + 1) % pts.length]; a += p.x * q.y - q.x * p.y; }
      return { kind: "area", v: (Math.abs(a) / 2) * k * k, unit: `${u}2`, n: pts.length };
    }
    return null;
  },
  fmt(x) { return x >= 100 ? x.toFixed(1) : x >= 10 ? x.toFixed(2) : x.toFixed(3); },
  render(svg = this.v.svg) {
    $$(".measure", svg).forEach((g) => g.remove());
    const g = document.createElementNS(SVGNS, "g"); g.setAttribute("class", "measure");
    const pts = this.hov && !this.closed && this.mode && this.pts.length ? [...this.pts, this.hov] : this.pts;
    if (pts.length) {
      const el = document.createElementNS(SVGNS, this.mode === "area" && (this.closed || pts.length >= 3) ? "polygon" : "polyline");
      el.setAttribute("points", pts.map((p) => `${p.x},${p.y}`).join(" "));
      el.setAttribute("class", this.mode === "scale" ? "m-scale" : this.mode === "area" ? "m-poly" : "m-line");
      g.appendChild(el);
      this.pts.forEach((p) => { const c = document.createElementNS(SVGNS, "circle"); c.setAttribute("cx", p.x); c.setAttribute("cy", p.y); c.setAttribute("class", "m-pt"); g.appendChild(c); });
    }
    const val = this.value();
    if (val && pts.length) {
      const last = pts[pts.length - 1];
      const tx = document.createElementNS(SVGNS, "text"); tx.setAttribute("class", "m-lbl");
      tx.setAttribute("x", last.x); tx.setAttribute("y", last.y); tx.textContent = `${this.fmt(val.v)} ${val.unit}`;
      g.appendChild(tx);
    }
    svg.appendChild(g); this.zoom(1 / this.v.s);
    const out = $("#m-out");
    const sc = this.scale ? `scale: ${esc(this.scale.desc)}` : "no scale yet";
    if (this.mode === "scale") out.innerHTML = `Click both ends of a known dimension (${this.pts.length}/2). <small>${sc}</small>`;
    else if (val) out.innerHTML = `<b>${val.kind === "area" ? "Area" : "Length"}: ${this.fmt(val.v)} ${val.unit}</b> <small>(${val.n} points; ${sc})</small>`;
    else if (this.mode === "length") out.innerHTML = `Click points along the line. <small>${sc}</small>`;
    else if (this.mode === "area") out.innerHTML = `Click the corners; click the first corner again to close. <small>${sc}</small>`;
    else out.innerHTML = this.scale ? `<small>${sc}</small>` : "Set the scale first.";
    this.last = val && (this.closed || this.mode === "length") ? val : null;
    $("#m-use").hidden = !this.last;
  },
  zoom(k) {
    $$(".measure circle", this.v.svg).forEach((c) => c.setAttribute("r", 5 * k));
    $$(".measure text", this.v.svg).forEach((t) => { t.setAttribute("font-size", 16 * k); t.setAttribute("dx", 8 * k); t.setAttribute("dy", -8 * k); });
  },
  use() {
    this.hov = null;
    const val = this.value();
    if (!val) return;
    const line = `Measured ${val.kind}: ${this.fmt(val.v)} ${val.unit} (${val.n} points; ${this.scale.desc}).`;
    const m = $("#q-method"); m.value = (m.value.trim() ? m.value.trim() + "\n" : "") + line;
    if (!$("#q-answer").value.trim()) { $("#q-answer").value = this.fmt(val.v); $("#q-unit").value = val.unit; $("#q-type").value = val.kind; }
    flash("Added ✓");
  },
};
asker.viewer.onClick = (p) => measure.click(p);
asker.viewer.onHover = (p) => { if (measure.mode && measure.mode !== "scale" && measure.pts.length && !measure.closed) { measure.hov = p; measure.render(); } };
asker.viewer.onDraw = (svg) => measure.render(svg);
asker.viewer.onZoom = (k) => measure.zoom(k);
$("#m-scale").addEventListener("click", () => measure.setMode("scale"));
$("#m-length").addEventListener("click", () => measure.setMode("length"));
$("#m-area").addEventListener("click", () => measure.setMode("area"));
$("#m-printed").addEventListener("click", () => measure.printed());
$("#m-use").addEventListener("click", () => measure.use());
document.addEventListener("keydown", (e) => {
  if ($("#tab-ask").hidden || e.target.matches("textarea, input, select")) return;
  if (e.key === "Escape" && measure.mode) { measure.pts = []; measure.closed = false; measure.hov = null; measure.render(); }
  if (e.key === "Enter" && measure.mode === "area" && measure.pts.length >= 3) { measure.closed = true; measure.render(); }
});

// ---------------------------------------------------------------------------------------------------------
// Tab 3: rules
const rules = {
  async load() {
    const r = await api("api/rules");
    $("#rule-count").textContent = r.rules.length;
    $("#rule-checked-on").textContent = r.checked_on ? `Tested on ${r.checked_on}.` : "";
    const chk = (c) => {
      if (!c) return "";
      if (c.skip) return `<small>not testable (${esc(c.skip)})</small>`;
      if (!c.touched) return `<small>no matching question in our test set</small>`;
      const ex = (c.examples || []).map((e) => `<li>${esc(e.question.slice(0, 90))} → <b>${esc(e.value)} ${esc(e.unit || "")}</b> (reference ${esc(e.gold)})</li>`).join("");
      return `applies to ${c.touched} answers; <b>${c.flagged}</b> outside the range` +
        (c.flagged ? ` (${c.flagged_wrong} of them wrong)` : "") + (ex ? `<details><summary><small>examples</small></summary><ul class="small">${ex}</ul></details>` : "");
    };
    $("#rule-table tbody").innerHTML = r.rules.map((x) => `<tr><td>${esc(x.what || "—")}</td>
      <td>${x.min != null || x.max != null ? `${esc(x.min ?? "?")} – ${esc(x.max ?? "?")} ${esc(x.unit || "")}` : "—"}</td>
      <td>${esc(x.why || "")}${x.uncertainty ? `<br><i>${esc(x.uncertainty)}</i>` : ""}</td><td>${chk(x.check)}</td></tr>`).join("");
  },
};
$("#rule-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const body = Object.fromEntries(new FormData(e.target).entries());
  const lo = parseFloat(String(body.min).replace(",", ".")), hi = parseFloat(String(body.max).replace(",", "."));
  if (!isNaN(lo) && !isNaN(hi) && lo > hi && !confirm(`Min (${lo}) is larger than max (${hi}). Save anyway?`)) return;
  if ((body.min || body.max) && !body.unit && !confirm("No unit given, so this range cannot be tested against our answers. Save anyway?")) return;
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

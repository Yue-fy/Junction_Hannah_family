/**
 * 3D IFC viewer: web-ifc (geometry + properties, MPL-2.0, used unmodified) + three.js (MIT).
 *
 * Geometry is merged into one mesh per (storey, opaque|transparent) bucket with vertex colours, which keeps
 * draw calls low for 10k-element models. Each bucket remembers which triangle range belongs to which IFC
 * element (expressID), so we can pick, highlight and frame single elements. IfcSpace volumes are loaded
 * separately and only drawn when highlighted (areas are the most common IFC question).
 */
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import * as WebIFC from "web-ifc";
import wasmUrl from "web-ifc/web-ifc.wasm?url";

export interface Storey {
  id: number;
  name: string;
  elevation: number;
}

interface Range {
  start: number; // first index (in the bucket's index buffer)
  count: number; // number of indices
  id: number; // expressID
}

interface Bucket {
  key: string;
  storey: number;
  transparent: boolean;
  pos: number[];
  nrm: number[];
  col: number[];
  idx: number[];
  ranges: Range[];
  mesh?: THREE.Mesh;
}

let apiPromise: Promise<WebIFC.IfcAPI> | null = null;
function ifcApi(): Promise<WebIFC.IfcAPI> {
  apiPromise ??= (async () => {
    const api = new WebIFC.IfcAPI();
    await api.Init((p: string) => (p.endsWith(".wasm") ? wasmUrl : p), true);
    return api;
  })();
  return apiPromise;
}

const HL = new THREE.Color("#ff6a13");
/** Elements shown for contrast, not as the answer's evidence (e.g. same-kind fixtures a text answer leaves out). */
const HL2 = new THREE.Color("#7b4fd6");

export class Viewer3D {
  readonly el: HTMLElement;
  private renderer: THREE.WebGLRenderer;
  private scene = new THREE.Scene();
  private camera: THREE.PerspectiveCamera;
  private controls: OrbitControls;
  private root = new THREE.Group();
  private hlGroup = new THREE.Group();
  private buckets: Bucket[] = [];
  /** Floor height of each storey in world y (10th percentile of its vertices; IFC elevations are not in world units after COORDINATE_TO_ORIGIN). */
  private storeyBaseY = new Map<number, number>();
  /** With a storey filter: cut everything above the next storey's floor (elements a model assigns to a storey but places higher up). */
  private clipPlane = new THREE.Plane(new THREE.Vector3(0, -1, 0), 0);
  private spaceBuckets = new Map<number, Bucket>();
  private elementBuckets = new Map<number, { b: Bucket; r: Range }[]>();
  private api: WebIFC.IfcAPI | null = null;
  private modelID = -1;
  private guidToId = new Map<string, number>();
  private idToGuid = new Map<number, string>();
  storeys: Storey[] = [];
  private storeyOf = new Map<number, number>();
  private activeStorey: number | null = null;
  private ghost = false;
  file = "";
  onPick: (guid: string, label: string, props: Record<string, string>) => void = () => {};
  private loadToken = 0;
  private needsRender = true;
  private lastFramed: THREE.Object3D | null = null;
  /** Customer view: numbered pins 1…5 over the elements the answer lists (HTML labels, placed on every render). */
  private labels: { el: HTMLDivElement; p: THREE.Vector3 }[] = [];
  private labelLayer = document.createElement("div");

  constructor(el: HTMLElement) {
    this.el = el;
    el.classList.add("v3d");
    this.renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setClearColor(new THREE.Color("#eef1f5"));
    this.renderer.localClippingEnabled = true;
    el.append(this.renderer.domElement);
    this.camera = new THREE.PerspectiveCamera(45, 1, 0.1, 5000);
    this.camera.position.set(30, 30, 30);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.addEventListener("change", () => (this.needsRender = true));
    // once the visitor orbits/zooms, a pane resize keeps their view; until then it re-fits the last framing
    this.controls.addEventListener("start", () => (this.lastFramed = null));
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x8899aa, 2.2));
    const sun = new THREE.DirectionalLight(0xffffff, 1.6);
    sun.position.set(50, 100, 30);
    this.scene.add(sun, this.root, this.hlGroup);
    new ResizeObserver(() => this.resize()).observe(el);
    this.installPick();
    const loop = () => {
      requestAnimationFrame(loop);
      this.controls.update();
      if (this.needsRender) {
        this.renderer.render(this.scene, this.camera);
        this.needsRender = false;
        this.placeLabels();
      }
    };
    loop();
  }

  /** Number these elements 1 2 3 … (GlobalIds in the order of the answer's list; '' = no element for that number); [] clears. */
  setNumbers(guids: string[]) {
    this.setNumberGroups(guids.map((g) => (g ? [g] : [])));
  }

  /** One number per group of elements (e.g. one per floor), placed over the centre of the group's top. */
  setNumberGroups(groups: string[][]) {
    this.ensureGuidIndex();
    for (const l of this.labels) l.el.remove();
    this.labels = [];
    if (!this.labelLayer.isConnected) {
      this.labelLayer.className = "v3d-labels";
      this.el.append(this.labelLayer);
    }
    const mat = new THREE.MeshBasicMaterial();
    groups.forEach((gs, k) => {
      // an empty group = a numbered item without a GlobalId (a 2D box only): its number stays free
      const box = this.boxOf(gs, mat);
      if (box.isEmpty()) return;
      const p = box.getCenter(new THREE.Vector3());
      p.y = box.max.y;
      const el = document.createElement("div");
      el.className = "v3d-num pin-badge";
      el.textContent = String(k + 1);
      this.labelLayer.append(el);
      this.labels.push({ el, p });
    });
    mat.dispose();
    this.needsRender = true;
  }

  private boxOf(guids: string[], mat: THREE.Material) {
    this.ensureGuidIndex();
    const box = new THREE.Box3();
    for (const g of guids) {
      const id = this.guidToId.get(g);
      const m = id === undefined ? null : this.elementMesh(id, mat);
      if (!m) continue;
      box.union(new THREE.Box3().setFromObject(m));
      m.geometry.dispose();
    }
    return box;
  }

  /** Show one storey and frame these elements on it (customer view: a floor row of a whole-building answer). */
  focusGuids(guids: string[], storey: number | null) {
    this.ensureGuidIndex();
    this.setStorey(storey);
    const mat = new THREE.MeshBasicMaterial();
    const g = new THREE.Group();
    for (const guid of guids) {
      const id = this.guidToId.get(guid);
      const m = id === undefined ? null : this.elementMesh(id, mat);
      if (m) g.add(m);
    }
    // frame() samples the vertices (kept in JS memory after dispose) and re-fits on resize until the visitor orbits
    if (g.children.length) this.frame(g);
    for (const m of g.children) (m as THREE.Mesh).geometry.dispose();
    mat.dispose();
  }

  private placeLabels() {
    if (!this.labels.length) return;
    const w = this.renderer.domElement.clientWidth, h = this.renderer.domElement.clientHeight;
    for (const l of this.labels) {
      const v = l.p.clone().project(this.camera);
      const vis = v.z < 1 && Math.abs(v.x) <= 1.02 && Math.abs(v.y) <= 1.02;
      l.el.style.display = vis ? "" : "none";
      if (vis) l.el.style.transform = `translate(${((v.x + 1) / 2) * w}px, ${((1 - v.y) / 2) * h}px) translate(-50%, -110%)`;
    }
  }

  private resize() {
    const w = this.el.clientWidth;
    const h = this.el.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false);
    this.renderer.domElement.style.width = "100%";
    this.renderer.domElement.style.height = "100%";
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    if (this.lastFramed) this.frame(this.lastFramed);
    this.needsRender = true;
  }

  async load(file: string, url: string, onProgress: (msg: string) => void = () => {}): Promise<void> {
    if (file === this.file && this.modelID >= 0) return;
    const token = ++this.loadToken;
    this.clear();
    this.file = file;
    this.el.dataset.state = "loading";
    onProgress("downloading model…");
    const resp = await fetch(url);
    const total = Number(resp.headers.get("content-length") ?? 0);
    const reader = resp.body!.getReader();
    const chunks: Uint8Array[] = [];
    let got = 0;
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      got += value.length;
      onProgress(`downloading model… ${(got / 1e6).toFixed(1)}${total ? ` / ${(total / 1e6).toFixed(1)}` : ""} MB`);
    }
    const data = new Uint8Array(got);
    let off = 0;
    for (const c of chunks) {
      data.set(c, off);
      off += c.length;
    }
    onProgress("parsing IFC (web-ifc)…");
    await new Promise((r) => setTimeout(r, 30));
    const api = await ifcApi();
    if (token !== this.loadToken) return;
    this.api = api;
    this.modelID = api.OpenModel(data, { COORDINATE_TO_ORIGIN: true });
    this.readSpatialStructure();
    onProgress("building geometry…");
    await new Promise((r) => setTimeout(r, 30));
    const byKey = new Map<string, Bucket>();
    api.StreamAllMeshes(this.modelID, (mesh) => this.addMesh(mesh, (id, transparent) => {
      const storey = this.storeyOf.get(id) ?? -1;
      const key = `${storey}:${transparent ? "t" : "o"}`;
      let b = byKey.get(key);
      if (!b) {
        b = { key, storey, transparent, pos: [], nrm: [], col: [], idx: [], ranges: [] };
        byKey.set(key, b);
      }
      return b;
    }));
    api.StreamAllMeshesWithTypes(this.modelID, [WebIFC.IFCSPACE], (mesh) => this.addMesh(mesh, (id) => {
      let b = this.spaceBuckets.get(id);
      if (!b) {
        b = { key: `space:${id}`, storey: this.storeyOf.get(id) ?? -1, transparent: true, pos: [], nrm: [], col: [], idx: [], ranges: [] };
        this.spaceBuckets.set(id, b);
      }
      return b;
    }));
    if (token !== this.loadToken) return;
    this.buckets = [...byKey.values()];
    for (const b of this.buckets) {
      b.mesh = this.toMesh(b, new THREE.MeshLambertMaterial({
        vertexColors: true, transparent: b.transparent, opacity: b.transparent ? 0.35 : 1, side: THREE.DoubleSide,
        depthWrite: !b.transparent,
      }));
      b.mesh.userData.bucket = b;
      this.root.add(b.mesh);
    }
    this.computeStoreyBases();
    this.frame(this.root);
    this.el.dataset.state = "ready";
    onProgress("");
  }

  private clear() {
    for (const o of [...this.root.children, ...this.hlGroup.children]) {
      const m = o as THREE.Mesh;
      m.geometry?.dispose();
      (m.material as THREE.Material)?.dispose?.();
    }
    this.root.clear();
    this.hlGroup.clear();
    this.buckets = [];
    this.spaceBuckets.clear();
    this.elementBuckets.clear();
    this.guidToId.clear();
    this.idToGuid.clear();
    this.storeyOf.clear();
    this.storeys = [];
    this.activeStorey = null;
    if (this.api && this.modelID >= 0) this.api.CloseModel(this.modelID);
    this.modelID = -1;
    this.file = "";
    this.needsRender = true;
  }

  private readSpatialStructure() {
    const api = this.api!;
    const m = this.modelID;
    const ids = api.GetLineIDsWithType(m, WebIFC.IFCBUILDINGSTOREY);
    const storeyIds = new Set<number>();
    for (let i = 0; i < ids.size(); i++) {
      const s = api.GetLine(m, ids.get(i));
      storeyIds.add(s.expressID);
      this.storeys.push({ id: s.expressID, name: s.Name?.value ?? `storey ${i + 1}`, elevation: Number(s.Elevation?.value ?? 0) });
    }
    this.storeys.sort((a, b) => a.elevation - b.elevation);
    // child → parent (containment and aggregation), then walk up to a storey
    const parent = new Map<number, number>();
    const rels = api.GetLineIDsWithType(m, WebIFC.IFCRELCONTAINEDINSPATIALSTRUCTURE);
    for (let i = 0; i < rels.size(); i++) {
      const r = api.GetLine(m, rels.get(i));
      for (const e of r.RelatedElements ?? []) parent.set(e.value, r.RelatingStructure.value);
    }
    const aggs = api.GetLineIDsWithType(m, WebIFC.IFCRELAGGREGATES);
    for (let i = 0; i < aggs.size(); i++) {
      const r = api.GetLine(m, aggs.get(i));
      for (const e of r.RelatedObjects ?? []) if (!parent.has(e.value)) parent.set(e.value, r.RelatingObject.value);
    }
    const fills = api.GetLineIDsWithType(m, WebIFC.IFCRELFILLSELEMENT);
    const voids = new Map<number, number>();
    const vrels = api.GetLineIDsWithType(m, WebIFC.IFCRELVOIDSELEMENT);
    for (let i = 0; i < vrels.size(); i++) {
      const r = api.GetLine(m, vrels.get(i));
      voids.set(r.RelatedOpeningElement.value, r.RelatingBuildingElement.value);
    }
    for (let i = 0; i < fills.size(); i++) {
      const r = api.GetLine(m, fills.get(i));
      const host = voids.get(r.RelatingOpeningElement.value);
      if (host !== undefined && !parent.has(r.RelatedBuildingElement.value)) parent.set(r.RelatedBuildingElement.value, host);
    }
    const resolve = (id: number): number => {
      let cur: number | undefined = id;
      for (let k = 0; k < 12 && cur !== undefined; k++) {
        if (storeyIds.has(cur)) return cur;
        cur = parent.get(cur);
      }
      return -1;
    };
    for (const id of parent.keys()) this.storeyOf.set(id, resolve(id));
  }

  private addMesh(mesh: WebIFC.FlatMesh, bucketFor: (id: number, transparent: boolean) => Bucket) {
    const api = this.api!;
    const id = mesh.expressID;
    const n = mesh.geometries.size();
    for (let i = 0; i < n; i++) {
      const pg = mesh.geometries.get(i);
      const geom = api.GetGeometry(this.modelID, pg.geometryExpressID);
      const v = api.GetVertexArray(geom.GetVertexData(), geom.GetVertexDataSize());
      const ix = api.GetIndexArray(geom.GetIndexData(), geom.GetIndexDataSize());
      const t = pg.flatTransformation;
      const b = bucketFor(id, pg.color.w < 0.99);
      const base = b.pos.length / 3;
      const start = b.idx.length;
      for (let k = 0; k < v.length; k += 6) {
        const x = v[k], y = v[k + 1], z = v[k + 2];
        b.pos.push(t[0] * x + t[4] * y + t[8] * z + t[12], t[1] * x + t[5] * y + t[9] * z + t[13], t[2] * x + t[6] * y + t[10] * z + t[14]);
        const nx = v[k + 3], ny = v[k + 4], nz = v[k + 5];
        b.nrm.push(t[0] * nx + t[4] * ny + t[8] * nz, t[1] * nx + t[5] * ny + t[9] * nz, t[2] * nx + t[6] * ny + t[10] * nz);
        b.col.push(pg.color.x, pg.color.y, pg.color.z);
      }
      for (let k = 0; k < ix.length; k++) b.idx.push(ix[k] + base);
      const r = { start, count: ix.length, id };
      b.ranges.push(r);
      const list = this.elementBuckets.get(id) ?? [];
      list.push({ b, r });
      this.elementBuckets.set(id, list);
      geom.delete();
    }
  }

  private computeStoreyBases() {
    this.storeyBaseY.clear();
    const ys = new Map<number, number[]>();
    for (const b of this.buckets) {
      if (b.storey < 0 || b.transparent) continue;
      const l = ys.get(b.storey) ?? [];
      const step = Math.max(3, Math.floor(b.pos.length / 3 / 4000) * 3); // sample ≤ ~4k vertices per bucket
      for (let i = 1; i < b.pos.length; i += step) l.push(b.pos[i]);
      ys.set(b.storey, l);
    }
    for (const [id, l] of ys) {
      if (l.length < 20) continue;
      l.sort((a, c) => a - c);
      this.storeyBaseY.set(id, l[Math.floor(l.length * 0.1)]);
    }
  }

  /** World y where the active storey ends: the floor of the next storey above that has geometry. */
  private clipHeight(): number | null {
    if (this.activeStorey === null) return null;
    const base = this.storeyBaseY.get(this.activeStorey);
    if (base === undefined) return null;
    const i = this.storeys.findIndex((s) => s.id === this.activeStorey);
    for (const s of this.storeys.slice(i + 1)) {
      const nb = this.storeyBaseY.get(s.id);
      if (nb !== undefined && nb > base) return nb;
    }
    return null;
  }

  private toMesh(b: Bucket, mat: THREE.Material): THREE.Mesh {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(b.pos, 3));
    g.setAttribute("normal", new THREE.Float32BufferAttribute(b.nrm, 3));
    g.setAttribute("color", new THREE.Float32BufferAttribute(b.col, 3));
    g.setIndex(b.idx);
    g.computeBoundingBox();
    g.computeBoundingSphere();
    return new THREE.Mesh(g, mat);
  }

  /** Sub-geometry of one element (or space) as a standalone mesh, for highlights. */
  private elementMesh(id: number, mat: THREE.Material): THREE.Mesh | null {
    const parts = this.elementBuckets.get(id);
    if (!parts?.length) return null;
    const pos: number[] = [];
    const idx: number[] = [];
    const remap = new Map<string, number>();
    for (const { b, r } of parts) {
      for (let k = r.start; k < r.start + r.count; k++) {
        const vi = b.idx[k];
        const key = `${b.key}:${vi}`;
        let ni = remap.get(key);
        if (ni === undefined) {
          ni = pos.length / 3;
          pos.push(b.pos[vi * 3], b.pos[vi * 3 + 1], b.pos[vi * 3 + 2]);
          remap.set(key, ni);
        }
        idx.push(ni);
      }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    g.setIndex(idx);
    g.computeVertexNormals();
    g.computeBoundingBox();
    const mesh = new THREE.Mesh(g, mat);
    mesh.renderOrder = 10;
    mesh.userData.expressID = id;
    return mesh;
  }

  private ensureGuidIndex() {
    if (this.guidToId.size || !this.api) return;
    for (const id of [...this.elementBuckets.keys()]) {
      try {
        const line = this.api.GetLine(this.modelID, id);
        const gid = line.GlobalId?.value;
        if (gid) {
          this.guidToId.set(gid, id);
          this.idToGuid.set(id, gid);
        }
      } catch {
        /* skip */
      }
    }
    for (const s of this.storeys) {
      const gid = this.api.GetLine(this.modelID, s.id).GlobalId?.value;
      if (gid) {
        this.guidToId.set(gid, s.id);
        this.idToGuid.set(s.id, gid);
      }
    }
  }

  hasGuid(guid: string) {
    this.ensureGuidIndex();
    return this.guidToId.has(guid);
  }

  /** Highlight elements by GlobalId; returns how many were found. Storey GUIDs select that storey. */
  highlight(guids: string[], frame = true, contrast: Set<string> = new Set()): number {
    this.ensureGuidIndex();
    for (const o of this.hlGroup.children) (o as THREE.Mesh).geometry.dispose();
    this.hlGroup.clear();
    let found = 0;
    const mat = new THREE.MeshLambertMaterial({ color: HL, emissive: HL, emissiveIntensity: 0.35, transparent: true, opacity: 0.92,
      side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2, depthTest: true });
    const spaceMat = new THREE.MeshLambertMaterial({ color: HL, emissive: HL, emissiveIntensity: 0.4, transparent: true, opacity: 0.55,
      side: THREE.DoubleSide, depthWrite: false });
    const mat2 = new THREE.MeshLambertMaterial({ color: HL2, emissive: HL2, emissiveIntensity: 0.35, transparent: true, opacity: 0.92,
      side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2, depthTest: true });
    for (const gid of guids) {
      const id = this.guidToId.get(gid);
      if (id === undefined) continue;
      if (this.storeys.some((s) => s.id === id)) continue; // storey context, not an element
      const isSpace = this.spaceBuckets.has(id);
      const m = this.elementMesh(id, isSpace ? spaceMat : contrast.has(gid) ? mat2 : mat);
      if (m) {
        this.hlGroup.add(m);
        found++;
      }
    }
    this.setGhost(found > 0);
    if (found && frame) this.frame(this.hlGroup);
    this.needsRender = true;
    return found;
  }

  storeyOfGuid(guid: string): number | null {
    this.ensureGuidIndex();
    const id = this.guidToId.get(guid);
    if (id === undefined) return null;
    if (this.storeys.some((s) => s.id === id)) return id;
    const s = this.storeyOf.get(id);
    return s !== undefined && s >= 0 ? s : null;
  }

  isStoreyGuid(guid: string) {
    this.ensureGuidIndex();
    const id = this.guidToId.get(guid);
    return id !== undefined && this.storeys.some((s) => s.id === id);
  }

  focusGuid(guid: string) {
    const n = this.highlight([guid], true);
    return n > 0;
  }

  /** Show one storey (others faded); null shows all. */
  setStorey(id: number | null) {
    this.activeStorey = id;
    this.updateMaterials();
  }

  private setGhost(on: boolean) {
    this.ghost = on;
    this.updateMaterials();
  }

  private updateMaterials() {
    const clipY = this.clipHeight();
    if (clipY !== null) this.clipPlane.constant = clipY;
    for (const b of this.buckets) {
      const mat = b.mesh!.material as THREE.MeshLambertMaterial;
      mat.clippingPlanes = clipY !== null && b.storey === this.activeStorey ? [this.clipPlane] : null;
      const other = this.activeStorey !== null && b.storey !== this.activeStorey;
      let opacity = b.transparent ? 0.35 : 1;
      if (other) opacity = 0.06;
      else if (this.ghost) opacity = b.transparent ? 0.15 : 0.32;
      mat.opacity = opacity;
      mat.transparent = opacity < 1;
      mat.depthWrite = opacity === 1;
      mat.needsUpdate = true;
      // with a storey filter: hide storeys above it and elements without a storey (roof proxies, annotations)
      b.mesh!.visible = !(other && ((b.storey > -1 && this.storeyAbove(b.storey)) || b.storey === -1));
    }
    this.needsRender = true;
  }

  /** Hide storeys above the active one so the plan view is unobstructed. */
  private storeyAbove(id: number) {
    const a = this.storeys.find((s) => s.id === this.activeStorey);
    const s = this.storeys.find((x) => x.id === id);
    return !!a && !!s && s.elevation > a.elevation;
  }

  frame(obj: THREE.Object3D) {
    const box = new THREE.Box3().setFromObject(obj);
    if (box.isEmpty()) return;
    this.lastFramed = obj;
    const c = box.getCenter(new THREE.Vector3());
    // a single door or window is shown with ~3 m of its surroundings
    box.expandByVector(new THREE.Vector3(3, 3, 3).sub(box.getSize(new THREE.Vector3()).multiplyScalar(0.5)).max(new THREE.Vector3()));
    const dir = new THREE.Vector3(0.6, 0.75, 0.9).normalize();
    // exact fit: the closest camera distance along `dir` that keeps the elements inside the view (+ margin), so the lit
    // elements fill the pane instead of a sphere around the box diagonal
    const fwd = dir.clone().negate();
    const right = fwd.clone().cross(new THREE.Vector3(0, 1, 0)).normalize();
    const up = right.clone().cross(fwd);
    const tanV = Math.tan((this.camera.fov * Math.PI) / 360);
    const tanH = tanV * (this.camera.aspect || 1);
    const margin = obj === this.root ? 1.08 : 1.25;
    // fit on the geometry itself (sampled vertices, ≤ ~20k), not on the axis-aligned box: a building rotated on its
    // site has empty box corners that would leave the lit part small; the expanded box's corners keep the minimum size
    const pts: THREE.Vector3[] = [];
    for (const x of [box.min.x, box.max.x]) for (const y of [box.min.y, box.max.y]) for (const z of [box.min.z, box.max.z]) pts.push(new THREE.Vector3(x, y, z));
    const small = box.getSize(new THREE.Vector3()).length() <= Math.sqrt(3) * 6 + 0.01;
    if (!small) {
      pts.length = 0;
      const meshes: THREE.Mesh[] = [];
      obj.updateMatrixWorld(true);
      obj.traverse((o) => { const m = o as THREE.Mesh; if (m.isMesh && m.visible && m.geometry?.attributes?.position) meshes.push(m); });
      const total = meshes.reduce((n, m) => n + m.geometry.attributes.position.count, 0);
      const step = Math.max(1, Math.ceil(total / 20000));
      for (const m of meshes) {
        const pos = m.geometry.attributes.position as THREE.BufferAttribute;
        for (let i = 0; i < pos.count; i += step) pts.push(new THREE.Vector3().fromBufferAttribute(pos, i).applyMatrix4(m.matrixWorld));
      }
      if (!pts.length) for (const x of [box.min.x, box.max.x]) for (const y of [box.min.y, box.max.y]) for (const z of [box.min.z, box.max.z]) pts.push(new THREE.Vector3(x, y, z));
    }
    // centre the view on the points' extent in the camera's own axes, then back off until all of them fit
    let [r0, r1, u0, u1] = [Infinity, -Infinity, Infinity, -Infinity];
    for (const p of pts) {
      const v = p.clone().sub(c);
      const a = v.dot(right), b = v.dot(up);
      r0 = Math.min(r0, a); r1 = Math.max(r1, a); u0 = Math.min(u0, b); u1 = Math.max(u1, b);
    }
    c.addScaledVector(right, (r0 + r1) / 2).addScaledVector(up, (u0 + u1) / 2);
    let dist = 0;
    for (const p of pts) {
      const v = p.clone().sub(c);
      const depth = v.dot(fwd);
      dist = Math.max(dist, (Math.abs(v.dot(right)) * margin) / tanH - depth, (Math.abs(v.dot(up)) * margin) / tanV - depth);
    }
    this.camera.position.copy(c).addScaledVector(dir, dist);
    this.camera.near = Math.max(dist / 1000, 0.01);
    this.camera.far = dist * 20 + box.getSize(new THREE.Vector3()).length() * 4;
    this.camera.updateProjectionMatrix();
    this.controls.target.copy(c);
    this.controls.update();
    this.needsRender = true;
  }

  frameAll() {
    this.frame(this.root);
  }

  private installPick() {
    const ray = new THREE.Raycaster();
    let down = { x: 0, y: 0 };
    this.renderer.domElement.addEventListener("pointerdown", (e) => (down = { x: e.clientX, y: e.clientY }));
    this.renderer.domElement.addEventListener("pointerup", (e) => {
      if (Math.abs(e.clientX - down.x) + Math.abs(e.clientY - down.y) > 4 || !this.api) return;
      const r = this.renderer.domElement.getBoundingClientRect();
      ray.setFromCamera(new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), this.camera);
      const targets = this.buckets.filter((b) => b.mesh!.visible && (b.mesh!.material as THREE.Material).opacity > 0.1).map((b) => b.mesh!);
      const hit = ray.intersectObjects(targets, false)[0];
      if (!hit || hit.faceIndex == null) return;
      const b = hit.object.userData.bucket as Bucket;
      const tri = hit.faceIndex * 3;
      const range = b.ranges.find((x) => tri >= x.start && tri < x.start + x.count);
      if (!range) return;
      this.ensureGuidIndex();
      const line = this.api.GetLine(this.modelID, range.id);
      const type = this.api.GetNameFromTypeCode(line.type) ?? "";
      const props: Record<string, string> = {
        type, name: line.Name?.value ?? "", GlobalId: line.GlobalId?.value ?? "",
        storey: this.storeys.find((s) => s.id === this.storeyOf.get(range.id))?.name ?? "",
      };
      if (line.ObjectType?.value) props.objectType = line.ObjectType.value;
      if (line.Tag?.value) props.tag = line.Tag.value;
      this.highlight([props.GlobalId], false);
      this.onPick(props.GlobalId, `${type.replace(/^IFC/i, "")} ${props.name}`.trim(), props);
    });
  }

  /** Type, names and storey of one element (for follow-up questions about a picked element). */
  info(guid: string): { type: string; name: string; longName: string; storey: string } | null {
    this.ensureGuidIndex();
    const id = this.guidToId.get(guid);
    if (id === undefined || !this.api) return null;
    const l = this.api.GetLine(this.modelID, id);
    return {
      type: this.api.GetNameFromTypeCode(l.type) ?? "", name: l.Name?.value ?? "", longName: l.LongName?.value ?? "",
      storey: this.storeys.find((s) => s.id === this.storeyOf.get(id))?.name ?? "",
    };
  }

  /** Element types a free-text answer names ("Toilet-Domestic-3D: 9 units"), found in the loaded model by name: Revit
   * "Family:Type:Type:id" names give the family and "Family:Type"; ObjectType too. Per named type: its elements and the
   * number the text puts right after the name (null when it gives none). Generic class words alone never match. */
  findNamed(text: string, question = ""): { name: string; guids: string[]; said: number | null; missed?: boolean }[] {
    this.ensureGuidIndex();
    const api = this.api;
    if (!api || !text) return [];
    const families = new Map<string, Set<string>>();
    const GENERIC = /^(ifc\w*|walls?|doors?|windows?|floors?|roofs?|slabs?|columns?|beams?|stairs?|railings?|spaces?|rooms?|default|generic|level \d+|none|unnamed)$/i;
    const lower = text.toLowerCase();
    const byName = new Map<string, Set<string>>();
    for (const id of this.elementBuckets.keys()) {
      const gid = this.idToGuid.get(id);
      if (!gid || this.spaceBuckets.has(id)) continue;
      let l: { Name?: { value?: string }; ObjectType?: { value?: string } };
      try {
        l = api.GetLine(this.modelID, id);
      } catch {
        continue;
      }
      const name = String(l.Name?.value ?? "");
      const segs = name.split(":").map((x) => x.trim()).filter(Boolean);
      if (segs[0]) (families.get(segs[0]) ?? families.set(segs[0], new Set()).get(segs[0])!).add(gid);
      const cands = new Set([segs[0], segs.length > 2 ? `${segs[0]}:${segs[1]}` : "", String(l.ObjectType?.value ?? "").trim()]);
      for (const c of cands) {
        if (!c || c.length < 5 || GENERIC.test(c) || /^\d+$/.test(c) || !lower.includes(c.toLowerCase())) continue;
        if (!byName.has(c)) byName.set(c, new Set());
        byName.get(c)!.add(gid);
      }
    }
    // keep the most specific name per element ("Sink Vanity-Round:19\" x 19\"" over "Sink Vanity-Round")
    const names = [...byName.keys()].sort((a, b) => b.length - a.length);
    const taken = new Set<string>();
    const out: { name: string; guids: string[]; said: number | null; missed?: boolean }[] = [];
    for (const n of names) {
      const guids = [...byName.get(n)!].filter((g) => !taken.has(g));
      if (!guids.length) continue;
      guids.forEach((g) => taken.add(g));
      const esc = n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      // the count after the name, skipping a size in the type name ('Sink Vanity-Round:19" (6)', '42" x 19" (2)')
      const m = text.match(new RegExp(`${esc}[^\\n]{0,30}?(?<![\\d.,])(?<!x\\s?)(\\d+)(?![\\d.,]*\\s*(mm|cm|m\\b|m²|m2|"|''|in\\b|ft|x\\s*\\d))`, "i"));
      out.push({ name: n, guids, said: m ? Number(m[1]) : null });
    }
    // Omissions: when the named types are fixtures of one kind (sanitary, furniture, lighting), other families of that
    // kind in the model that the answer does not name ("Sink Vanity-Round ×6" next to toilets and urinals).
    // A kind is checked when the answer names one of its families or the QUESTION asks about it ("plumbing fixtures"),
    // so an answer that names none ("no plumbing fixtures are listed") is still checked against the model.
    const KINDS: [RegExp, RegExp][] = [
      [/toilet|\bwc\b|urinal|sink|basin|lavatory|shower|bath|tub\b|bidet|faucet|\btap\b|water closet/i,
        /plumbing|sanitary|toilets?\b|urinals?|sinks?\b|wash ?basins?|lavator/i],
      [/chair|table|desk|\bbed\b|sofa|couch|cabinet|shelf|shelving|wardrobe|bench|cubicle|work ?station/i, /furniture|furnishing/i],
      [/light|lamp|luminaire/i, /light(ing)? fixtures?|lamps?\b|luminaires?|lighting/i]];
    for (const [k, q] of KINDS) {
      // a question about rooms/spaces ("which rooms have a toilet?") is not a question about the fixtures themselves
      if (!out.some((o) => k.test(o.name)) && (!q.test(question) || /\b(rooms?|spaces?|zones?)\b/i.test(question))) continue;
      for (const [fam, gs] of families) {
        if (!k.test(fam) || out.some((o) => o.name.startsWith(fam) || fam.startsWith(o.name))) continue;
        const guids = [...gs].filter((g) => !taken.has(g));
        if (guids.length) out.push({ name: fam, guids, said: null, missed: true });
      }
    }
    return out.slice(0, 16);
  }

  /** Name lookup for evidence labels (e.g. "IfcSpace 119 KORIDOR"). */
  describe(guid: string): string {
    this.ensureGuidIndex();
    const id = this.guidToId.get(guid);
    if (id === undefined || !this.api) return guid;
    const l = this.api.GetLine(this.modelID, id);
    return `${this.api.GetNameFromTypeCode(l.type) ?? ""} ${l.Name?.value ?? ""} ${l.LongName?.value ?? ""}`.trim();
  }
}

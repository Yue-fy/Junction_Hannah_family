// Mirrors stoa/contract.py and docs/CONTRACT.md (keep in sync; additive changes only).

export type BBoxSpace = "pdf_pt" | "image_px";

export interface Evidence {
  file: string;
  page?: number | null;
  bbox?: [number, number, number, number] | number[] | null;
  bbox_space?: BBoxSpace | null;
  ifc_guid?: string | null;
  note?: string;
}

export interface Cost {
  llm_tokens_in?: number;
  llm_tokens_out?: number;
  gpu_seconds?: number;
  api_calls?: number;
  api_tokens_in?: number;
  api_tokens_out?: number;
  llm_calls?: number;
  wall_seconds?: number;
  [k: string]: number | undefined;
}

export interface Answer {
  /** set by the web middleware when a hosted call timed out and its recorded answer is shown instead */
  replayed?: string;
  recorded_at?: string;
  value: number | string | boolean | null; // boolean: a Python bool from a solver (shown yes/no)
  unit: string | null;
  confidence: number;
  evidence: Evidence[];
  trace: string[];
  solver: string;
  assumptions?: string[];
  missing?: string[];
  cost?: Cost;
  // Additive fields from stoa.api /ask (W4, CONTRACT D6): how the question was parsed, the sub-question plan
  // for compound questions, and whether the answer came from the API's cache.
  intent?: Intent | null;
  plan?: { op: string; parts: string[]; sub_questions: string[] } | null;
  cached?: boolean;
  /** web only (set in main.ts, never from the API): the element types a free-text answer about an .ifc names,
   *  counted in the loaded model in the browser. said = the count the answer gives (null: named without a count);
   *  notInAnswer = a type of the same kind the answer leaves out. */
  checked?: { name: string; model: number; said: number | null; notInAnswer?: boolean }[];
}

export interface Intent {
  task: string; // count | area | length | volume | text | …
  target: string;
  scope: string; // drawing | storey | model | room | apartment | …
  unit?: string | null;
  filters?: Record<string, string | number | boolean | null>;
  lang?: string;
  key?: string;
}

export interface FileInfo {
  path: string;
  source: string;
  ext: string;
  siblings: Record<string, string>;
  n_questions: number;
  license: string;
  credit: string;
  title?: string;
  source_url?: string;
  /** uploads: the drawing style the visitor declared or the image was guessed as ("cubicasa5k" = Nordic apartment plan), "" = any */
  style?: string;
  /** uploads: R2's style guess from the image content (only "cubicasa5k" at p >= 0.8 changes how it is read) */
  style_guess?: { style: string; p: number };
  /** uploads: the files uploaded together with this one (one folder: a sheet + its IFC model link up) */
  set?: string[];
}

export interface ExampleQuestion {
  question: string;
  type: string;
  unit: string | null;
  has_fixture?: boolean;
}

// GET /kg?path= → W1's `stoa.kg.links(path)` (night-W1 stoa/kg/graph.py). Everything but path/source is optional.
export interface KgFile {
  path: string;
  kind: string; // model | discipline-model | plan | section | elevation | sibling | floor | sheet
  storey?: string | null; // storey GlobalId (ifc_models plans)
  svg?: string;
  relation?: string; // only from the directory-based fallback
  label?: string; // historical sheets: the view named in the source's title ("West Elevation", "sheet 2 of 4")
}

export interface KgStorey {
  guid: string;
  name: string;
  elevation: number;
  plan: string | null;
  model_counts?: Record<string, number>;
  drawn_counts?: Record<string, number>;
  plan_scale?: string;
}

export interface KgRoom {
  // ifc_models
  guid?: string;
  name?: string;
  long_name?: string;
  storey?: string;
  storey_name?: string;
  area_m2?: number;
  plan?: string | null;
  bbox_pt?: number[];
  label?: string;
  label_bbox_pt?: number[];
  drawn_area_m2?: number | null;
  plan_scale?: string;
  // swiss_dwellings
  number?: string;
  apartment?: string;
  area_m2_dxf?: number;
  area_m2_printed?: number | null;
  printed_matches_dxf?: boolean | null;
}

export interface KgCrossCheck {
  storey?: string;
  what: string;
  model: number;
  drawn: number;
  ok: boolean | null; // null = not comparable (reason says why)
  reason?: string;
  // W1 843beaa: sheets are cuts at floor + 1.2 m; compare with the elements crossing that plane
  model_cut?: number;
  drawn_all?: number;
  drawn_other?: Record<string, number>;
  cut_z?: number;
  plan?: string;
}

export interface Kg {
  path: string;
  source: string;
  group?: string;
  siblings?: Record<string, string>;
  kind?: string;
  model?: string | null;
  storey?: KgStorey | null;
  files?: KgFile[];
  storeys?: KgStorey[];
  rooms?: KgRoom[];
  same_building?: string[];
  same_site?: string[];
  crosschecks?: KgCrossCheck[];
  transform?: { s: number; a: number; b: number; rms_pt: number; scale?: string };
  counts_dxf?: Record<string, number>;
  /** Linked files for the strip (W1 2eea21a: {path, kind, label, relation}); older stoa.kg put the graph's
   *  {id, type, label} nodes here instead (night at 00:40), so both shapes are accepted. */
  nodes?: { path?: string; kind?: string; label: string; relation?: string; id?: string; type?: string }[];
  edges?: { from: string; to: string; rel: string }[];
  /** Cross-checks as one-line badges (W1 2eea21a). */
  checks?: { text: string; ok: boolean }[];
  /** The fine graph (model, plans, storeys, rooms) for a graph view. */
  graph?: { nodes: { id: string; type: string; label: string }[]; edges: { from: string; to: string; rel: string }[] };
  kg_error?: string;
}

/** R1's room graph of a CubiCasa plan (GET /api/rooms, experiments/r1/room_graph/graph.py); boxes in image px. */
export interface RoomGraphRoom {
  id: string;
  cls: string; // living | bedroom | kitchen | bath | entry | storage | garage | sauna | outdoor | undefined
  label?: string | null; // printed label read on the plan ('MH', 'OH', 'WC')
  bbox: number[];
  centroid: number[];
  m2?: number | null;
  m2_80?: number[] | null;
  windows?: number[][];
  doors?: string[];
  fixtures?: Record<string, number[][]>;
  door_to?: string[];
  open_to?: string[];
}
export interface RoomGraph {
  path: string;
  size: number[];
  rooms: RoomGraphRoom[];
  doors: { id: string; box: number[]; between: string[] }[];
  windows: { box: number[]; room: string | null; side?: string }[];
  scale?: { px_per_m?: number; assumptions?: string[]; missing?: string[] } | null;
  source?: string;
}

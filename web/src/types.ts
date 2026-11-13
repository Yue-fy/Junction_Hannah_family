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
  value: number | string | null;
  unit: string | null;
  confidence: number;
  evidence: Evidence[];
  trace: string[];
  solver: string;
  assumptions?: string[];
  missing?: string[];
  cost?: Cost;
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
}

export interface ExampleQuestion {
  question: string;
  type: string;
  unit: string | null;
  has_fixture?: boolean;
}

export interface KgNode {
  path: string;
  kind: string;
  label: string;
  relation: string;
}

export interface Kg {
  path: string;
  project: string;
  nodes: KgNode[];
  mock?: boolean;
}

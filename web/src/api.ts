import type { Answer, ExampleQuestion, FileInfo, Kg, RoomGraph } from "./types";

// All calls go to `/api/*`; the Vite middleware forwards to W4's API (:8100) or falls back to the mock.
export type Backend = "live" | "mock" | "disk" | "kg" | "unknown";
export let lastBackend: Backend = "unknown";
const listeners: ((b: Backend) => void)[] = [];
export const onBackend = (f: (b: Backend) => void) => listeners.push(f);

async function call<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  const b = (r.headers.get("X-Stoa-Backend") as Backend) ?? "unknown";
  if (b !== "disk" && b !== "kg") {
    lastBackend = b;
    listeners.forEach((f) => f(b));
  }
  if (!r.ok) {
    let detail = r.statusText;
    try {
      detail = (await r.json()).detail ?? detail;
    } catch {
      /* not json */
    }
    throw new Error(`${r.status} ${detail}`);
  }
  return (await r.json()) as T;
}

export const fileUrl = (path: string) => `/api/file?path=${encodeURIComponent(path)}`;

export const listFiles = (source = "", q = "", limit = 60, withQuestions = true) =>
  call<{ files: FileInfo[] }>(`/api/files?source=${encodeURIComponent(source)}&q=${encodeURIComponent(q)}&limit=${limit}${withQuestions ? "" : "&with_questions=false"}`)
    .then((r) => r.files);

export const exampleQuestions = (path: string) =>
  call<{ questions: ExampleQuestion[] }>(`/api/questions?path=${encodeURIComponent(path)}`).then((r) => r.questions);

export const knowledgeGraph = (path: string) => call<Kg>(`/api/kg?path=${encodeURIComponent(path)}`);

/** Rooms + door links of a CubiCasa plan (R1's room graph from the cached CubiCasa5K segmentation; local only). */
export const roomGraph = (path: string) => fetch(`/api/rooms?path=${encodeURIComponent(path)}`)
  .then((r) => (r.ok ? (r.json() as Promise<RoomGraph>) : Promise.reject(new Error(`${r.status}`))));

export const ask = (path: string, question: string, solver?: string, solverArgs?: Record<string, unknown>) =>
  call<Answer>("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(solver ? { path, question, solver, ...(solverArgs ? { solver_args: solverArgs } : {}) } : { path, question }),
  });

/** Hosted NVIDIA Nemotron (vision + reasoning) as an on-demand second opinion: one API call, cached by the API. */
export const secondOpinion = (path: string, question: string) => ask(path, question, "vlm_direct", { backend: "nvidia" });

/** Your own drawing: saved by the Vite middleware outside the repo and the dataset; returns its FileInfo
 * (path `upload/<id>/<name>`), usable like any dataset path in the calls above. */
export const upload = (file: File) =>
  call<FileInfo>(`/api/upload?name=${encodeURIComponent(file.name)}`, { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file });

export const benchmark = () => fetch("/api/bench").then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${r.status}`))));

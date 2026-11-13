import type { Answer, Cost, Evidence } from "./types";

// Same rates as stoa/eval/runner.py:RATES (USD). Keep in sync.
const RATES = {
  gpu_usd_per_s: 0.0006, cpu_usd_per_s: 0.000014, api_usd_per_mtok_in: 0.4, api_usd_per_mtok_out: 1.6,
  local_usd_per_mtok_in: 0.05, local_usd_per_mtok_out: 0.2,
};
const EUR_PER_USD = 0.86; // display only; fixed rate, not live

export function costUsd(c: Cost): number {
  const g = (k: string) => Number(c[k] ?? 0);
  const localIn = Math.max(0, g("llm_tokens_in") - g("api_tokens_in"));
  const localOut = Math.max(0, g("llm_tokens_out") - g("api_tokens_out"));
  let usd = g("gpu_seconds") * RATES.gpu_usd_per_s + g("wall_seconds") * RATES.cpu_usd_per_s;
  usd += (g("api_tokens_in") * RATES.api_usd_per_mtok_in + g("api_tokens_out") * RATES.api_usd_per_mtok_out) / 1e6;
  if (!g("gpu_seconds")) usd += (localIn * RATES.local_usd_per_mtok_in + localOut * RATES.local_usd_per_mtok_out) / 1e6;
  return usd;
}

export function costTier(c: Cost): "deterministic" | "local" | "api" {
  if ((c.api_calls ?? 0) > 0 || (c.api_tokens_in ?? 0) > 0) return "api";
  if ((c.llm_calls ?? 0) > 0 || (c.llm_tokens_in ?? 0) > 0 || (c.gpu_seconds ?? 0) > 0) return "local";
  return "deterministic";
}

const TIER_LABEL = { deterministic: "rules only", local: "local model", api: "hosted model" };
const UNIT_LABEL: Record<string, string> = { m2: "m²", m3: "m³", ft2: "ft²", count: "", m: "m" };

const esc = (s: unknown) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

function fmtEur(usd: number) {
  const eur = usd * EUR_PER_USD;
  if (eur === 0) return "€0";
  if (eur < 0.0001) return `€${(eur * 1e6).toFixed(1)}µ`;
  if (eur < 0.01) return `€${eur.toFixed(5)}`;
  return `€${eur.toFixed(3)}`;
}

function fmtValue(a: Answer) {
  if (a.value === null || a.value === undefined) return "—";
  if (typeof a.value === "number") {
    const v = Number.isInteger(a.value) ? String(a.value) : a.value.toLocaleString("en", { maximumFractionDigits: 2 });
    return v;
  }
  return String(a.value);
}

/** "cross-check: … ✓/✗" lines from evidence notes and trace (D4: no contract change). */
export function crossChecks(a: Answer): { text: string; ok: boolean }[] {
  const parse = (lines: string[]) => lines.flatMap((l) => {
    const m = l.match(/cross-?check:?\s*(.*)$/i);
    if (!m) return [];
    const text = m[1].trim();
    return [{ text: text.replace(/\s*[✓✗]\s*/g, " ").trim(), ok: !/✗|disagree|mismatch/i.test(text) }];
  });
  // Evidence notes carry the specific check; the trace usually repeats it, so use the trace only as fallback.
  const fromEv = parse(a.evidence.map((e) => e.note ?? ""));
  const out = fromEv.length ? fromEv : parse(a.trace ?? []);
  return out.filter((x, i) => out.findIndex((y) => y.text === x.text) === i).slice(0, 2);
}

function evLabel(e: Evidence, i: number, describe: (g: string) => string) {
  const where = e.ifc_guid && !e.bbox ? `3D · ${esc(describe(e.ifc_guid))}` : e.bbox ? (e.ifc_guid ? "2D + 3D" : "2D") : "";
  return `<li class="ev-item" data-i="${i}"><span class="n">${i + 1}</span><span class="t">${esc(e.note || e.ifc_guid || "evidence")}</span><span class="w">${where}</span></li>`;
}

export function renderCard(el: HTMLElement, a: Answer, opts: { roundTripMs: number; onEvidence: (i: number) => void; describeGuid: (g: string) => string }) {
  const c: Cost = a.cost ?? {};
  const tier = costTier(c);
  const wall = c.wall_seconds && c.wall_seconds > 0 ? c.wall_seconds : opts.roundTripMs / 1000;
  const tokens = (c.llm_tokens_in ?? 0) + (c.llm_tokens_out ?? 0);
  const conf = Math.round((a.confidence ?? 0) * 100);
  const confClass = conf >= 85 ? "hi" : conf >= 55 ? "mid" : "lo";
  const checks = crossChecks(a);
  const unit = a.unit ? UNIT_LABEL[a.unit] ?? a.unit : "";
  const isText = typeof a.value === "string";
  const ev = a.evidence ?? [];
  const shown = ev.slice(0, 60);

  el.className = `card answer ${a.value === null ? "refused" : ""}`;
  el.innerHTML = `
    <div class="value-row">
      <div class="value ${isText ? "text" : ""}">${esc(fmtValue(a))}${unit ? `<span class="unit">${esc(unit)}</span>` : ""}</div>
      <div class="conf ${confClass}" title="Calibrated confidence">
        <div class="conf-num">${conf}%</div><div class="conf-bar"><i style="width:${conf}%"></i></div><div class="conf-lbl">confidence</div>
      </div>
    </div>
    ${checks.map((x) => `<div class="xcheck ${x.ok ? "ok" : "bad"}"><b>${x.ok ? "✓ Cross-checked" : "✗ Sources disagree"}</b> ${esc(x.text)}</div>`).join("")}
    <div class="cost">
      <span class="tier ${tier}" title="Cheapest path that answered">${TIER_LABEL[tier]}</span>
      <span title="Wall time">⏱ ${wall < 1 ? `${Math.round(wall * 1000)} ms` : `${wall.toFixed(1)} s`}</span>
      <span title="LLM tokens in / out">${tokens ? `${(c.llm_tokens_in ?? 0).toLocaleString()} / ${(c.llm_tokens_out ?? 0).toLocaleString()} tok` : "0 tokens"}</span>
      <span title="Estimated cost with the eval's rates (stoa/eval/runner.py), shown in EUR at ${EUR_PER_USD} €/$">≈ ${fmtEur(costUsd({ ...c, wall_seconds: wall }))}</span>
      <span class="solver" title="Solver">${esc(a.solver || "?")}</span>
    </div>
    <details class="sec" open><summary>Why <small>${(a.trace ?? []).length} steps</small></summary>
      <ol class="trace">${(a.trace ?? []).map((t) => `<li>${esc(t)}</li>`).join("")}</ol></details>
    ${(a.assumptions ?? []).length ? `<details class="sec" open><summary>Assumptions</summary><ul class="assume">${a.assumptions!.map((t) => `<li>${esc(t)}</li>`).join("")}</ul></details>` : ""}
    ${(a.missing ?? []).length ? `<details class="sec" open><summary>What would make it certain</summary><ul class="missing">${a.missing!.map((t) => `<li>${esc(t)}</li>`).join("")}</ul></details>` : ""}
    <details class="sec" open><summary>Evidence <small>${ev.length} item${ev.length === 1 ? "" : "s"} · click to zoom</small></summary>
      <ul class="evidence">${shown.map((e, i) => evLabel(e, i, opts.describeGuid)).join("")}${ev.length > shown.length ? `<li class="more">+ ${ev.length - shown.length} more</li>` : ""}</ul></details>
  `;
  el.querySelectorAll<HTMLElement>(".ev-item").forEach((li) => li.addEventListener("click", () => opts.onEvidence(Number(li.dataset.i))));
}

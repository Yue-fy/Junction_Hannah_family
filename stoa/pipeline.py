"""`pipeline` — the team's one entry point: parse → route → cost-aware cascade → never a bare refusal (S0 D4).

    python -m stoa.eval --solver pipeline --split dev

1. Parse the question into an intent (`stoa.router.intent`, rules, any language).
2. Route by file type and siblings (cheapest first): IFC → `ifc`; PDF with a DXF sibling → `dxf`; schedule
   sheets → `schedule`; vector PDF → `pdf_vector`; raster → `raster`; then `vlm_direct` (local VLM).
   Solvers that are not registered yet are skipped, so the pipeline keeps working as solvers land.
3. Gate per (source, intent) with `stoa/router/gating.json` (measured on TRAIN): a solver that does not beat the
   prior on train for this kind of question is skipped (saves cost and accuracy). Confidence = the solver's
   train hit rate for this key when known.
4. Escalate: if the accepted answer is unsure (confidence < `accept`), try the next solver; two independent
   solvers that agree raise confidence (cross-check note in evidence/trace), disagreement goes to `missing`.
5. Last resort: the train prior for this intent, with assumptions and what is missing. Never `value=None`.
   Hosted Nemotron (`vlm_direct` with backend=nvidia) only with `api=1` and only when still unsure.

Options (`--solver-arg k=v`): accept=0.6 (confidence to stop), agree=cheap|always|never (second opinion when
unsure: cheap = only from a deterministic solver; always = also the local VLM),
api=0 (allow hosted API tier), margin=0.03 (gate margin over the prior), max_tries=3, vlm_args (json dict for
vlm_direct), use_gate=1, compose=1 (split compound questions), normalise=1 (give template solvers the canonical
English question when the asked one is a translation/paraphrase).
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from stoa.contract import Answer, Cost, Evidence
from stoa.data import siblings, source_of
from stoa.router import gating, prior
from stoa.router.canonical import canonical
from stoa.router.compose import combine, decompose
from stoa.router.intent import Intent, parse
from stoa.router.prior import known_template

IMG_EXT = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".gif")
# tier of each solver (cost order); unknown names count as "local"
TIER = {"dxf": "deterministic", "ifc": "deterministic", "schedule": "deterministic", "pdf_vector": "deterministic",
        "pdf_text": "deterministic", "raster": "local", "vlm_direct": "local", "agent": "local",
        "vlm_nvidia": "api", "prior": "deterministic"}


def route(path: str, intent: Intent | None = None) -> list[str]:
    """Candidate solvers for this file, cheapest first (names; may not all be registered)."""
    src = source_of(path)
    ext = Path(path).suffix.lower()
    sib = siblings(path)
    out: list[str] = []
    if ext == ".ifc" or (src == "ifc_models" and ".ifc" in sib):
        out.append("ifc")
    if ext == ".pdf" or ".pdf" in sib:
        if ".dxf" in sib:
            out.append("dxf")
        if src == "opening_design" or (intent and intent.filters.get("sheet")):
            out.append("schedule")
        out += ["pdf_vector", "pdf_text"]
    if ext in IMG_EXT or any(e in sib for e in IMG_EXT):
        out.append("raster")
    out += ["agent", "vlm_direct"]
    seen: set[str] = set()
    return [x for x in out if not (x in seen or seen.add(x))]


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _agree(a, b, task: str) -> bool:
    x, y = _num(a), _num(b)
    if x is None or y is None:
        return str(a).strip().lower() == str(b).strip().lower()
    if task == "count":
        return round(x) == round(y)
    return abs(x - y) <= 0.02 * max(abs(y), 1e-9)


def _cost_of(ans: Answer) -> Cost:
    c = ans.cost
    return Cost.model_validate(c) if isinstance(c, dict) else (c or Cost())


from stoa.solvers import register  # noqa: E402  (after helpers: registry imports this module)
from stoa.solvers.base import BaseSolver  # noqa: E402


@register("pipeline")
class Pipeline(BaseSolver):
    def __init__(self, accept: float | str = 0.6, agree: str = "cheap", api: int | str = 0, margin: float | str = 0.03,
                 max_tries: int | str = 3, vlm_args: str | dict | None = None, use_gate: int | str = 1,
                 compose: int | str = 1, normalise: int | str = 1, **kwargs):
        super().__init__(**kwargs)
        self.accept = float(accept)
        self.agree = {"1": "cheap", "0": "never", "2": "always"}.get(str(agree), str(agree))  # cheap|never|always
        self.api = bool(int(api))
        self.margin = float(margin)
        self.max_tries = int(max_tries)
        self.use_gate = bool(int(use_gate))
        self.compose = bool(int(compose))
        self.normalise = bool(int(normalise))
        self.vlm_args = json.loads(vlm_args) if isinstance(vlm_args, str) else dict(vlm_args or {})
        self._solvers: dict[str, object | None] = {}
        self._lock = threading.Lock()

    # -- registry access ------------------------------------------------------------------------
    def _get(self, name: str):
        with self._lock:
            if name not in self._solvers:
                from stoa.solvers import available, get_solver

                inst = None
                if name == "vlm_nvidia" and "vlm_direct" in available():
                    inst = get_solver("vlm_direct", backend="nvidia", **self.vlm_args)
                elif name in available() and name != self.name:
                    inst = get_solver(name, **(self.vlm_args if name == "vlm_direct" else {}))
                self._solvers[name] = inst
            return self._solvers[name]

    def can_handle(self, path: str, question: str) -> bool:
        return True

    # -- main -------------------------------------------------------------------------------------
    def solve(self, path: str, question: str) -> Answer:
        t0 = time.perf_counter()
        plan = decompose(source_of(path), question) if self.compose else None
        if plan is None:
            ans = self._solve_atomic(path, question)
        else:
            ans = self._solve_composed(path, question, plan)
        ans.cost.wall_seconds = round(time.perf_counter() - t0, 4)
        return ans

    def _solve_composed(self, path: str, question: str, plan) -> Answer:
        trace = [f"compound question → {plan.op} over {len(plan.subs)} parts: " + ", ".join(plan.labels)]
        parts = []
        total = Cost()
        for lab, sub in zip(plan.labels, plan.subs):
            a = self._solve_atomic(path, sub)
            total = total.add(_cost_of(a))
            parts.append(a)
            trace.append(f"part '{lab}': \"{sub[:90]}\" → {a.value} {a.unit or ''} (conf {a.confidence:.2f}, {a.solver})")
        value, expr = combine(plan, [a.value for a in parts])
        trace.append(f"combine: {expr}")
        conf = 1.0
        for a in parts:
            conf *= max(0.0, min(1.0, a.confidence))
        if plan.op == "exists":
            conf = max(conf, parts[0].confidence)
        evidence = []
        for lab, a in zip(plan.labels, parts):
            for e in a.evidence:
                evidence.append(e.model_copy(update={"note": f"{lab}: {e.note}".strip(": ")}))
        assumptions = [f"{lab}: {x}" for lab, a in zip(plan.labels, parts) for x in a.assumptions]
        missing = [f"{lab}: {x}" for lab, a in zip(plan.labels, parts) for x in a.missing]
        unit = plan.unit if plan.unit else None
        if unit is None and plan.op in ("sum", "diff", "rdiff", "max", "min") and parts:
            unit = parts[0].unit
        out = Answer(value=value, unit=unit, confidence=round(conf, 3), evidence=evidence, trace=trace,
                     solver="pipeline/compose", assumptions=assumptions, missing=missing, cost=total)
        return out

    def _solve_atomic(self, path: str, question: str) -> Answer:
        t0 = time.perf_counter()
        intent = parse(question)
        src = source_of(path)
        trace = [f"intent: {intent.describe()} (lang {intent.lang})"]
        cands = route(path, intent)
        if self.api:
            cands.append("vlm_nvidia")
        if self.use_gate:
            order, gate = gating.plan(src, intent.key, cands, margin=self.margin)
        else:
            order, gate = cands, None
        acc = (gate or {}).get("acc", {})
        if gate:
            skipped = [c for c in cands if c in acc and c not in order]
            trace.append(f"gate (train n={gate['n']}): prior {100 * acc.get('prior', 0):.0f}%"
                         + "".join(f", {c} {100 * acc[c]:.0f}%" for c in cands if c in acc)
                         + (f"; skip {', '.join(skipped)}" if skipped else ""))
        else:
            trace.append("no train gate for this kind of question: general path by file type")

        canon = None
        if self.normalise and not known_template(question):
            canon = canonical(src, intent)
        total = Cost()
        answers: list[tuple[str, Answer, float]] = []  # (solver, answer, calibrated confidence)
        tries = 0
        for name in order:
            if tries >= self.max_tries:
                break
            s = self._get(name)
            if s is None:
                continue
            # unseen wording (translation/paraphrase) of a known kind: every solver gets the canonical English
            # question (template solvers match it; the VLM is also far better in English, F's error analysis)
            ask = canon if (canon and canon != question) else question
            try:
                if not (s.can_handle(path, ask) or (ask != question and s.can_handle(path, question))):
                    continue
            except Exception:  # noqa: BLE001
                continue
            tries += 1
            if ask != question:
                trace.append(f"{name}: asked the canonical form \"{canon[:100]}\"")
            try:
                ans = s.solve(path, ask)
            except Exception as e:  # noqa: BLE001
                trace.append(f"{name}: error {type(e).__name__}: {str(e)[:120]}")
                continue
            if not isinstance(ans, Answer):
                ans = Answer.model_validate(ans)
            total = total.add(_cost_of(ans))
            if ans.value is None:
                trace.append(f"{name}: abstained ({(ans.missing or ['?'])[0][:80]})")
                continue
            if gate and name in acc:  # train hit rate for this key, smoothed (k+1)/(n+2): 40/40 -> 0.976, not 1.0
                conf = (acc[name] * gate["n"] + 1) / (gate["n"] + 2)
            else:
                conf = ans.confidence
            trace.append(f"{name}: {ans.value} {ans.unit or ''} (conf {conf:.2f}"
                         + (", train hit rate" if name in acc else "") + ")")
            answers.append((name, ans, conf))
            if conf >= self.accept or self.agree == "never" or len(answers) >= 2:
                break
            # unsure: a second opinion only if it is cheap (deterministic), or always with agree=always
            rest = [n for n in order[order.index(name) + 1:] if self._get(n) is not None]
            if not rest or (self.agree == "cheap" and TIER.get(rest[0], "local") != "deterministic"):
                break
            trace.append(f"unsure (conf {conf:.2f} < {self.accept}): asking {rest[0]} for a cross-check")
        best = self._combine(answers, intent, trace)
        if best is None:
            best = self._prior_answer(src, intent, trace, gate)
        best.cost = total.add(_cost_of(best)) if best.solver == "prior" else total
        best.cost.wall_seconds = round(time.perf_counter() - t0, 4)
        # keep the sub-solver's own steps after ours, short
        best.trace = trace + [f"[{best.solver}] {t}" for t in best.trace[-8:]]
        best.solver = f"pipeline/{best.solver}"
        return best

    def _combine(self, answers, intent: Intent, trace: list[str]) -> Answer | None:
        if not answers:
            return None
        name, ans, conf = max(answers, key=lambda x: x[2])
        out = ans.model_copy(deep=True)
        out.solver = name
        out.confidence = round(min(1.0, conf), 3)
        if len(answers) >= 2:
            (n1, a1, c1), (n2, a2, c2) = answers[0], answers[1]
            if _agree(a1.value, a2.value, intent.task):
                out.confidence = round(min(0.99, 1 - (1 - c1) * (1 - c2)), 3)
                note = f"cross-check: {n1} {a1.value} = {n2} {a2.value} ✓"
            else:
                out.confidence = round(conf * 0.8, 3)
                note = f"cross-check: {n1} {a1.value} ≠ {n2} {a2.value}"
                out.missing = [*out.missing, f"{n1} and {n2} disagree ({a1.value} vs {a2.value})"]
            trace.append(note)
            if out.evidence:
                out.evidence[0] = out.evidence[0].model_copy(update={"note": (out.evidence[0].note + "; " + note).strip("; ")})
        if not out.evidence:
            out.missing = [*out.missing, "no located evidence from this solver"]
        return out

    def _prior_answer(self, src: str, intent: Intent, trace: list[str], gate: dict | None) -> Answer:
        pa = prior.lookup(src, intent)
        if pa is None:
            trace.append("no prior for this question type")
            return Answer(value=None, confidence=0.0, solver="prior", trace=["abstain: no statistics"],
                          missing=["a solver for this question type"])
        what = intent.target if intent.target != "unknown" else intent.task
        assumptions = [f"no direct evidence; answered with the {'median' if intent.task in ('area', 'length', 'volume') else 'most common'} "
                       f"answer for '{what}' questions on {pa.n} training drawings (right {100 * pa.hit_rate:.0f}% of the time)"]
        missing = [f"a reliable reading of {what} on this drawing"]
        if gate:
            missing.append("solvers tried did not beat this prior on training data for this question type")
        trace.append(f"prior[{pa.level}]: {pa.value} {pa.unit or ''} (train hit rate {100 * pa.hit_rate:.0f}%, n={pa.n})")
        return Answer(value=pa.value, unit=pa.unit, confidence=round(pa.hit_rate, 3), solver="prior",
                      assumptions=assumptions, missing=missing, trace=[])


__all__ = ["Pipeline", "route", "Evidence"]

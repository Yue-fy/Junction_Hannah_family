"""Generate `hardL`: the SAME known-gold questions in 8 languages nobody has tuned on (language robustness probe).

Why (F, 04:15): sealed hard2r showed that the generality drop on fresh questions is mostly LANGUAGE: new English
wordings ~80%, Polish / Estonian ~20% (KNOWLEDGE 04:01). R2 (stoa.llm.to_english) and W4 (pipeline front end) are
building a translate-first front end. This probe measures it with gold answers and a PAIRED design: 60 base English
questions (40 atomic dev questions + 20 hard2 compositions; known gold, dev drawings only) are asked again in each
language, so `acc(en) - acc(xx)` on the same items is the language penalty, free of item difficulty.

Translations come from a DIFFERENT model family than the local Qwen server that a front end would use (hosted
Nemotron 3.5 VL via stoa.llm backend="nvidia", reasoning off), so a front end is not just inverting its own output.
Quoted names, numbers and units are checked to be copied verbatim; a failing (question, language) pair is retried
once, then dropped.

Two files, two rules:
  hardL_open.jsonl  en + cs/hu/tr/ro (R2's development languages): OPEN, read it, debug on it.
  hardL.jsonl       nb/hr/el/lt: HELD OUT. F/S0 run it at milestones, aggregates only; never quote its questions.
  Neither shares a language with sealed hard2r (es/et/pl) or hard3 (en/it/de/es/nl/fi/pt/sv).
The eval reports accuracy per language as by_kind ("lang:cs", ...), and per origin as by_recipe.

Run:  python -m stoa.eval.hardl --write   (translations cached in $JUNCTION_SHARED/sealed/F/hardL_translations.json;
      prints counts only)
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import random
import re
import sys
from pathlib import Path

from stoa.data import _QUOTED, drawing_group, load_questions, source_of
from stoa.eval.splits import SEED, load_split, shared_root, splits_dir

OPEN_LANGS = ("cs", "hu", "tr", "ro")
HELD_LANGS = ("nb", "hr", "el", "lt")
LANG_NAMES = {"cs": "Czech", "hu": "Hungarian", "tr": "Turkish", "ro": "Romanian",
              "nb": "Norwegian Bokmål", "hr": "Croatian", "el": "Greek", "lt": "Lithuanian"}
SCORED = {"count", "area", "length", "volume", "ratio"}
ATOMIC_QUOTA = {("cubicasa5k", "count"): 12, ("swiss_dwellings", "count"): 6, ("swiss_dwellings", "area"): 8,
                ("ifc_models", "area"): 6, ("ifc_models", "count"): 4, ("ifc_models", "length"): 2,
                ("ifc_models", "volume"): 2}
HARD2_QUOTA = {("cubicasa5k", "count"): 6, ("swiss_dwellings", "ratio"): 4, ("swiss_dwellings", "area"): 3,
               ("swiss_dwellings", "count"): 2, ("ifc_models", "area"): 2, ("ifc_models", "length"): 1,
               ("ifc_models", "ratio"): 1, ("ifc_models", "count"): 1}
_EN = re.compile(r"^(how|what|which|is|are|does|do|count|give|find|in|on|of|for|by|if|compute|calculate|state)\b", re.I)
_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def translations_path() -> Path:
    return shared_root() / "sealed" / "F" / "hardL_translations.json"


def _pick(pool: list, quota: dict, rng: random.Random, key) -> list:
    """Per (source, type) bucket: spread picks over distinct templates, then fill."""
    out = []
    for b, n in quota.items():
        cands = [r for r in pool if key(r) == b]
        rng.shuffle(cands)
        seen, first, rest = set(), [], []
        for r in cands:
            t = re.sub(r"\d+", "N", _QUOTED.sub("Q", r["question"].lower()))[:60]
            (rest if t in seen else first).append(r)
            seen.add(t)
        out += (first + rest)[:n]
    return out


def base_questions(seed: int = SEED) -> list[dict]:
    rng = random.Random(seed + 41)
    dev = [q for q in load_split("dev") if q.type in SCORED and q.answer is not None and _EN.match(q.question)]
    pool = [{"qid": q.qid, "path": q.path, "question": q.question, "answer": q.answer, "unit": q.unit, "type": q.type,
             "source": source_of(q.path), "origin": "dev", "recipe": "atomic"} for q in dev]
    atomic = _pick(pool, ATOMIC_QUOTA, rng, key=lambda r: (r["source"], r["type"]))
    h2 = [json.loads(line) for line in open(splits_dir() / "hard2.jsonl", encoding="utf-8") if line.strip()]
    h2 = [{"qid": r["qid"], "path": r["path"], "question": r["question"], "answer": r["answer"], "unit": r.get("unit"),
           "type": r["type"], "source": r["source"], "origin": "hard2", "recipe": r["meta"]["recipe"]}
          for r in h2 if r["type"] in SCORED and r.get("answer") is not None and _EN.match(r["question"])]
    comp = _pick(h2, HARD2_QUOTA, rng, key=lambda r: (r["source"], r["type"]))
    return atomic + comp


def _keep_ok(src: str, dst: str) -> bool:
    """Every quoted name (inner text) and every number of the source must survive verbatim (number: . or , ok)."""
    for m in _QUOTED.finditer(src):
        if m.group(0)[1:-1] not in dst:
            return False
    rest = _QUOTED.sub(" ", src)
    dnums = {n.replace(",", ".") for n in _NUM.findall(dst)}
    return all(n.replace(",", ".") in dnums for n in _NUM.findall(rest))


def _prompt(q: str, langs: tuple[str, ...], strict: bool) -> str:
    names = ", ".join(f"{lg} ({LANG_NAMES[lg]})" for lg in langs)
    return (f"Translate this question about a building drawing into each of these languages: {names}.\n"
            "Rules: write it the way a native-speaking architect would ask it; copy every text inside quotes (with its "
            "quote marks) exactly, untranslated; keep every number, unit and abbreviation in brackets as it is."
            + (" Do NOT change, round, spell out or drop any number." if strict else "") +
            "\nReply with JSON only: {" + ", ".join(f'"{lg}": "..."' for lg in langs) + "}.\n\nQuestion: " + q)


def _ask(q: str, langs: tuple[str, ...], strict: bool) -> dict:
    from stoa import llm
    llm.BACKENDS["nvidia"]["timeout"] = 90.0  # a hung hosted call must not stall the generator (300 s default)
    r = llm.chat(_prompt(q, langs, strict), backend="nvidia", thinking=False, max_tokens=2000, cache=True, retries=2)
    m = re.search(r"\{.*\}", r.text or "", re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        d = {}
    return {k: v.strip() for k, v in d.items() if k in langs and isinstance(v, str) and v.strip()}


def translate(base: list[dict], workers: int = 6) -> dict[str, dict[str, str]]:
    from concurrent.futures import ThreadPoolExecutor
    path = translations_path()
    tr = json.load(open(path, encoding="utf-8")) if path.exists() else {}
    langs = OPEN_LANGS + HELD_LANGS

    def one(b: dict) -> tuple[str, dict]:
        have = dict(tr.get(b["qid"], {}))
        for strict in (False, True):
            todo = tuple(lg for lg in langs if lg not in have)
            if not todo:
                break
            try:
                got = _ask(b["question"], todo, strict)
            except Exception as e:  # noqa: BLE001
                print(f"  call failed ({type(e).__name__})", file=sys.stderr)
                continue
            have.update({lg: t for lg, t in got.items() if _keep_ok(b["question"], t)})
        return b["qid"], have

    done = 0
    with ThreadPoolExecutor(workers) as ex:
        for qid, have in ex.map(one, base):
            tr[qid] = have
            done += 1
            path.parent.mkdir(parents=True, exist_ok=True)
            json.dump(tr, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print(f"  translated {done}/{len(base)}: {len(have)}/{len(langs)} languages kept", file=sys.stderr)
    return tr


def rows(base: list[dict], tr: dict, langs: tuple[str, ...], with_en: bool) -> list[dict]:
    out = []
    for b in base:
        variants = ([("en", b["question"])] if with_en else []) + \
                   [(lg, tr.get(b["qid"], {}).get(lg)) for lg in langs]
        for lg, q in variants:
            if not q:
                continue
            out.append({"qid": "L" + hashlib.sha1(f"{b['path']}\n{q}".encode()).hexdigest()[:11], "path": b["path"],
                        "question": q, "answer": b["answer"], "unit": b["unit"], "type": b["type"], "source": b["source"],
                        "group": drawing_group(b["path"]),
                        "meta": {"kind": f"lang:{lg}", "recipe": f"{b['origin']}:{b['recipe']}", "lang": lg,
                                 "base_qid": b["qid"], "from_qids": [b["qid"]]}})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--from-cache", action="store_true", help="write the splits from cached translations, no API calls")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args(argv)
    base = base_questions()
    print(f"base: {len(base)} questions", collections.Counter((b["origin"], b["source"], b["type"]) for b in base))
    if not a.write:
        return
    if a.from_cache:
        p = translations_path()
        tr = json.load(open(p, encoding="utf-8")) if p.exists() else {}
    else:
        tr = translate(base, workers=a.workers)
    for name, langs, with_en in (("hardL_open", OPEN_LANGS, True), ("hardL", HELD_LANGS, False)):
        rs = rows(base, tr, langs, with_en)
        f = splits_dir() / f"{name}.jsonl"
        with open(f, "w", encoding="utf-8") as fh:
            for r in rs:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"{name}: {len(rs)} rows", dict(collections.Counter(r["meta"]["lang"] for r in rs)))


if __name__ == "__main__":
    main()

"""Robustness of the link route on wordings R1 did NOT write: the local LLM rewrites every link question of
probe_kg + Q v17 (3 English paraphrases + one translation per language), gold unchanged; then measure the trigger
on the wording as asked and after the pipeline's to_english front end (uncovered languages only, as the pipeline
does), and kg_qa end to end on the fired rows.

    python experiments/r1/kg_qa/paraphrase.py make    -> experiments/r1/kg_qa/probe_para.jsonl
    python experiments/r1/kg_qa/paraphrase.py score
"""
import json
import re
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from experiments.r1.kg_qa.kgqa import is_link_question, solve  # noqa: E402
from experiments.r1.kg_qa.run import correct  # noqa: E402

H = Path(__file__).parent
SRC = [H / "probe_kg.jsonl", Path("/home/fangy4/work/projects/junction-shared/artifacts/Q/v17.jsonl")]
OUT = H / "probe_para.jsonl"
LANGS = {"fi": "Finnish", "de": "German", "fr": "French", "it": "Italian", "sv": "Swedish", "nl": "Dutch",
         "et": "Estonian", "es": "Spanish"}
QUOTED = re.compile(r"'([^']+)'")


def make():
    from stoa.llm import chat, extract_json

    rows = []
    for f in SRC:
        for line in open(f):
            r = json.loads(line)
            if r["meta"].get("kind", "").startswith(("link", "yesno:link")) or f.name == "probe_kg.jsonl":
                if r["qid"] == "rt9eb1ec8aa7":  # 'how many more doors on A than B' is a building fact, not a link
                    continue
                rows.append(r)

    def para(r):
        keep = [m.group(1) for m in QUOTED.finditer(r["question"])]
        p = (f"Rewrite this question about a building's drawing set and its IFC model in 3 different ways an engineer "
             f"or a hackathon judge might type it (vary words and sentence shape; same meaning; keep quoted names "
             f"exactly). Then translate the ORIGINAL into {', '.join(LANGS.values())}, the way a native engineer "
             f"would ask it, keeping quoted names. JSON: {{\"en\": [3 strings], " +
             ", ".join(f'"{k}": string' for k in LANGS) + "}}\n\nQuestion: " + r["question"])
        js = extract_json(chat(p, max_tokens=900, temperature=0.0).text) or {}
        out = []
        for i, q in enumerate((js.get("en") or [])[:3]):
            out.append(("en", i, q))
        for k in LANGS:
            if isinstance(js.get(k), str):
                out.append((k, 0, js[k]))
        res = []
        for lang, i, q in out:
            if not isinstance(q, str) or not all(k in q for k in keep):
                continue
            res.append({**r, "qid": f"{r['qid']}-{lang}{i}", "question": q.strip(),
                        "meta": {**r["meta"], "orig_qid": r["qid"], "lang": lang, "orig": r["question"]}})
        return res

    with ThreadPoolExecutor(8) as ex:
        allr = [x for xs in ex.map(para, rows) for x in xs]
    with open(OUT, "w") as f:
        for r in allr:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(allr)} paraphrases of {len(rows)} link questions -> {OUT}")


def score():
    from stoa.llm import to_english

    rows = [json.loads(x) for x in open(OUT)]

    def run(r):
        q = r["question"]
        h = is_link_question(q)
        q_used, via = q, "asked"
        if not h["fire"]:
            tr = to_english(q)  # translates only languages outside en/fi/de/fr/it, like the pipeline front end
            if tr.text != q and is_link_question(tr.text)["fire"]:
                q_used, via, h = tr.text, "to_english", is_link_question(tr.text)
        a = solve(r["path"], q_used) if h["fire"] else None
        return h["fire"], via, (correct(r, a.value) if a is not None else None), (a.confidence if a else None), \
            (a.value if a else None)

    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(run, rows))
    origs = sorted({r["meta"]["orig_qid"] for r in rows})
    half_a = set(origs[0::2])  # same split as trigger_eval.py: A = tuning, B = held out
    by = defaultdict(lambda: [0, 0, 0, 0, 0])  # n, fired, right, conf>=0.8, conf>=0.8 right
    for r, (fire, via, ok, conf, val) in zip(rows, res):
        half = "A" if r["meta"]["orig_qid"] in half_a else "B"
        for k in (r["meta"]["lang"], "ALL", "half " + half):
            b = by[k]
            b[0] += 1
            b[1] += fire
            b[2] += bool(ok)
            if conf is not None and conf >= 0.8:
                b[3] += 1
                b[4] += bool(ok)
        if not fire:
            print("NO FIRE", r["meta"]["lang"], "|", r["question"][:110])
        elif not ok:
            print("WRONG  ", r["meta"]["lang"], via, "|", r["question"][:90], "->", str(val)[:60], conf, "gold",
                  r["answer"])
    for k, (n, f, ok, hi, hiok) in sorted(by.items()):
        print(f"{k:4s} n={n:3d} trigger {f:3d} ({100 * f / n:.0f}%)  kg_qa right {ok:3d} ({100 * ok / n:.0f}%)  "
              f"conf>=0.8 {hi} ({hiok} right)")


if __name__ == "__main__":
    {"make": make, "score": score}[sys.argv[1]]()

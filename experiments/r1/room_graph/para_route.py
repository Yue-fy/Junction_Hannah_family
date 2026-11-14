"""Per-room route on wordings R1 did NOT write: the local LLM rewrites every by-eye probe question (v1..v4) 3x in
English and once in fi/de/sv/fr/it/nl/es (gold unchanged), then we measure per_room() recall (fire_any; fire for
non-area Qs) on the wording as asked, and after the pipeline's to_english front end for uncovered languages.
Split by original question: half A (tuning) / half B (held out).

    python experiments/r1/room_graph/para_route.py make|score
"""
import json
import re
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from experiments.r1.room_graph.route import per_room  # noqa: E402

P = Path(__file__).parent / "probe"
OUT = P / "probe_para.jsonl"
LANGS = {"fi": "Finnish", "de": "German", "sv": "Swedish", "fr": "French", "it": "Italian", "nl": "Dutch",
         "es": "Spanish"}


def make():
    from stoa.llm import chat, extract_json

    rows = [json.loads(x) for v in (1, 2, 3, 4) for x in open(P / f"probe_v{v}.jsonl")]

    def para(r):
        p = (f"Rewrite this question about an apartment floor plan in 3 different ways a user might type it (vary words "
             f"and sentence shape; same meaning; keep room names, codes in parentheses and numbers). Then translate the "
             f"ORIGINAL into {', '.join(LANGS.values())} as a native speaker would ask it. JSON: {{\"en\": [3 strings], "
             + ", ".join(f'"{k}": string' for k in LANGS) + "}}\n\nQuestion: " + r["question"])
        js = extract_json(chat(p, max_tokens=900, temperature=0.0).text) or {}
        if isinstance(js, list):
            js = next((x for x in js if isinstance(x, dict)), {})
        out = [("en", i, q) for i, q in enumerate((js.get("en") or [])[:3])]
        out += [(k, 0, js[k]) for k in LANGS if isinstance(js.get(k), str)]
        return [{**r, "qid": f"{r['qid']}-{lang}{i}", "question": q.strip(),
                 "meta": {**r.get("meta", {}), "orig_qid": r["qid"], "lang": lang, "orig": r["question"]}}
                for lang, i, q in out if isinstance(q, str) and q.strip()]

    with ThreadPoolExecutor(8) as ex:
        allr = [x for xs in ex.map(para, rows) for x in xs]
    with open(OUT, "w") as f:
        for r in allr:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(allr)} paraphrases of {len(rows)} probe questions -> {OUT}")


def score():
    from stoa.llm import to_english

    rows = [json.loads(x) for x in open(OUT)]
    origs = sorted({r["meta"]["orig_qid"] for r in rows})
    half_a = set(origs[0::2])
    orig_fire = {}
    for v in (1, 2, 3, 4):
        for x in open(P / f"probe_v{v}.jsonl"):
            r = json.loads(x)
            orig_fire[r["qid"]] = per_room(r["question"], r["path"])

    def run(r):
        h = per_room(r["question"], r["path"])
        via = "asked"
        if not h["fire_any"]:
            tr = to_english(r["question"])
            if tr.text != r["question"]:
                h2 = per_room(tr.text, r["path"])
                if h2["fire_any"]:
                    h, via = h2, "to_english"
        return h, via

    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(run, rows))
    by = defaultdict(lambda: [0, 0, 0, 0])  # n (orig fired), fire_any, n non-area, fire
    show = "--show" in sys.argv
    for r, (h, via) in zip(rows, res):
        o = orig_fire[r["meta"]["orig_qid"]]
        if not o["fire_any"]:
            continue  # the original wording does not fire either (whole-apartment areas etc.)
        half = "A" if r["meta"]["orig_qid"] in half_a else "B"
        for k in (r["meta"]["lang"], "ALL", "half " + half):
            b = by[k]
            b[0] += 1
            b[1] += h["fire_any"]
            if o["fire"]:
                b[2] += 1
                b[3] += h["fire"]
        if show and not h["fire_any"] and (half == "A" or "--all" in sys.argv):
            print("  miss", half, r["meta"]["lang"], "|", r["question"][:110])
    for k, (n, fa, nn, f) in sorted(by.items()):
        print(f"{k:7s} fire_any {fa}/{n} ({100 * fa / max(n, 1):.0f}%)   non-area fire {f}/{nn} "
              f"({100 * f / max(nn, 1):.0f}%)")


if __name__ == "__main__":
    {"make": make, "score": score}[sys.argv[1]]()

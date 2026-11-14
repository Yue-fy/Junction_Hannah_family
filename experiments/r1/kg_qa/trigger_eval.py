"""Trigger recall on the LLM paraphrases, split by ORIGINAL question (half A = tuning, half B = held out), and false
fires on every dataset question + open split.

    python experiments/r1/kg_qa/trigger_eval.py [--show A|B]
"""
import glob
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from experiments.r1.kg_qa.kgqa import is_link_question  # noqa: E402

H = Path(__file__).parent


def halves():
    rows = [json.loads(x) for x in open(H / "probe_para.jsonl")]
    origs = sorted({r["meta"]["orig_qid"] for r in rows})
    a = set(origs[0::2])
    return [r for r in rows if r["meta"]["orig_qid"] in a], [r for r in rows if r["meta"]["orig_qid"] not in a]


def main():
    A, B = halves()
    show = sys.argv[sys.argv.index("--show") + 1] if "--show" in sys.argv else None
    for name, rs in (("A (tuning)", A), ("B (held out)", B)):
        by = defaultdict(lambda: [0, 0])
        for r in rs:
            f = is_link_question(r["question"])["fire"]
            for k in (r["meta"]["lang"], "ALL"):
                by[k][0] += 1
                by[k][1] += f
            if show and name.startswith(show) and not f:
                print("  miss", r["meta"]["lang"], "|", r["question"][:120])
        print(name, "  ".join(f"{k} {v[1]}/{v[0]}" for k, v in sorted(by.items())))
    fires = 0
    n = 0
    for line in open(os.environ["STOA_DATA"] + "/questions.jsonl"):
        q = json.loads(line)["question"]
        n += 1
        if is_link_question(q)["fire"]:
            fires += 1
            if fires <= 8:
                print("  FALSE FIRE dataset:", q[:120])
    for f in sorted(glob.glob("/home/fangy4/work/projects/junction-shared/results/splits/*.jsonl")):
        if f.endswith(("test.jsonl", "hard2q.jsonl", "hard2p.jsonl", "hard2r.jsonl", "hard3.jsonl")):
            continue
        for line in open(f):
            r = json.loads(line)
            if "question" in r:
                n += 1
                if is_link_question(r["question"])["fire"]:
                    fires += 1
                    print("  FALSE FIRE", Path(f).name, r["question"][:120])
    print(f"false fires: {fires} / {n}")


if __name__ == "__main__":
    main()

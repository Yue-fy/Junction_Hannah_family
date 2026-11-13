"""Retry the room-label call for drawings whose v2 output looped, with vLLM repetition_penalty.
Writes <stem>.labels.v2r.json next to the v2 cache; policy.py --retry uses it in place of a looped v2 output.
Run: $JUNCTION_VENV/bin/python -I retry_loops.py [--penalty 1.15]
"""
import argparse
import concurrent.futures as cf
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from openai import OpenAI  # noqa: E402

import run  # noqa: E402
from policy import looped  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--penalty", type=float, default=1.15)
    a = ap.parse_args()
    client = OpenAI(base_url=run.BASE, api_key="EMPTY")
    todo = []
    for f in sorted(os.listdir(run.CACHE)):
        if f.endswith(".labels.v2.json") and looped(json.load(open(os.path.join(run.CACHE, f)))["text"]):
            todo.append(f.replace(".labels.v2.json", ""))
    print(f"{len(todo)} looped drawings to retry")

    def go(stem):
        out_f = os.path.join(run.CACHE, stem + ".labels.v2r.json")
        if os.path.exists(out_f):
            return
        t0 = time.time()
        r = client.chat.completions.create(
            model="default", temperature=0, max_tokens=1500, extra_body={"repetition_penalty": a.penalty},
            messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + run.img_b64(os.path.join(run.DATA, "data/cubicasa5k", stem))}},
                {"type": "text", "text": run.PROMPT}]}])
        json.dump({"text": r.choices[0].message.content, "penalty": a.penalty,
                   "cost": {"in": r.usage.prompt_tokens, "out": r.usage.completion_tokens, "s": time.time() - t0}},
                  open(out_f, "w"), ensure_ascii=False)
    with cf.ThreadPoolExecutor(12) as ex:
        list(ex.map(go, todo))
    still = sum(looped(json.load(open(os.path.join(run.CACHE, s + ".labels.v2r.json")))["text"]) for s in todo)
    print(f"retried {len(todo)}; still looping after retry: {still}")

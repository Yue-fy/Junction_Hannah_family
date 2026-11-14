"""Batched throughput of a local server (amortised GPU-s per token for the cost meter). R2 09:40.
usage: python experiments/r2/tput.py PORT MODEL [CONC=16]"""
import concurrent.futures as cf
import sys
import time

from openai import OpenAI

port, model = sys.argv[1], sys.argv[2]
conc = int(sys.argv[3]) if len(sys.argv) > 3 else 16
c = OpenAI(base_url=f"http://127.0.0.1:{port}/v1", api_key="x")
filler = " ".join(f"room {i} has area {i * 1.7:.1f} m2 and {i % 5} doors;" for i in range(260))  # ~2.6k tokens


def call(i, prompt_len, out):
    p = f"[{i}] " + (filler if prompt_len else "Write a numbered list of 60 short building facts.")
    r = c.chat.completions.create(model=model, messages=[{"role": "user", "content": p}], max_tokens=out, temperature=0.7,
                                  extra_body={"chat_template_kwargs": {"enable_thinking": False}, "ignore_eos": True})
    return r.usage.prompt_tokens, r.usage.completion_tokens


for name, plen, out, n in [("prefill", 1, 1, conc * 4), ("decode", 0, 256, conc)]:
    t = time.time()
    with cf.ThreadPoolExecutor(conc) as ex:
        us = list(ex.map(lambda i: call(i, plen, out), range(n)))
    dt = time.time() - t
    tin, tout = sum(u[0] for u in us), sum(u[1] for u in us)
    print(f"{model} {name}: {n} reqs in {dt:.1f}s -> prefill {tin / dt:,.0f} tok/s, decode {tout / dt:,.0f} tok/s")

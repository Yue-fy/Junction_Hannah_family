"""Room-type counts on cubicasa by READING room labels (one VLM call per drawing) vs asking directly.

Hypothesis: ~25% of all questions (saunas, kitchens, bedrooms, bathrooms, WC rooms, balconies on Finnish
plans) are answered by the printed room codes (MH, K/KK/TK/KT, KH/PH/PESUH/KPH/SH, WC, S/SAUNA, PARV).
Method A "labels": ask the VLM once per drawing to transcribe every room label; map codes to classes by
rules; count. Method B "direct": ask the VLM the question itself (one call per question). Method C
"prior": the most common train answer for the template. Scored per template on our dev split.
Run: $JUNCTION_VENV/bin/python -I run.py [--split dev] [--max-drawings N] [--direct]
Raw VLM outputs are cached in $JUNCTION_SHARED/artifacts/R1/room_labels/.
"""
import argparse
import base64
import collections
import concurrent.futures as cf
import io
import json
import os
import re
import time

from openai import OpenAI
from PIL import Image

SHARED = os.environ.get("JUNCTION_SHARED", "/home/fangy4/work/projects/junction-shared")
DATA = os.environ.get("STOA_DATA", "/home/fangy4/work/projects/junction-data/stoa-full/junction-dataset")
CACHE = os.path.join(SHARED, "artifacts", "R1", "room_labels")
BASE = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:8001/v1")

TEMPLATES = {  # class -> regex on the question (EN + FI)
    "sauna": r"How many saunas|Kuinka monta saunaa",
    "kitchen": r"How many kitchens|Kuinka monta keittiötä",
    "bedroom": r"How many bedrooms|Kuinka monta makuuhuonetta",
    "bathroom": r"How many bathrooms or washrooms|kylpy- tai pesuhuonetta",
    "wc_room": r"How many separate WC rooms|erillistä WC-tilaa",
    "balcony": r"How many balconies|Kuinka monta parveketta",
}
# Finnish room codes -> class. Checked against the token after splitting on + / , - and spaces.
CODES = {
    "bedroom": {"MH", "MAKUUHUONE", "MAKUUH"},
    "kitchen": {"K", "KK", "TK", "KT", "KEITTIÖ", "KEITTIO", "KEITTOKOMERO", "TUPAKEITTIÖ", "AVOK", "KEITTIÖTILA"},
    "bathroom": {"KH", "PH", "KPH", "PESUH", "SH", "KYLPYHUONE", "PESUHUONE", "KYLPYH", "PESUHUONE/SAUNA"},
    "wc_room": {"WC"},
    "sauna": {"S", "SAUNA", "LÖYLYH", "LÖYLYHUONE"},
    "balcony": {"PARV", "PARVEKE", "LASPARV", "LASITETTUPARVEKE", "PARV.", "RANSKALAINENPARVEKE"},
}
# v1 listed example codes and the model echoed them back on some plans; v2 has no examples and asks for boxes.
PROMPT = ("Locate every room name or room code that is printed as text inside the rooms of this floor plan. "
          "Output a JSON list, one entry per printed label: "
          '[{"bbox_2d": [x1, y1, x2, y2], "text": "<label exactly as printed>"}]. '
          "Skip room areas (numbers with m2), dimensions and furniture.")
PROMPT_VERSION = "v2"


def img_b64(path, scale=2.0, max_side=2400):
    im = Image.open(path).convert("RGB")
    s = min(scale, max_side / max(im.size))
    if s != 1:
        im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def ask(client, path, text, max_tokens=400):
    t0 = time.time()
    r = client.chat.completions.create(model="default", temperature=0, max_tokens=max_tokens, messages=[{
        "role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + img_b64(path)}},
            {"type": "text", "text": text}]}])
    u = r.usage
    return r.choices[0].message.content, {"in": u.prompt_tokens, "out": u.completion_tokens, "s": time.time() - t0}


def classify(label):
    t = label.upper().strip().strip(".:;")
    t = re.sub(r"\s+", "", t) if t.startswith("LASITETTU") else t
    hits = set()
    for tok in re.split(r"[+/,&\s-]+", t):
        tok = re.sub(r"\d+$", "", tok.strip(".:;()"))  # MH1 -> MH
        for cls, codes in CODES.items():
            if tok in codes:
                hits.add(cls)
    return hits


def parse_items(text):
    """JSON list of {bbox_2d, text}; tolerant of code fences and truncated output."""
    items = []
    for m in re.finditer(r'\{[^{}]*?"bbox_2d"\s*:\s*\[([^\]]*)\][^{}]*?"text"\s*:\s*"([^"]*)"[^{}]*\}', text):
        try:
            box = [float(v) for v in m.group(1).split(",")]
        except ValueError:
            continue
        if len(box) == 4:
            items.append((box, m.group(2)))
    return items


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / u if u > 0 else 0


def count_labels(text):
    """Count classes over unique labels (same text + overlapping box = one label: kills repetition loops)."""
    kept = []
    for box, t in parse_items(text):
        if re.search(r"m²|m2", t) or any(t == t2 and iou(box, b2) > 0.3 for b2, t2 in kept):
            continue
        kept.append((box, t))
    c = collections.Counter()
    for _, t in kept:
        for cls in classify(t):
            c[cls] += 1
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev")
    ap.add_argument("--max-drawings", type=int, default=0)
    ap.add_argument("--direct", action="store_true", help="also ask each question directly (EN only)")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    os.makedirs(CACHE, exist_ok=True)

    gold = {}
    for line in open(os.path.join(DATA, "questions.jsonl")):
        d = json.loads(line)
        if d["path"].startswith("data/cubicasa5k/"):
            gold[(d["path"], d["question"])] = d["answer"]
    # prior from train split
    split_rows = lambda s: [json.loads(l) for l in open(os.path.join(SHARED, "results", "splits", f"{s}.jsonl"))]
    qtext = {}
    for line in open(os.path.join(DATA, "questions.jsonl")):
        d = json.loads(line)
        if d["path"].startswith("data/cubicasa5k/"):
            import hashlib
            qtext[hashlib.sha1(f"{d['path']}\n{d['question']}".encode()).hexdigest()[:12]] = d
    def tpl(q):
        for k, rx in TEMPLATES.items():
            if re.search(rx, q):
                return k
    prior_c = collections.defaultdict(collections.Counter)
    for r in split_rows("train"):
        d = qtext.get(r["qid"])
        if d and tpl(d["question"]):
            prior_c[tpl(d["question"])][d["answer"]] += 1
    prior = {k: v.most_common(1)[0][0] for k, v in prior_c.items()}

    rows = []
    for r in split_rows(a.split):
        d = qtext.get(r["qid"])
        if d and tpl(d["question"]):
            rows.append(d)
    paths = sorted({d["path"] for d in rows})
    if a.max_drawings:
        paths = paths[: a.max_drawings]
        rows = [d for d in rows if d["path"] in set(paths)]
    print(f"{len(rows)} room-type questions on {len(paths)} drawings ({a.split}); prior: {prior}")

    client = OpenAI(base_url=BASE, api_key="EMPTY")

    def labels_for(path):
        f = os.path.join(CACHE, os.path.basename(path) + f".labels.{PROMPT_VERSION}.json")
        if os.path.exists(f):
            return json.load(open(f))
        text, cost = ask(client, os.path.join(DATA, path), PROMPT, max_tokens=1500)
        out = {"text": text, "cost": cost}
        json.dump(out, open(f, "w"), ensure_ascii=False)
        return out

    with cf.ThreadPoolExecutor(a.workers) as ex:
        L = dict(zip(paths, ex.map(labels_for, paths)))

    direct = {}
    if a.direct:
        en = [d for d in rows if d["question"].startswith("How many")]

        def ask_direct(d):
            f = os.path.join(CACHE, os.path.basename(d["path"]) + f".direct.{tpl(d['question'])}.json")
            if os.path.exists(f):
                return json.load(open(f))
            text, cost = ask(client, os.path.join(DATA, d["path"]), d["question"] + " Answer with a single integer.", 20)
            m = re.search(r"\d+", text)
            out = {"text": text, "value": int(m.group()) if m else None, "cost": cost}
            json.dump(out, open(f, "w"))
            return out
        with cf.ThreadPoolExecutor(a.workers) as ex:
            for d, out in zip(en, ex.map(ask_direct, en)):
                direct[(d["path"], tpl(d["question"]))] = out

    S = collections.defaultdict(collections.Counter)
    for d in rows:
        k = tpl(d["question"])
        pred = count_labels(L[d["path"]]["text"])[k]
        S[k]["n"] += 1
        S[k]["labels"] += pred == d["answer"]
        S[k]["prior"] += prior[k] == d["answer"]
        S[k]["labels_off"] += abs(pred - d["answer"])
        if (d["path"], k) in direct and d["question"].startswith("How many"):
            S[k]["n_en"] += 1
            S[k]["direct"] += direct[(d["path"], k)]["value"] == d["answer"]
            S[k]["prior_en"] += prior[k] == d["answer"]
            S[k]["labels_en"] += pred == d["answer"]
    tot = collections.Counter()
    print(f"{'template':10s} {'n':>4s} {'labels':>7s} {'prior':>7s} {'MAE':>5s}" + ("  | n_en direct labels prior" if a.direct else ""))
    for k in TEMPLATES:
        s = S[k]
        tot.update(s)
        if s["n"]:
            line = f"{k:10s} {s['n']:4d} {s['labels']/s['n']:7.1%} {s['prior']/s['n']:7.1%} {s['labels_off']/s['n']:5.2f}"
            if a.direct and s["n_en"]:
                line += f"  | {s['n_en']:4d} {s['direct']/s['n_en']:6.1%} {s['labels_en']/s['n_en']:6.1%} {s['prior_en']/s['n_en']:6.1%}"
            print(line)
    print(f"{'ALL':10s} {tot['n']:4d} {tot['labels']/tot['n']:7.1%} {tot['prior']/tot['n']:7.1%}"
          + (f"  | {tot['n_en']:4d} {tot['direct']/max(1,tot['n_en']):6.1%} {tot['labels_en']/max(1,tot['n_en']):6.1%} {tot['prior_en']/max(1,tot['n_en']):6.1%}" if a.direct else ""))
    c_in = sum(v["cost"]["in"] for v in L.values()); c_out = sum(v["cost"]["out"] for v in L.values())
    print(f"label calls: {len(L)} drawings, tokens in {c_in}, out {c_out}, mean {sum(v['cost']['s'] for v in L.values())/len(L):.1f}s/call")
    if direct:
        print(f"direct calls: {len(direct)}, tokens in {sum(v['cost']['in'] for v in direct.values())}, out {sum(v['cost']['out'] for v in direct.values())}")


if __name__ == "__main__":
    main()

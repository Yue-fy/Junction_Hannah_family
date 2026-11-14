"""LoRA fine-tune of the served Qwen3-VL-8B on raster counting (train split only). Owner: R2.

Run under the GPU lock, next to the shared server (caps itself at --mem-frac of the GPU):
  flock $JUNCTION_SHARED/locks/gpu.lock /data/User/fangy4/envs/junction-train/bin/python \
      experiments/r2/lora/train_lora.py --data $JUNCTION_SHARED/artifacts/R2/lora/train_cc.jsonl \
      --out $JUNCTION_SHARED/artifacts/R2/lora/cc-v1 --minutes 70

The env junction-train = coder390-vllm packages (read-only, via a .pth) + peft/accelerate.
Images go through stoa.llm.downscale exactly like at inference, then the model's own HF processor
(the same one vLLM uses), so train and serve see identical visual tokens.
The adapter (PEFT format) can be served by vLLM: --enable-lora --lora-modules cc-v1=<out>.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # repo root, for stoa.llm / vlm_direct
from stoa.llm import downscale, load_image  # noqa: E402
from stoa.solvers.vlm_direct import DIRECT, SYSTEM  # noqa: E402

MODEL = "/data/User/fangy4/models/hf/local/Qwen3-VL-8B-Instruct-from-QwenImage2.1"
# chat-format markers per architecture: (turn start, assistant header after it, turn end)
MARKERS = {"qwen3vl": ("<|im_start|>", "assistant\n", "<|im_end|>"),
           "gemma4": ("<|turn>", "model\n", "<turn|>")}
ARCH = "qwen3vl"


def build(processor, rec: dict, max_pixels: int, max_turns: int, rng: random.Random):
    img, _ = downscale(load_image(rec["image"]), max_pixels)
    turns = rec["turns"][:]
    rng.shuffle(turns)
    turns = turns[:max_turns]
    msgs = [{"role": "system", "content": [{"type": "text", "text": SYSTEM}]}]
    for i, t in enumerate(turns):
        content = ([{"type": "image", "image": img}] if i == 0 else []) + \
                  [{"type": "text", "text": t["q"].strip() + "\n\n" + DIRECT["count"]}]
        msgs.append({"role": "user", "content": content})
        msgs.append({"role": "assistant", "content": [{"type": "text", "text": t["a"]}]})
    enc = processor.apply_chat_template(msgs, tokenize=True, return_dict=True, return_tensors="pt",
                                        add_generation_prompt=False)
    ids = enc["input_ids"][0]
    labels = torch.full_like(ids, -100)
    tok = processor.tokenizer
    m_start, m_head, m_end = MARKERS[ARCH]
    start = tok.convert_tokens_to_ids(m_start)
    end = tok.convert_tokens_to_ids(m_end)
    asst = tok.encode(m_head, add_special_tokens=False)
    i, n = 0, len(ids)
    while i < n:
        if ids[i] == start and ids[i + 1:i + 1 + len(asst)].tolist() == asst:
            j = i + 1 + len(asst)
            k = j
            while k < n and ids[k] != end:
                k += 1
            labels[j:k + 1] = ids[j:k + 1]  # answer tokens + end-of-turn marker
            i = k
        i += 1
    enc["labels"] = labels.unsqueeze(0)
    return enc


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--minutes", type=float, default=70.0, help="time box; saves and stops after this")
    ap.add_argument("--epochs", type=float, default=1.0)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--accum", type=int, default=8)
    ap.add_argument("--max-pixels", type=int, default=3_200_000)
    ap.add_argument("--max-turns", type=int, default=12)
    ap.add_argument("--max-samples", type=int, default=0)
    ap.add_argument("--mem-frac", type=float, default=0.42)
    ap.add_argument("--save-every", type=int, default=1000, help="samples")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--init-adapter", default="", help="continue training this saved adapter (rank/targets from it)")
    ap.add_argument("--arch", default="qwen3vl", choices=sorted(MARKERS))
    ap.add_argument("--img-tokens", type=int, default=1120, help="gemma4 only: image soft-token budget (match the server)")
    a = ap.parse_args()
    global ARCH
    ARCH = a.arch

    from peft import LoraConfig, get_peft_model
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

    torch.manual_seed(a.seed)
    rng = random.Random(a.seed)
    torch.cuda.set_per_process_memory_fraction(a.mem_frac)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    log = open(out / "train_log.jsonl", "a")

    recs = [json.loads(l) for l in open(a.data)]
    rng.shuffle(recs)
    if a.max_samples:
        recs = recs[: a.max_samples]
    total = int(len(recs) * a.epochs)
    print(f"{len(recs)} drawings, {total} samples planned, time box {a.minutes} min", flush=True)

    processor = AutoProcessor.from_pretrained(a.model)
    if a.arch == "gemma4":
        from transformers import AutoModelForImageTextToText

        processor.image_processor.max_soft_tokens = a.img_tokens  # same budget as vLLM's --mm-processor-kwargs
        model = AutoModelForImageTextToText.from_pretrained(a.model, dtype=torch.bfloat16,
                                                            attn_implementation="sdpa").cuda()
    else:
        model = Qwen3VLForConditionalGeneration.from_pretrained(a.model, dtype=torch.bfloat16,
                                                                attn_implementation="sdpa").cuda()
    model.config.use_cache = False
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.enable_input_require_grads()
    if a.init_adapter:
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, a.init_adapter, is_trainable=True)
        print(f"continuing from adapter {a.init_adapter}", flush=True)
    else:
        targets = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
        if a.arch == "gemma4":  # language model only (vision/audio towers reuse these names; vLLM serves LM LoRA)
            targets = r".*language_model.*\.(q_proj|k_proj|v_proj|o_proj|gate_proj|up_proj|down_proj)"
        cfg = LoraConfig(r=a.rank, lora_alpha=2 * a.rank, lora_dropout=0.05, bias="none", target_modules=targets)
        model = get_peft_model(model, cfg)
    model.print_trainable_parameters()

    params = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(params, lr=a.lr, weight_decay=0.0, betas=(0.9, 0.999))
    steps = max(1, total // a.accum)
    warm = max(1, int(0.05 * steps))
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: min(1.0, (s + 1) / warm) * 0.5 * (1 + math.cos(math.pi * min(1.0, s / steps))))

    model.train()
    t0 = time.time()
    run_loss, run_n, step = 0.0, 0, 0
    for si in range(total):
        rec = recs[si % len(recs)]
        try:
            enc = build(processor, rec, a.max_pixels, a.max_turns, rng)
        except Exception as e:  # noqa: BLE001
            print("skip", rec["path"], type(e).__name__, e, flush=True)
            continue
        enc = {k: (v.cuda() if hasattr(v, "cuda") else v) for k, v in enc.items()}
        outp = model(**enc)
        loss = outp.loss / a.accum
        loss.backward()
        run_loss += outp.loss.item()
        run_n += 1
        if (si + 1) % a.accum == 0:
            torch.nn.utils.clip_grad_norm_(params, 1.0)
            opt.step()
            sched.step()
            opt.zero_grad(set_to_none=True)
            step += 1
            if step % 10 == 0:
                el = time.time() - t0
                row = {"step": step, "samples": si + 1, "loss": round(run_loss / run_n, 4),
                       "lr": sched.get_last_lr()[0], "min": round(el / 60, 1),
                       "s_per_sample": round(el / (si + 1), 3),
                       "mem_gb": round(torch.cuda.max_memory_allocated() / 1e9, 1)}
                print(json.dumps(row), flush=True)
                log.write(json.dumps(row) + "\n")
                log.flush()
                run_loss, run_n = 0.0, 0
        if (si + 1) % a.save_every == 0:
            model.save_pretrained(out)
        if time.time() - t0 > a.minutes * 60:
            print(f"time box reached after {si + 1} samples", flush=True)
            break
    model.save_pretrained(out)
    meta = {"base": a.model, "arch": a.arch, "data": a.data, "samples": si + 1, "minutes": round((time.time() - t0) / 60, 1),
            "rank": a.rank, "lr": a.lr, "accum": a.accum, "max_pixels": a.max_pixels}
    (out / "r2_meta.json").write_text(json.dumps(meta, indent=1))
    print("saved", out, meta, flush=True)


if __name__ == "__main__":
    main()

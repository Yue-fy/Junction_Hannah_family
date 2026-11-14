"""Merge a LoRA adapter into its base VLM on the CPU and save a plain HF checkpoint (owner: R2).

Fallback for when vLLM cannot serve an adapter directly (e.g. a new architecture's LoRA layout): the merged
checkpoint is served like any base model (serving/start.sh with MODEL_PATH=<out>), no --enable-lora needed.
No GPU used. Example:
  /data/User/fangy4/envs/junction-train/bin/python experiments/r2/lora/merge_lora.py --arch gemma4 \
      --base $MODEL_DIR/hf/google/gemma-4-E4B-it --adapter $JUNCTION_SHARED/artifacts/R2/lora/gemma-cc-v1 \
      --out $MODEL_DIR/hf/local/gemma-4-E4B-it-gemma-cc-v1
"""
from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arch", choices=["qwen3vl", "gemma4"], required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    import torch
    from peft import PeftModel
    from transformers import AutoProcessor

    t0 = time.time()
    if a.arch == "gemma4":
        from transformers import AutoModelForImageTextToText as Cls
    else:
        from transformers import Qwen3VLForConditionalGeneration as Cls
    model = Cls.from_pretrained(a.base, dtype=torch.bfloat16, device_map="cpu")
    model = PeftModel.from_pretrained(model, a.adapter)
    model = model.merge_and_unload()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out, safe_serialization=True, max_shard_size="5GB")
    AutoProcessor.from_pretrained(a.base).save_pretrained(out)
    # keep the base's own chat template / generation config files byte-identical (vLLM reads them)
    for f in Path(a.base).iterdir():
        if f.is_file() and f.suffix in (".jinja", ".json", ".model", ".txt") and "safetensors" not in f.name \
                and f.name != "model.safetensors.index.json" and (f.name == "config.json" or not (out / f.name).exists()):
            shutil.copy2(f, out / f.name)  # config.json too: newer transformers re-serialise it in a form vLLM may not read
    (out / "R2_MERGED_FROM.txt").write_text(f"base={a.base}\nadapter={a.adapter}\n")
    print(f"merged -> {out} in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()

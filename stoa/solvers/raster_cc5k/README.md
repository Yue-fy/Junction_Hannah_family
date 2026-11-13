# raster_cc5k

Counts windows, doors, WC seats and sinks on raster floor plans with the pretrained **CubiCasa5K
multi-task model**. Each counted symbol comes back with a box (`image_px`) as evidence. CPU only, no LLM.

- Model and weights: A. Kalervo, J. Ylioinas, M. Häikiö, A. Karhu, J. Kannala, "CubiCasa5K: A Dataset and an
  Improved Multi-Task Model for Floorplan Image Analysis", SCIA 2019 (arXiv 1904.01920).
  Weights `model_best_val_loss_var.pkl` from https://github.com/CubiCasa/CubiCasa5k,
  **licensed CC BY-NC 4.0**. They are not in this repo; set `CC5K_WEIGHTS` to their path.
- Our code: `experiments/r1/cc5k_model/net.py` is our own re-implementation of the network. The checkpoint is
  loaded with `torch.load(weights_only=True)`, and no upstream code is executed.
- Env vars: `CC5K_WEIGHTS` (checkpoint path), `CC5K_PYTHON` (a python with torch, numpy, PIL, cv2; used for
  live inference), `CC5K_THREADS` (CPU threads, default 6).
- Leak rule (DECISIONS D3/D8): the model was trained on the original CubiCasa5K train list. Quote its
  accuracy from the `cc5k_heldout` split only. Measured there: windows 34%, doors 40%, WC seats 76%,
  sinks 60% (prior 14/10/55/46). Details: `research/methods.md` §3a.
- Commercial use of the weights needs a licence from CubiCasa, or retraining on licensed data.

"""Frozen CC5K counting settings (chosen on original CubiCasa5K VAL drawings; see count.py / calib.py).
template -> (icon class ids, min component area as a fraction of H*W, k×k opening kernel; 0 = none)."""
import json
import os

FROZEN = {"windows": ([1], 2e-4, 5), "doors": ([2], 2e-4, 0), "wc_seats": ([5], 2e-4, 5), "sinks": ([6], 2e-5, 5)}
CALIB = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "calib_plain.json")))


def confidence(template, count):
    tab = CALIB[template]["buckets"]
    return tab[str(min(count, max(int(b) for b in tab)))]["conf_model"]

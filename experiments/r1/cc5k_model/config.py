"""Frozen CC5K counting settings (chosen on original CubiCasa5K VAL drawings; see count.py / calib.py).
template -> (icon class ids, min component area as a fraction of H*W, k×k opening kernel; 0 = none)."""
import json
import os

FROZEN = {"windows": ([1], 2e-4, 5), "doors": ([2], 2e-4, 0), "wc_seats": ([5], 2e-4, 5), "sinks": ([6], 2e-5, 5)}
CALIB = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "calib_plain.json")))


def confidence(template, count):
    tab = CALIB[template]["buckets"]
    return tab[str(min(count, max(int(b) for b in tab)))]["conf_model"]

# Room-type region counts from the room map (classes: 1 Outdoor, 3 Kitchen, 5 Bed Room, 6 Bath), frozen on CC5K val.
# Best used as a CROSS-CHECK of label reading (agreement → pipeline right 92–96% on cc5k_heldout); alone it
# beats the pipeline only on bedrooms (test 67% vs 56%).
ROOMS_FROZEN = {"bedrooms": (5, 1.2e-2), "balconies": (1, 2.4e-2), "bathrooms": (6, 1.2e-2), "kitchens": (3, 1.6e-2)}

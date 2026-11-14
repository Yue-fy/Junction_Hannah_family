"""Held-out accuracy of guess_style by source and by confidence threshold (groups never seen in training)."""
import collections
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import style  # noqa: E402

ROOT = Path("/home/fangy4/work/projects/junction-data/stoa-full/junction-dataset")


def run(f):
    return f, style.guess_style(f)


if __name__ == "__main__":
    files = [f for f in style._files(ROOT, 600) if style._is_test(f)]
    with ProcessPoolExecutor(24) as ex:
        res = list(ex.map(run, files, chunksize=8))
    by = collections.defaultdict(lambda: [0, 0])
    conf = collections.Counter()
    for f, (c, p) in res:
        src = Path(f).parent.name
        ok = c == style._label(f)
        by[src][0] += 1
        by[src][1] += ok
        for t in (0.0, 0.6, 0.8, 0.9):
            if p >= t:
                conf[(t, "n")] += 1
                conf[(t, "ok")] += ok
    print({k: f"{v[1]}/{v[0]}" for k, v in by.items()})
    for t in (0.0, 0.6, 0.8, 0.9):
        print(f"p>={t}: coverage {conf[(t, 'n')]}/{len(res)}, accuracy {conf[(t, 'ok')] / max(1, conf[(t, 'n')]):.3f}")
    wrong = [(Path(f).parent.name + "/" + Path(f).name, c, round(p, 2)) for f, (c, p) in res if c != style._label(f) and p >= 0.8]
    print("confident wrong examples:", wrong[:12])

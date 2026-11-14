"""Won / lost / confidence moves between two red-team runs over the same rows: python3 redteam/compare.py OLD.jsonl NEW.jsonl
(rows rescored with analyze.rescore; a flag row "wins" when it leaves conf >= 0.8; CONF = same correctness, conf moved >= 0.25)."""
import json, sys
sys.path.insert(0, 'redteam')
from analyze import rescore
a = rescore([json.loads(l) for l in open(sys.argv[1])]); b = rescore([json.loads(l) for l in open(sys.argv[2])])
A = {r['qid']: r for r in a}
lost = won = 0
for r in b:
    x = A.get(r['qid'])
    if not x: continue
    cx, cy = x.get('correct'), r.get('correct')
    fx = x['meta']['expect'] == 'flag'
    if fx:
        hx, hy = (x['confidence'] or 0) >= 0.8, (r['confidence'] or 0) >= 0.8
        if hx != hy: print(('WON ' if hx else 'LOST'), f"[{r['meta']['kind']}] {r['question'][:80]!r}: {str(x['value'])[:30]} @{x['confidence']:.2f} -> {str(r['value'])[:30]} @{r['confidence']:.2f}")
        continue
    big = abs((x['confidence'] or 0) - (r['confidence'] or 0)) >= 0.25
    if cx != cy or (big and cy is not None):
        tag = 'WON ' if (cy and not cx) else 'LOST' if (cx and not cy) else 'CONF'
        won += tag == 'WON '; lost += tag == 'LOST'
        print(tag, f"[{r['meta']['kind']}] {r['question'][:80]!r}: {str(x['value'])[:30]} @{(x['confidence'] or 0):.2f} -> {str(r['value'])[:40]} @{(r['confidence'] or 0):.2f} ({r['solver']}) gold {str(r.get('gold'))[:15]}")
print('won', won, 'lost', lost)

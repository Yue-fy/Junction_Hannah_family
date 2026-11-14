"""Print a Swiss floor's room table from the DXF (for writing probe gold by hand).
Usage: PYTHONPATH=. python experiments/w2/op_probe/floor_table.py data/swiss_dwellings/<stem>.pdf"""
import sys

from stoa.solvers.vector.dxf_solver import DxfSolver
from stoa.solvers.vector.floor import window_count

s = DxfSolver(llm=0)
for p in sys.argv[1:]:
    fm, rel, _ = s._load(p)
    print(f"== {p}: {len(fm.rooms)} rooms, units {[u.label for u in fm.units]}, doors {len(fm.doors) if hasattr(fm, 'doors') else '?'}, "
          f"windows {window_count(fm)}")
    for r in sorted(fm.rooms, key=lambda r: (r.number or "zz")):
        print(f"  {r.number or '-':>6} {r.name or '':<22} {r.area:8.2f}  unit={r.unit} outdoor={r.outdoor} shaft={r.shaft}")

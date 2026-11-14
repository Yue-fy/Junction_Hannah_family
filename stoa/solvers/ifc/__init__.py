"""IFC solver package (W1): structured BIM questions answered from the model, evidence = GlobalIds.

- `ifc` solver: stoa/solvers/ifc/solver.py
- `load_index(path)` / `ifc_index(path)`: parsed model (storeys, elements, quantities, geometry), cached
- `plan_storey(path, idx)`: which storey a rendered `<model>_plan-NN-<level>.pdf` shows
"""

from stoa.solvers.ifc.index import IfcIndex, ifc_index, load_index  # noqa: F401
from stoa.solvers.ifc.solver import IfcSolver, model_for, plan_storey, plan_vs_model  # noqa: F401

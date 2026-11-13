"""Vector drawings: DXF layers, vector-PDF text, schedules (owner: W2).

Solvers registered here:
- `dxf`: swiss_dwellings floors (asked on .pdf/.png/.dxf), answered from the sibling DXF's layers
  (ROOM_OUTLINE, ROOM_TEXT, UNIT_OUTLINE, DOOR, WINDOW, FIXTURE), evidence mapped onto the asked file.

Modules:
- `floor.py`   DXF -> FloorModel (rooms, units, doors, windows, fixtures), cached per file
- `pdfmap.py`  DXF -> PDF page transform fitted from matching text, PDF -> PNG pixel scale
- `qparse.py`  multilingual question parser (EN/DE/FR/IT) -> small expression over primitives
- `dxf_solver.py` the `dxf` solver (+ table-QA fallback via `tableqa.py`)
- `pdffloor.py` PDF-only floor model (room polygons/doors/apartments by drawing style + printed scale)
- `pdftables.py` schedule tables rebuilt from a (rotated) PDF text layer
- `schedule_solver.py` the `schedule` solver: pdftables + tableqa
"""

from stoa.solvers.vector import dxf_solver  # noqa: F401  (registers "dxf")
from stoa.solvers.vector import schedule_solver  # noqa: F401  (registers "schedule")
# dxf_solver also registers "pdf_vector" (same rules, floor model read from the PDF alone: pdffloor.py)

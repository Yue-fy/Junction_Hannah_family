"""S0 D15 mechanism A, reproduced on a synthetic IFC (no test data): stair parts exported as IfcStair entities
aggregated under a parent IfcStair must be counted once per assembly; mechanism B: an explicit space
NetFloorArea wins over the shape."""

from __future__ import annotations

import pytest

ifcopenshell = pytest.importorskip("ifcopenshell")


def _model(path):
    import ifcopenshell.api as api

    f = api.run("project.create_file", version="IFC4")
    proj = api.run("root.create_entity", f, ifc_class="IfcProject", name="P")
    api.run("unit.assign_unit", f)
    site = api.run("root.create_entity", f, ifc_class="IfcSite", name="S")
    bld = api.run("root.create_entity", f, ifc_class="IfcBuilding", name="B")
    st = api.run("root.create_entity", f, ifc_class="IfcBuildingStorey", name="Level 1")
    api.run("aggregate.assign_object", f, relating_object=proj, products=[site])
    api.run("aggregate.assign_object", f, relating_object=site, products=[bld])
    api.run("aggregate.assign_object", f, relating_object=bld, products=[st])
    for i in range(2):  # two stair assemblies, each with 3 IfcStair parts
        parent = api.run("root.create_entity", f, ifc_class="IfcStair", name=f"Stair {i}")
        api.run("spatial.assign_container", f, relating_structure=st, products=[parent])
        kids = [api.run("root.create_entity", f, ifc_class="IfcStair", name=f"Stair {i} part {j}") for j in range(3)]
        api.run("aggregate.assign_object", f, relating_object=parent, products=kids)
    for i in range(3):
        api.run("spatial.assign_container", f, relating_structure=st,
                products=[api.run("root.create_entity", f, ifc_class="IfcDoor", name=f"D{i}")])
    f.write(str(path))
    return path


def test_nested_parts_counted_once(tmp_path):
    from stoa.solvers.ifc.index import nested_parts
    from stoa.solvers.ifc.solver import IfcSolver

    p = _model(tmp_path / "parts.ifc")
    parts = nested_parts(str(p))
    assert len(parts) == 6 and set(parts.values()) == {"IfcStair"}
    s = IfcSolver(plan2d="0", llm="0")
    a = s.solve(str(p), "How many stairs are there on 'Level 1'?")
    assert a.value == 2, a.trace
    assert any("parts of another stair" in t for t in a.trace)
    assert s.solve(str(p), "How many doors are there on 'Level 1'?").value == 3

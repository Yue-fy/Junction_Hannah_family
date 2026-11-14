"""A model with neighbour/context buildings whose storeys share the designed building's storey names
(IFC-Bench city_house_munich: '2. Erdgeschoss' in the house, 'Erdgeschoss' in two neighbours). W1 c5."""

from __future__ import annotations

import pytest

ifcopenshell = pytest.importorskip("ifcopenshell")


def _model(path):
    import ifcopenshell.api as api

    f = api.run("project.create_file", version="IFC4")
    proj = api.run("root.create_entity", f, ifc_class="IfcProject", name="P")
    api.run("unit.assign_unit", f)
    site = api.run("root.create_entity", f, ifc_class="IfcSite", name="S")
    api.run("aggregate.assign_object", f, relating_object=proj, products=[site])
    house = api.run("root.create_entity", f, ifc_class="IfcBuilding", name="House")
    nb = api.run("root.create_entity", f, ifc_class="IfcBuilding", name="Neighbor_A")
    api.run("aggregate.assign_object", f, relating_object=site, products=[house, nb])
    for bld, names, doors in ((house, ["1. Kellergeschoss", "2. Erdgeschoss"], 3), (nb, ["Kellergeschoss", "Erdgeschoss"], 1)):
        for k, n in enumerate(names):
            st = api.run("root.create_entity", f, ifc_class="IfcBuildingStorey", name=n)
            st.Elevation = -2.8 if k == 0 else 0.0
            api.run("aggregate.assign_object", f, relating_object=bld, products=[st])
            m = doors if k == 1 else 0
            for i in range(m):
                api.run("spatial.assign_container", f, relating_structure=st,
                        products=[api.run("root.create_entity", f, ifc_class="IfcDoor", name=f"{bld.Name} D{i}")])
            for i in range(3 if bld is house else 1):
                api.run("spatial.assign_container", f, relating_structure=st,
                        products=[api.run("root.create_entity", f, ifc_class="IfcWall", name=f"{bld.Name} W{k}{i}")])
    f.write(str(path))
    return path


def test_storey_name_shared_with_a_neighbour(tmp_path):
    from stoa.solvers.ifc.solver import IfcSolver

    p = str(_model(tmp_path / "multi.ifc"))
    s = IfcSolver(plan2d="0", llm="0")
    a = s.solve(p, "How many doors are on the Erdgeschoss?")
    assert a.value == 3 and a.confidence <= 0.75, a.trace
    assert any("main building 'House'" in t for t in a.trace)
    a = s.solve(p, "How many storeys does the building have?")
    assert a.value == 2 and a.confidence <= 0.75, a.trace
    assert s.solve(p, "How many doors does the building have?").value == 3
    a = s.solve(p, "How many doors are in the model?")
    assert a.value == 4 and a.confidence <= 0.75 and any("covers all" in m for m in a.missing)

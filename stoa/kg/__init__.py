"""Project knowledge graph (Stoa point 4: "different data don't talk to each other; linking them earns points").

    from stoa.kg import links, crosscheck, project_graph
    links("data/ifc_models/bsc-esplanades_1807-ep-ar-v18_plan-01-1-korrus.pdf")
        -> {"project", "kind", "model", "storey", "files", "storeys", "rooms", "same_building", "crosschecks",
            "nodes", "edges"}
    crosscheck(path, intent, answer) -> "IFC model: 46 IfcDoor on storey '1.korrus'; plan drawing: 46 door
        symbols; answer 46 ✓"  | None

What is linked (per project / building):
- ifc_models: the IFC model <-> every sheet rendered from it (plans, sections, elevations) <-> storeys (plan
  file -> IfcBuildingStorey) <-> rooms (IfcSpace: GUID, name, net area) <-> the room's polygon and label box on
  the plan (pdf_pt, via the SVG twin's data-guid) <-> elements (GUID) drawn on each plan; discipline models of
  the same project; the same building in ifc_bench (duplex, fzk_house, smiley_west, molio, digital_hub).
- ifc_bench: model <-> discipline models of the project <-> same building in ifc_models.
- swiss_dwellings: PDF <-> DXF <-> PNG of one floor (W2's DXF->PDF transform), rooms (number, name, DXF polygon
  area, printed area) with pdf_pt boxes, other floors of the same site.
- other sources: sibling formats only.

Graphs are cached as JSON under $JUNCTION_SHARED/artifacts/W1/kg/ (one file per project), for the UI and for
inspection; everything is recomputed from the (cached) IFC index if the JSON is missing.
"""

from stoa.kg.graph import crosscheck, links, project_graph  # noqa: F401

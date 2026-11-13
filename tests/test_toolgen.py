from simonto.toolgen import to_tools


def test_every_operation_becomes_a_tool(model):
    tools = to_tools(model)
    assert [t["name"] for t in tools] == list(model)


def test_schema_is_strict_and_typed(model):
    t = {t["name"]: t for t in to_tools(model)}["generate_mesh"]
    s = t["inputSchema"]
    assert s["additionalProperties"] is False
    assert s["required"] == ["global_size"]
    gs = s["properties"]["global_size"]
    assert gs["type"] == "number" and gs["minimum"] == 0.1 and gs["maximum"] == 500
    assert "Unit: mm" in gs["description"]
    assert s["properties"]["mesh_type"]["enum"] == ["hex_dominant", "poly", "tet"]
    assert s["properties"]["boundary_layers"]["type"] == "integer"


def test_annotations_reflect_ontology(model):
    t = {t["name"]: t for t in to_tools(model)}
    assert t["export_results"]["annotations"]["destructiveHint"] is True
    assert t["check_mesh_quality"]["annotations"]["readOnlyHint"] is True
    assert t["run_solver"]["annotations"]["readOnlyHint"] is False


def test_description_carries_prerequisites_and_flags(model):
    d = {t["name"]: t for t in to_tools(model)}["run_solver"]["description"]
    assert "Run first: configure_solver" in d and "long running" in d

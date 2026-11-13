from rdflib import Literal, RDF

from simonto.graph import SIM, ROOT, load_graph
from simonto.validate import find_cycles, graph_issues, shacl_issues, validate_all
from simonto.graph import load_model


def test_product_description_is_valid():
    assert validate_all() == []


def test_model_has_expected_operations(model):
    assert len(model) == 13
    assert model["generate_mesh"].kind == "PreprocessingOperation"
    assert model["train_surrogate"].kind == "SurrogateOperation"
    assert model["export_results"].destructive is True
    assert model["check_mesh_quality"].read_only is True


def test_shacl_catches_missing_output(graph):
    g = load_graph()
    g.remove((None, SIM.produces, None))
    msgs = [str(i) for i in shacl_issues(g)]
    assert any("produced artifact" in m for m in msgs)


def test_shacl_catches_enum_without_values():
    issues = validate_all(ROOT / "data" / "legacy_sample.ttl")
    text = "\n".join(map(str, issues))
    assert "Enum parameters must list" in text
    assert "must declare a sim:unit" in text
    assert "at least 40 characters" in text


def test_cycle_detection(model):
    from dataclasses import replace

    broken = dict(model)
    broken["import_geometry"] = replace(model["import_geometry"], requires=("run_solver",))
    assert find_cycles(broken)


def test_dangling_input_detected():
    issues = validate_all(ROOT / "data" / "legacy_sample.ttl")
    assert any(i.code == "dangling-input" for i in issues)


def test_default_outside_range_detected(graph, model):
    from dataclasses import replace

    op = model["generate_mesh"]
    bad = replace(op, params=tuple(replace(p, default=999) if p.name == "boundary_layers" else p for p in op.params))
    g = load_graph()
    issues = graph_issues(g, {**model, "generate_mesh": bad})
    assert any(i.code == "out-of-range" for i in issues)

import pytest

from simonto.planner import downstream, example_arguments, plan, prerequisites, to_mermaid


def names(ops):
    return [o.tool_name for o in ops]


def test_prerequisites_are_transitive(graph, model):
    assert prerequisites(graph, model, "run_solver") == {
        "import_geometry", "repair_geometry", "generate_mesh",
        "check_mesh_quality", "set_boundary_conditions", "configure_solver"}


def test_plan_respects_dependencies(graph, model):
    order = names(plan(graph, model, "predict_with_surrogate"))
    assert order[0] == "import_geometry" and order[-1] == "predict_with_surrogate"
    pos = {t: i for i, t in enumerate(order)}
    for t in order:
        for r in model[t].requires:
            assert pos[r] < pos[t]


def test_plan_is_deterministic(graph, model):
    assert names(plan(graph, model, "export_results")) == names(plan(graph, model, "export_results"))


def test_plan_for_root_is_single_step(graph, model):
    assert names(plan(graph, model, "import_geometry")) == ["import_geometry"]


def test_impact_analysis(graph, model):
    assert "train_surrogate" in downstream(graph, model, "generate_mesh")
    assert downstream(graph, model, "predict_with_surrogate") == set()


def test_unknown_operation(graph, model):
    with pytest.raises(KeyError):
        plan(graph, model, "does_not_exist")


def test_example_arguments_cover_required(model):
    for op in model.values():
        assert set(example_arguments(op)) == {p.name for p in op.params if p.required}


def test_mermaid_has_edges(model):
    m = to_mermaid(model)
    assert m.startswith("flowchart LR") and "generate_mesh --> check_mesh_quality" in m

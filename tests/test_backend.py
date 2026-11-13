import pytest

from simonto.backend import SimulatedBackend, ToolError, check_args
from simonto.planner import example_arguments, plan


@pytest.fixture
def be(model):
    return SimulatedBackend(model)


def run_plan(be, graph, model, goal):
    for op in plan(graph, model, goal)[:-1]:
        be.call(op.tool_name, example_arguments(op))


def test_prerequisite_enforced_with_actionable_hint(be):
    with pytest.raises(ToolError) as e:
        be.call("generate_mesh", {"global_size": 25})
    assert e.value.code == "missing_prerequisite" and "ontology_plan_workflow" in e.value.hint


def test_argument_validation(model):
    op = model["generate_mesh"]
    _, errs = check_args(op, {"global_size": 0.01, "mesh_type": "quad", "boundary_layers": 2.5, "bogus": 1})
    text = " ".join(errs)
    assert "below the minimum 0.1 mm" in text and "not one of" in text
    assert "must be an integer" in text and "unknown parameter 'bogus'" in text


def test_bool_is_not_a_number(model):
    _, errs = check_args(model["generate_mesh"], {"global_size": True})
    assert errs


def test_defaults_applied(model):
    full, errs = check_args(model["generate_mesh"], {"global_size": 25})
    assert not errs and full["boundary_layers"] == 10 and full["mesh_type"] == "poly"


def test_happy_path_and_state(be, graph, model):
    run_plan(be, graph, model, "extract_forces")
    r = be.call("extract_forces", {"reference_area": 1.8})
    assert r["simulated"] is True and "ForceCoefficients" in be.state()["artifacts"]


def test_dry_run_changes_nothing(be):
    r = be.call("import_geometry", {"file_path": "a.step"}, dry_run=True)
    assert r["dry_run"] and be.state()["artifacts"] == []


def test_failed_quality_check_blocks_solver_setup(be, graph, model):
    for t, a in [("import_geometry", {"file_path": "a.step"}), ("repair_geometry", {}),
                 ("generate_mesh", {"global_size": 400}), ("set_boundary_conditions", {"inlet_velocity": 60})]:
        be.call(t, a)
    r = be.call("check_mesh_quality", {})
    assert r["passed"] is False and "MeshQualityReport" not in be.state()["artifacts"]
    with pytest.raises(ToolError) as e:
        be.call("configure_solver", {})
    assert e.value.code == "missing_prerequisite"


def test_results_are_deterministic(model, graph):
    out = []
    for _ in range(2):
        b = SimulatedBackend(model)
        run_plan(b, graph, model, "extract_forces")
        out.append(b.call("extract_forces", {"reference_area": 1.8}))
    assert out[0] == out[1]

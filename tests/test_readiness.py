from simonto.graph import ROOT, load_graph, load_model
from simonto.readiness import overall, review, to_markdown


def test_scores_in_range(model):
    scores = review(model)
    assert all(0 <= s.score <= 100 for s in scores) and overall(scores) > 90


def test_legacy_surface_scores_much_lower(model):
    legacy = review(load_model(load_graph(ROOT / "data" / "legacy_sample.ttl")))
    assert overall(legacy) < overall(review(model)) - 25
    run_it = next(s for s in legacy if s.tool == "run_it")
    assert any("missing unit" in f for f in run_it.findings)


def test_markdown_report(model):
    md = to_markdown(review(model))
    assert md.startswith("# Agentic-readiness report") and "| Check | Points |" in md

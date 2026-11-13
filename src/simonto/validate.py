"""Validation: SHACL shapes (structure) + graph checks SHACL cannot express."""
from __future__ import annotations

from dataclasses import dataclass

from pyshacl import validate as shacl_validate
from rdflib import Graph

from .graph import Operation, load_graph, load_model, load_shapes


@dataclass(frozen=True)
class Issue:
    severity: str  # error | warning
    code: str
    message: str

    def __str__(self) -> str:
        return f"[{self.severity.upper()}] {self.code}: {self.message}"


def shacl_issues(g: Graph) -> list[Issue]:
    conforms, results_graph, _ = shacl_validate(
        g, shacl_graph=load_shapes(), inference="rdfs", abort_on_first=False, meta_shacl=False
    )
    if conforms:
        return []
    from rdflib.namespace import SH

    issues = []
    for r in results_graph.subjects(None, SH.ValidationResult):
        msg = results_graph.value(r, SH.resultMessage)
        node = results_graph.value(r, SH.focusNode)
        issues.append(Issue("error", "shacl", f"{msg} (focus: {str(node).rsplit('#', 1)[-1]})"))
    return sorted(issues, key=str)


def find_cycles(model: dict[str, Operation]) -> list[list[str]]:
    """Prerequisite cycles make a workflow unrunnable."""
    cycles, state = [], {}

    def visit(n, path):
        state[n] = 1
        for m in model[n].requires:
            if m not in model:
                continue
            if state.get(m) == 1:
                cycles.append(path[path.index(m):] + [m] if m in path else [n, m])
            elif m not in state:
                visit(m, path + [m])
        state[n] = 2

    for n in model:
        if n not in state:
            visit(n, [n])
    return cycles


def graph_issues(g: Graph, model: dict[str, Operation]) -> list[Issue]:
    issues: list[Issue] = []
    produced = {a for op in model.values() for a in op.produces}

    for cyc in find_cycles(model):
        issues.append(Issue("error", "cycle", "prerequisite cycle: " + " -> ".join(cyc)))

    for op in model.values():
        for art in op.consumes:
            if art not in produced:
                issues.append(Issue("error", "dangling-input",
                                    f"{op.tool_name} consumes {art}, which no operation produces"))
        if op.kind == "Operation":
            issues.append(Issue("warning", "untyped-kind",
                                f"{op.tool_name} is not typed as a Preprocessing/Solve/Postprocessing/Surrogate operation"))
        for p in op.params:
            if p.type in ("number", "integer") and p.minimum is not None and p.maximum is not None:
                for label, v in (("default", p.default), ("example", p.example)):
                    if isinstance(v, (int, float)) and not isinstance(v, bool) and not (p.minimum <= v <= p.maximum):
                        issues.append(Issue("error", "out-of-range",
                                            f"{op.tool_name}.{p.name} {label} {v} outside [{p.minimum}, {p.maximum}]"))
            if p.type == "enum":
                for label, v in (("default", p.default), ("example", p.example)):
                    if v is not None and str(v) not in p.allowed:
                        issues.append(Issue("error", "enum-violation",
                                            f"{op.tool_name}.{p.name} {label} '{v}' not in {list(p.allowed)}"))
    return issues


def validate_all(data_file=None) -> list[Issue]:
    g = load_graph(data_file)
    return shacl_issues(g) + graph_issues(g, load_model(g))

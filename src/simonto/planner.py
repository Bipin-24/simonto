"""Workflow planning and impact analysis, answered with SPARQL over the graph.

The transitive `sim:requiresOperation` property means "what must run first?"
is a property-path query, not hand-written orchestration logic.
"""
from __future__ import annotations

from rdflib import Graph

from .graph import SIM, Operation, _local

_PREREQ_CLOSURE = """
SELECT DISTINCT ?pre WHERE { ?op sim:requiresOperation+ ?pre }
"""

_DOWNSTREAM = """
SELECT DISTINCT ?down WHERE { ?down sim:requiresOperation+ ?op }
"""

_PRODUCERS = """
SELECT DISTINCT ?op WHERE { ?op sim:produces ?artifact }
"""


def _iri(model: dict[str, Operation], tool: str):
    from rdflib import URIRef

    if tool not in model:
        raise KeyError(f"unknown operation '{tool}'. Known: {', '.join(model)}")
    return URIRef(model[tool].iri)


def _tool_of(model, iri) -> str:
    for t, op in model.items():
        if op.iri == str(iri):
            return t
    raise KeyError(iri)


def prerequisites(g: Graph, model: dict[str, Operation], tool: str) -> set[str]:
    rows = g.query(_PREREQ_CLOSURE, initNs={"sim": SIM}, initBindings={"op": _iri(model, tool)})
    return {_tool_of(model, r[0]) for r in rows}


def downstream(g: Graph, model: dict[str, Operation], tool: str) -> set[str]:
    """Impact analysis: everything that (transitively) depends on `tool`."""
    rows = g.query(_DOWNSTREAM, initNs={"sim": SIM}, initBindings={"op": _iri(model, tool)})
    return {_tool_of(model, r[0]) for r in rows}


def plan(g: Graph, model: dict[str, Operation], goal: str) -> list[Operation]:
    """Ordered list of operations to run so that `goal` can run (goal last).

    Kahn's algorithm over the prerequisite sub-graph; ties are broken
    alphabetically so plans are deterministic.
    """
    needed = prerequisites(g, model, goal) | {goal}
    indeg = {t: len([r for r in model[t].requires if r in needed]) for t in needed}
    ready = sorted(t for t, d in indeg.items() if d == 0)
    order: list[str] = []
    while ready:
        t = ready.pop(0)
        order.append(t)
        for u in sorted(needed):
            if t in model[u].requires:
                indeg[u] -= 1
                if indeg[u] == 0:
                    ready.append(u)
                    ready.sort()
    if len(order) != len(needed):
        raise ValueError("prerequisite cycle detected; run `simonto validate`")
    return [model[t] for t in order]


def example_arguments(op: Operation) -> dict:
    """Required parameters filled from sim:example values (for docs, demos, tests)."""
    return {p.name: p.example for p in op.params if p.required and p.example is not None}


def lineage(model: dict[str, Operation], artifact: str) -> list[str]:
    """Which operations produce / consume an artifact."""
    out = [f"{t} produces {artifact}" for t, op in model.items() if artifact in op.produces]
    out += [f"{t} consumes {artifact}" for t, op in model.items() if artifact in op.consumes]
    return out


def to_mermaid(model: dict[str, Operation]) -> str:
    """Prerequisite graph as a Mermaid flowchart, grouped by operation kind."""
    groups: dict[str, list[str]] = {}
    for t, op in model.items():
        groups.setdefault(op.kind, []).append(t)
    lines = ["flowchart LR"]
    for kind, tools in groups.items():
        lines.append(f'  subgraph {kind}["{kind}"]')
        for t in tools:
            shape = ("[[%s]]" if model[t].long_running else "[%s]") % t
            lines.append(f"    {t}{shape}")
        lines.append("  end")
    for t, op in model.items():
        for r in op.requires:
            lines.append(f"  {r} --> {t}")
    return "\n".join(lines)

"""Agentic-readiness review: how safely could an LLM agent discover and call each operation?

Heuristic rubric (documented, deterministic, 100 points per operation). It is a
review aid for ontology authors, not a guarantee of agent behaviour.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .graph import Operation

RUBRIC = [
    ("description", 15, "Description is specific (>= 60 chars) so an LLM can pick the right tool"),
    ("parameters_documented", 15, "Every parameter has a description of >= 20 chars"),
    ("units", 10, "Every numeric parameter declares a unit"),
    ("bounds", 15, "Every numeric parameter declares min and max (safe ranges)"),
    ("enums", 10, "Enum parameters list allowed values (checked by SHACL; partial credit otherwise)"),
    ("side_effects", 10, "Destructive / long-running flags are declared"),
    ("outputs", 10, "At least one typed output artifact is declared"),
    ("prerequisites", 15, "Every consumed artifact's producer is a declared (transitive) prerequisite"),
]


@dataclass
class OpScore:
    tool: str
    score: int
    findings: list[str] = field(default_factory=list)


def _producers(model):
    prod: dict[str, set[str]] = {}
    for t, op in model.items():
        for a in op.produces:
            prod.setdefault(a, set()).add(t)
    return prod


def _closure(model, tool, seen=None):
    seen = seen if seen is not None else set()
    for r in model[tool].requires:
        if r not in seen:
            seen.add(r)
            _closure(model, r, seen)
    return seen


def score_operation(model: dict[str, Operation], op: Operation) -> OpScore:
    pts, notes = 0, []
    weights = {k: w for k, w, _ in RUBRIC}

    if len(op.description) >= 60:
        pts += weights["description"]
    else:
        notes.append(f"description is {len(op.description)} chars; aim for >= 60")

    short = [p.name for p in op.params if len(p.description) < 20]
    if not short:
        pts += weights["parameters_documented"]
    else:
        pts += weights["parameters_documented"] * (1 - len(short) / len(op.params))
        notes.append("thin parameter descriptions: " + ", ".join(short))

    nums = [p for p in op.params if p.type in ("number", "integer")]
    if nums:
        no_unit = [p.name for p in nums if not p.unit]
        no_bounds = [p.name for p in nums if p.minimum is None or p.maximum is None]
        pts += weights["units"] * (1 - len(no_unit) / len(nums))
        pts += weights["bounds"] * (1 - len(no_bounds) / len(nums))
        if no_unit:
            notes.append("missing unit: " + ", ".join(no_unit))
        if no_bounds:
            notes.append("missing min/max: " + ", ".join(no_bounds))
    else:
        pts += weights["units"] + weights["bounds"]

    enums = [p for p in op.params if p.type == "enum"]
    if all(p.allowed for p in enums):
        pts += weights["enums"]
    else:
        notes.append("enum without allowed values")

    pts += weights["side_effects"]  # flags are mandatory in the model (SHACL); full credit when loaded

    if op.produces:
        pts += weights["outputs"]
    else:
        notes.append("no output artifact declared")

    prod = _producers(model)
    closure = _closure(model, op.tool_name)
    missing = [a for a in op.consumes if not (prod.get(a, set()) & closure)]
    if not missing:
        pts += weights["prerequisites"]
    else:
        notes.append("consumes " + ", ".join(missing) + " without a declared prerequisite that produces it")

    return OpScore(op.tool_name, round(pts), notes)


def review(model: dict[str, Operation]) -> list[OpScore]:
    return [score_operation(model, op) for op in model.values()]


def overall(scores: list[OpScore]) -> float:
    return round(sum(s.score for s in scores) / len(scores), 1) if scores else 0.0


def to_markdown(scores: list[OpScore]) -> str:
    lines = [
        "# Agentic-readiness report",
        "",
        f"**Overall: {overall(scores)} / 100** across {len(scores)} operations.",
        "",
        "| Operation | Score | Findings |",
        "|---|---:|---|",
    ]
    for s in sorted(scores, key=lambda s: (s.score, s.tool)):
        lines.append(f"| `{s.tool}` | {s.score} | {'; '.join(s.findings) or '-'} |")
    lines += ["", "## Rubric", "", "| Check | Points | Meaning |", "|---|---:|---|"]
    lines += [f"| {k} | {w} | {m} |" for k, w, m in RUBRIC]
    return "\n".join(lines) + "\n"

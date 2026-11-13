"""Generate agent-facing tool definitions (MCP `tools/list` shape) from the ontology."""
from __future__ import annotations

from .graph import Operation, Param


def param_schema(p: Param) -> dict:
    t = {"number": "number", "integer": "integer", "string": "string",
         "boolean": "boolean", "enum": "string"}[p.type]
    desc = p.description
    if p.unit and p.unit not in ("dimensionless", "count"):
        desc += f" Unit: {p.unit}."
    s: dict = {"type": t, "description": desc}
    if p.type == "enum":
        s["enum"] = list(p.allowed)
    if p.minimum is not None:
        s["minimum"] = p.minimum
    if p.maximum is not None:
        s["maximum"] = p.maximum
    if p.default is not None:
        s["default"] = p.default
    return s


def input_schema(op: Operation) -> dict:
    schema = {
        "type": "object",
        "properties": {p.name: param_schema(p) for p in op.params},
        "additionalProperties": False,
    }
    req = [p.name for p in op.params if p.required]
    if req:
        schema["required"] = req
    return schema


def tool_description(op: Operation) -> str:
    parts = [op.description.rstrip(".") + "."]
    if op.requires:
        parts.append("Run first: " + ", ".join(op.requires) + ".")
    if op.produces:
        parts.append("Produces: " + ", ".join(op.produces) + ".")
    flags = []
    if op.read_only:
        flags.append("read-only")
    if op.destructive:
        flags.append("can overwrite data")
    if op.long_running:
        flags.append("long running")
    if flags:
        parts.append("Note: " + ", ".join(flags) + ".")
    return " ".join(parts)


def to_tool(op: Operation) -> dict:
    return {
        "name": op.tool_name,
        "description": tool_description(op),
        "inputSchema": input_schema(op),
        "annotations": {
            "title": op.label,
            "readOnlyHint": op.read_only,
            "destructiveHint": op.destructive,
            "idempotentHint": op.idempotent,
            "openWorldHint": False,
        },
    }


def to_tools(model: dict[str, Operation]) -> list[dict]:
    return [to_tool(op) for op in model.values()]

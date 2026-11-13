"""A dependency-free Model Context Protocol (MCP) server over stdio.

Implements the subset of MCP an agent needs to discover and call tools:
`initialize`, `ping`, `tools/list`, `tools/call` (JSON-RPC 2.0, newline-delimited).
Tool definitions are generated from the ontology; calls go to the simulated backend.

Besides one tool per ontology operation, it exposes four *ontology-aware* meta tools
so an agent can reason about the product before acting:
  ontology_list_operations, ontology_describe_operation,
  ontology_plan_workflow, ontology_impact_analysis, session_state
"""
from __future__ import annotations

import json
import sys
from typing import IO

from . import __version__
from .backend import SimulatedBackend, ToolError
from .graph import load_graph, load_model
from .planner import downstream, example_arguments, plan, prerequisites
from .toolgen import to_tool, to_tools

SUPPORTED_PROTOCOLS = ["2025-03-26", "2024-11-05"]


def _meta_tools(names: list[str]) -> list[dict]:
    op_enum = {"type": "string", "enum": names, "description": "Operation (tool) name."}
    obj = lambda props, req: {"type": "object", "properties": props, "required": req, "additionalProperties": False}
    ro = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
    return [
        {"name": "ontology_list_operations",
         "description": "List every operation the product exposes, grouped by kind, with one-line descriptions and prerequisites. Start here.",
         "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
         "annotations": {"title": "List operations", **ro}},
        {"name": "ontology_describe_operation",
         "description": "Full ontology facts for one operation: parameters with units and bounds, consumed and produced artifacts, prerequisites, side effects.",
         "inputSchema": obj({"name": op_enum}, ["name"]), "annotations": {"title": "Describe operation", **ro}},
        {"name": "ontology_plan_workflow",
         "description": "Ordered list of operations (with example arguments for required parameters) needed before and including the goal operation.",
         "inputSchema": obj({"goal": {**op_enum, "description": "The operation you ultimately want to run."}}, ["goal"]),
         "annotations": {"title": "Plan workflow", **ro}},
        {"name": "ontology_impact_analysis",
         "description": "Which operations depend, directly or transitively, on the given operation. Use before re-running or changing a step.",
         "inputSchema": obj({"name": op_enum}, ["name"]), "annotations": {"title": "Impact analysis", **ro}},
        {"name": "session_state",
         "description": "Artifacts that exist in the current session and the operations already run.",
         "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
         "annotations": {"title": "Session state", **ro}},
    ]


def _with_dry_run(tool: dict) -> dict:
    """Every operation gets a protocol-level `dry_run` flag: validate and preview without executing."""
    props = {**tool["inputSchema"]["properties"],
             "dry_run": {"type": "boolean", "default": False,
                         "description": "Validate arguments and prerequisites and preview the effect without executing."}}
    return {**tool, "inputSchema": {**tool["inputSchema"], "properties": props}}


class McpServer:
    def __init__(self, data_file=None):
        self.g = load_graph(data_file)
        self.model = load_model(self.g)
        self.backend = SimulatedBackend(self.model)
        self.tools = [_with_dry_run(t) for t in to_tools(self.model)] + _meta_tools(list(self.model))

    # ---- JSON-RPC plumbing -------------------------------------------------

    def handle(self, msg: dict) -> dict | None:
        mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
        is_notification = "id" not in msg
        try:
            if method == "initialize":
                want = params.get("protocolVersion")
                result = {
                    "protocolVersion": want if want in SUPPORTED_PROTOCOLS else SUPPORTED_PROTOCOLS[-1],
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "simonto-aeroflow", "version": __version__},
                    "instructions": ("Tools mirror an ontology of the (fictional, simulated) AeroFlow CFD product. "
                                     "Call ontology_plan_workflow before running an operation whose prerequisites are unclear."),
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": self.tools}
            elif method == "tools/call":
                result = self._call(params.get("name"), params.get("arguments") or {})
            elif is_notification:
                return None  # e.g. notifications/initialized
            else:
                return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}
        except Exception as exc:  # protocol-level failure, not a tool error
            return None if is_notification else {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": str(exc)}}
        return None if is_notification else {"jsonrpc": "2.0", "id": mid, "result": result}

    def serve(self, stdin: IO[str] = sys.stdin, stdout: IO[str] = sys.stdout) -> None:
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
            else:
                resp = self.handle(msg)
            if resp is not None:
                stdout.write(json.dumps(resp) + "\n")
                stdout.flush()

    # ---- tools/call --------------------------------------------------------

    def _call(self, name: str, args: dict) -> dict:
        try:
            if name in self.model:
                args = dict(args)
                dry = bool(args.pop("dry_run", False))
                payload = self.backend.call(name, args, dry_run=dry)
            else:
                payload = self._meta(name, args)
            return {"content": [{"type": "text", "text": json.dumps(payload, indent=2)}], "isError": False}
        except ToolError as e:
            return {"content": [{"type": "text", "text": json.dumps(e.to_dict(), indent=2)}], "isError": True}

    def _need(self, args, key):
        v = args.get(key)
        if v not in self.model:
            raise ToolError("invalid_arguments", f"'{key}' must be one of {list(self.model)}")
        return v

    def _meta(self, name: str, args: dict) -> dict:
        m = self.model
        if name == "ontology_list_operations":
            out: dict[str, list] = {}
            for t, op in m.items():
                out.setdefault(op.kind, []).append({"name": t, "summary": op.description, "requires": list(op.requires)})
            return out
        if name == "ontology_describe_operation":
            op = m[self._need(args, "name")]
            return {**to_tool(op), "kind": op.kind, "consumes": list(op.consumes), "produces": list(op.produces),
                    "requires": list(op.requires), "invocation": op.invocation, "longRunning": op.long_running,
                    "parameters": [{"name": p.name, "type": p.type, "required": p.required, "unit": p.unit,
                                    "min": p.minimum, "max": p.maximum, "allowed": list(p.allowed), "default": p.default}
                                   for p in op.params]}
        if name == "ontology_plan_workflow":
            goal = self._need(args, "goal")
            steps = plan(self.g, m, goal)
            return {"goal": goal, "steps": [
                {"step": i + 1, "tool": o.tool_name, "arguments": example_arguments(o),
                 "already_done": all(a in self.backend.artifacts for a in o.produces)}
                for i, o in enumerate(steps)]}
        if name == "ontology_impact_analysis":
            t = self._need(args, "name")
            return {"operation": t, "depends_on_it": sorted(downstream(self.g, m, t)),
                    "it_depends_on": sorted(prerequisites(self.g, m, t))}
        if name == "session_state":
            return self.backend.state()
        raise ToolError("unknown_tool", f"no tool named '{name}'")


def main() -> None:
    McpServer().serve()


if __name__ == "__main__":
    main()

"""Command line interface: `python -m simonto <command>`."""
from __future__ import annotations

import argparse
import json
import sys

from .backend import SimulatedBackend, ToolError
from .graph import load_graph, load_model
from .planner import downstream, example_arguments, plan, prerequisites, to_mermaid
from .readiness import overall, review, to_markdown
from .toolgen import to_tools
from .validate import validate_all


def cmd_validate(a) -> int:
    issues = validate_all(a.data)
    for i in issues:
        print(i)
    errors = [i for i in issues if i.severity == "error"]
    g = load_graph(a.data)
    print(f"{len(load_model(g))} operations, {len(g)} triples: "
          f"{'FAILED' if errors else 'OK'} ({len(errors)} errors, {len(issues) - len(errors)} warnings)")
    return 1 if errors else 0


def cmd_tools(a) -> int:
    json.dump({"tools": to_tools(load_model(load_graph(a.data)))}, sys.stdout, indent=2)
    print()
    return 0


def cmd_plan(a) -> int:
    g = load_graph(a.data); m = load_model(g)
    for i, op in enumerate(plan(g, m, a.goal), 1):
        print(f"{i:>2}. {op.tool_name:<24} {json.dumps(example_arguments(op))}")
    return 0


def cmd_impact(a) -> int:
    g = load_graph(a.data); m = load_model(g)
    print(f"{a.name} depends on : {sorted(prerequisites(g, m, a.name)) or '-'}")
    print(f"{a.name} is needed by: {sorted(downstream(g, m, a.name)) or '-'}")
    return 0


def cmd_readiness(a) -> int:
    scores = review(load_model(load_graph(a.data)))
    if a.markdown:
        sys.stdout.write(to_markdown(scores))
    else:
        for s in sorted(scores, key=lambda s: s.score):
            print(f"{s.score:>3}  {s.tool:<24} {'; '.join(s.findings)}")
        print(f"overall {overall(scores)} / 100")
    return 0


def cmd_diagram(a) -> int:
    print(to_mermaid(load_model(load_graph(a.data))))
    return 0


def cmd_query(a) -> int:
    g = load_graph(a.data)
    q = open(a.file).read() if a.file else a.sparql
    for row in g.query(q, initNs={"sim": __import__("simonto.graph", fromlist=["SIM"]).SIM}):
        print("\t".join(str(c).rsplit("#", 1)[-1] for c in row))
    return 0


def cmd_demo(a) -> int:
    """A scripted 'agent' that plans against the ontology, hits errors, recovers and finishes."""
    g = load_graph(a.data); m = load_model(g)
    be = SimulatedBackend(m)

    def show(tool, args, **kw):
        print(f"\n> {tool} {json.dumps(args)}")
        try:
            r = be.call(tool, args, **kw)
            print("  ok:", json.dumps({k: v for k, v in r.items() if k not in ('simulated',)}))
            return r
        except ToolError as e:
            print(f"  ERROR {e.code}: {e.message}" + (f"\n  hint: {e.hint}" if e.hint else ""))
            return None

    print("Goal: predict lift/drag at 60 m/s, 4 deg AoA with a trained surrogate.")
    print("\n[1] Naive attempt - skip the workflow:")
    show("predict_with_surrogate", {"inlet_velocity": 60, "angle_of_attack": 4})

    print("\n[2] Ask the ontology for a plan:")
    steps = plan(g, m, "predict_with_surrogate")
    for i, op in enumerate(steps, 1):
        print(f"  {i:>2}. {op.tool_name}")

    print("\n[3] Bad argument is rejected with units and range:")
    show("generate_mesh", {"global_size": 0.01})

    print("\n[4] Execute the plan (sweeping 12 design points to feed the surrogate):")
    ex = {s.tool_name: example_arguments(s) for s in steps}
    for op in steps[:-3]:
        show(op.tool_name, ex[op.tool_name])
    for i in range(12):
        aoa = -6 + i
        show("set_boundary_conditions", {"inlet_velocity": 60, "angle_of_attack": aoa}) if i in (0, 11) else \
            be.call("set_boundary_conditions", {"inlet_velocity": 60, "angle_of_attack": aoa})
        be.call("configure_solver", {}); be.call("run_solver", {})
        be.call("extract_forces", {"reference_area": 1.8})
        be.call("record_design_point", {"dataset_path": "doe/wing_sweep.csv"})
    print("\n  ... 12 design points recorded.")
    show("train_surrogate", {})
    show("predict_with_surrogate", {"inlet_velocity": 60, "angle_of_attack": 4})
    return 0


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="simonto", description=__doc__)
    p.add_argument("--data", help="product description (Turtle); default: data/aeroflow.ttl")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate", help="SHACL + graph checks").set_defaults(fn=cmd_validate)
    sub.add_parser("tools", help="emit MCP tool definitions as JSON").set_defaults(fn=cmd_tools)
    s = sub.add_parser("plan", help="ordered workflow for a goal operation"); s.add_argument("goal"); s.set_defaults(fn=cmd_plan)
    s = sub.add_parser("impact", help="upstream/downstream of an operation"); s.add_argument("name"); s.set_defaults(fn=cmd_impact)
    s = sub.add_parser("readiness", help="agentic-readiness review"); s.add_argument("--markdown", action="store_true"); s.set_defaults(fn=cmd_readiness)
    sub.add_parser("diagram", help="Mermaid prerequisite graph").set_defaults(fn=cmd_diagram)
    s = sub.add_parser("query", help="run SPARQL (prefix sim: is predefined)"); s.add_argument("sparql", nargs="?"); s.add_argument("-f", "--file"); s.set_defaults(fn=cmd_query)
    sub.add_parser("demo", help="scripted agent walkthrough on the simulated backend").set_defaults(fn=cmd_demo)
    s = sub.add_parser("serve", help="run the MCP server on stdio")
    s.set_defaults(fn=lambda a: __import__("simonto.mcp_server", fromlist=["McpServer"]).McpServer(a.data).serve() or 0)
    args = p.parse_args(argv)
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()

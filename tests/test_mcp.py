"""End-to-end: spawn the server as a real subprocess and speak JSON-RPC over stdio."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SRC = str(Path(__file__).resolve().parents[1] / "src")


class Client:
    def __init__(self):
        self.p = subprocess.Popen([sys.executable, "-m", "simonto", "serve"], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, text=True, env={"PYTHONPATH": SRC, "PATH": ""})
        self.n = 0

    def rpc(self, method, params=None):
        self.n += 1
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params or {}}) + "\n")
        self.p.stdin.flush()
        return json.loads(self.p.stdout.readline())

    def notify(self, method):
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}) + "\n")
        self.p.stdin.flush()

    def call(self, tool, **args):
        r = self.rpc("tools/call", {"name": tool, "arguments": args})["result"]
        return r["isError"], json.loads(r["content"][0]["text"])

    def close(self):
        self.p.stdin.close(); self.p.wait(timeout=10)


@pytest.fixture
def client():
    c = Client()
    yield c
    c.close()


def test_handshake_and_listing(client):
    init = client.rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}})
    assert init["result"]["serverInfo"]["name"] == "simonto-aeroflow"
    assert init["result"]["capabilities"]["tools"] is not None
    client.notify("notifications/initialized")  # must not produce a response
    tools = client.rpc("tools/list")["result"]["tools"]
    names = {t["name"] for t in tools}
    assert {"generate_mesh", "ontology_plan_workflow", "session_state"} <= names and len(tools) == 18
    gm = next(t for t in tools if t["name"] == "generate_mesh")
    assert "dry_run" in gm["inputSchema"]["properties"]


def test_agent_recovers_from_error_using_ontology(client):
    client.rpc("initialize", {"protocolVersion": "2024-11-05"})
    is_err, body = client.call("run_solver")
    assert is_err and body["error"] == "missing_prerequisite"
    is_err, plan = client.call("ontology_plan_workflow", goal="run_solver")
    assert not is_err and plan["steps"][0]["tool"] == "import_geometry"
    for step in plan["steps"]:
        is_err, _ = client.call(step["tool"], **step["arguments"])
        assert not is_err, step
    is_err, body = client.call("run_solver")
    assert not is_err and body["simulated"] is True and "SolutionFields" in body["produced"]


def test_protocol_errors(client):
    assert client.rpc("nope")["error"]["code"] == -32601
    client.p.stdin.write("not json\n"); client.p.stdin.flush()
    assert json.loads(client.p.stdout.readline())["error"]["code"] == -32700
    assert client.rpc("ping")["result"] == {}


def test_impact_tool(client):
    client.rpc("initialize", {})
    _, body = client.call("ontology_impact_analysis", name="run_solver")
    assert "train_surrogate" in body["depends_on_it"] and "configure_solver" in body["it_depends_on"]

"""Load the ontology + product description and expose a typed Python model.

The RDF graph is the single source of truth. Everything else in this package
(tool schemas, plans, readiness scores, the MCP server) is derived from it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rdflib import RDF, RDFS, Graph, Namespace, URIRef

SIM = Namespace("https://github.com/Bipin-24/simonto#")
ROOT = Path(__file__).resolve().parents[2]
ONTOLOGY_FILE = ROOT / "ontology" / "simonto.ttl"
SHAPES_FILE = ROOT / "ontology" / "shapes.ttl"
DEFAULT_DATA_FILE = ROOT / "data" / "aeroflow.ttl"


@dataclass(frozen=True)
class Param:
    name: str
    label: str
    description: str
    type: str  # number | integer | string | boolean | enum
    required: bool
    unit: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    allowed: tuple[str, ...] = ()
    default: Any = None
    example: Any = None


@dataclass(frozen=True)
class Operation:
    iri: str
    tool_name: str
    label: str
    description: str
    kind: str
    invocation: str
    destructive: bool
    idempotent: bool
    long_running: bool
    read_only: bool = False
    params: tuple[Param, ...] = ()
    consumes: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()  # direct prerequisites, as tool names
    meta: dict = field(default_factory=dict, compare=False)


def load_graph(data_file: Path | str | None = None) -> Graph:
    """Ontology (TBox) + product description (ABox) in one graph."""
    g = Graph()
    g.bind("sim", SIM)
    g.parse(ONTOLOGY_FILE, format="turtle")
    g.parse(data_file or DEFAULT_DATA_FILE, format="turtle")
    return g


def load_shapes() -> Graph:
    g = Graph()
    g.parse(SHAPES_FILE, format="turtle")
    return g


def _val(g: Graph, s, p, default=None):
    v = g.value(s, p)
    return default if v is None else v.toPython()


def _local(iri) -> str:
    s = str(iri)
    return s.rsplit("#", 1)[-1]


_OPERATION_QUERY = """
SELECT DISTINCT ?op ?kind WHERE {
  ?op a ?kind .
  ?kind rdfs:subClassOf* sim:Operation .
}"""


def load_model(g: Graph) -> dict[str, Operation]:
    """Return {tool_name: Operation} built from the graph."""
    tool_by_iri: dict[URIRef, str] = {}
    kinds: dict[URIRef, str] = {}
    for row in g.query(_OPERATION_QUERY, initNs={"sim": SIM, "rdfs": RDFS}):
        op, kind = row
        tool_by_iri[op] = _val(g, op, SIM.toolName, _local(op))
        # prefer the most specific class (anything but sim:Operation itself)
        if kind != SIM.Operation or op not in kinds:
            kinds[op] = _local(kind)

    def names(op, prop):
        return tuple(sorted(_local(o) for o in g.objects(op, prop)))

    model: dict[str, Operation] = {}
    for op, tool in tool_by_iri.items():
        params = []
        for p in g.objects(op, SIM.hasParameter):
            params.append(
                Param(
                    name=_val(g, p, SIM.name),
                    label=str(_val(g, p, RDFS.label, "")),
                    description=str(_val(g, p, RDFS.comment, "")),
                    type=_val(g, p, SIM.valueType, "string"),
                    required=bool(_val(g, p, SIM.isRequired, False)),
                    unit=_val(g, p, SIM.unit),
                    minimum=_num(_val(g, p, SIM.minValue)),
                    maximum=_num(_val(g, p, SIM.maxValue)),
                    allowed=tuple(sorted(str(v) for v in g.objects(p, SIM.allowedValue))),
                    default=_num(_val(g, p, SIM.defaultValue)),
                    example=_num(_val(g, p, SIM.example)),
                )
            )
        # required first, then alphabetical: stable, readable schemas
        params.sort(key=lambda x: (not x.required, x.name))
        model[tool] = Operation(
            iri=str(op),
            tool_name=tool,
            label=str(_val(g, op, RDFS.label, tool)),
            description=str(_val(g, op, RDFS.comment, "")),
            kind=kinds.get(op, "Operation"),
            invocation=_val(g, op, SIM.invocation, ""),
            destructive=bool(_val(g, op, SIM.isDestructive, False)),
            idempotent=bool(_val(g, op, SIM.isIdempotent, False)),
            long_running=bool(_val(g, op, SIM.isLongRunning, False)),
            read_only=bool(_val(g, op, SIM.isReadOnly, False)),
            params=tuple(params),
            consumes=names(op, SIM.consumes),
            produces=names(op, SIM.produces),
            requires=tuple(sorted(tool_by_iri[o] for o in g.objects(op, SIM.requiresOperation) if o in tool_by_iri)),
        )
    return dict(sorted(model.items()))


def _num(v):
    """Decimals come back as Decimal; normalise to int/float for JSON."""
    from decimal import Decimal

    if isinstance(v, Decimal):
        f = float(v)
        return int(f) if f.is_integer() else f
    return v

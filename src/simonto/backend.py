"""A *simulated* AeroFlow backend, driven entirely by the ontology.

Nothing here talks to a real solver. Numbers are produced by small analytic
formulas (thin-airfoil-style lift, parabolic drag polar) plus deterministic
pseudo-noise, and every result is flagged `"simulated": true`. What is real is
the contract enforcement the ontology gives you: argument validation against
types / units / bounds / enums, prerequisite and data-flow checks, and
structured, actionable errors an agent can recover from.
"""
from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, field

from .graph import Operation, Param


class ToolError(Exception):
    def __init__(self, code: str, message: str, hint: str | None = None):
        super().__init__(message)
        self.code, self.message, self.hint = code, message, hint

    def to_dict(self) -> dict:
        d = {"error": self.code, "message": self.message}
        if self.hint:
            d["hint"] = self.hint
        return d


def check_args(op: Operation, args: dict) -> tuple[dict, list[str]]:
    """Validate `args` against the ontology; return (arguments with defaults applied, errors)."""
    errors: list[str] = []
    known = {p.name: p for p in op.params}
    for k in args:
        if k not in known:
            errors.append(f"unknown parameter '{k}' (valid: {', '.join(known) or 'none'})")
    out: dict = {}
    for p in op.params:
        if p.name not in args:
            if p.required:
                errors.append(f"missing required parameter '{p.name}' ({p.description})")
            elif p.default is not None:
                out[p.name] = p.default
            continue
        v = args[p.name]
        err = _check_value(p, v)
        if err:
            errors.append(err)
        else:
            out[p.name] = v
    return out, errors


def _check_value(p: Param, v) -> str | None:
    if p.type == "boolean":
        return None if isinstance(v, bool) else f"'{p.name}' must be a boolean"
    if p.type in ("number", "integer"):
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return f"'{p.name}' must be a number"
        if p.type == "integer" and float(v) != int(v):
            return f"'{p.name}' must be an integer"
        unit = f" {p.unit}" if p.unit and p.unit not in ("dimensionless", "count") else ""
        if p.minimum is not None and v < p.minimum:
            return f"'{p.name}'={v} is below the minimum {p.minimum}{unit}"
        if p.maximum is not None and v > p.maximum:
            return f"'{p.name}'={v} is above the maximum {p.maximum}{unit}"
        return None
    if p.type == "enum":
        return None if v in p.allowed else f"'{p.name}'='{v}' is not one of {list(p.allowed)}"
    return None if isinstance(v, str) and v else f"'{p.name}' must be a non-empty string"


def _rng(*parts) -> random.Random:
    h = hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()
    return random.Random(int(h[:12], 16))


def _aero(v: float, aoa: float) -> tuple[float, float]:
    """Illustrative lift/drag model: thin-airfoil lift slope, parabolic polar."""
    cl = 2 * math.pi * math.radians(aoa) * 0.9
    cd = 0.015 + 0.045 * cl**2 + 0.00001 * max(v - 60, 0)
    return cl, cd


@dataclass
class SimulatedBackend:
    model: dict[str, Operation]
    artifacts: set[str] = field(default_factory=set)
    ctx: dict = field(default_factory=dict)
    history: list[str] = field(default_factory=list)
    dataset_rows: int = 0

    def state(self) -> dict:
        return {"artifacts": sorted(self.artifacts), "calls": list(self.history), "design_points": self.dataset_rows}

    def reset(self) -> None:
        self.artifacts.clear(); self.ctx.clear(); self.history.clear(); self.dataset_rows = 0

    def call(self, tool: str, args: dict | None = None, dry_run: bool = False) -> dict:
        if tool not in self.model:
            raise ToolError("unknown_tool", f"no operation named '{tool}'", "call ontology_list_operations")
        op = self.model[tool]
        full, errors = check_args(op, args or {})
        if errors:
            raise ToolError("invalid_arguments", "; ".join(errors),
                            "see the tool's inputSchema; call ontology_describe_operation for ranges and units")
        missing = [a for a in op.consumes if a not in self.artifacts]
        if missing:
            raise ToolError(
                "missing_prerequisite",
                f"{tool} needs {', '.join(missing)}, which does not exist in this session yet",
                f"call ontology_plan_workflow with goal='{tool}' to get the ordered steps",
            )
        if dry_run:
            return {"dry_run": True, "would_run": tool, "arguments": full,
                    "would_produce": list(op.produces), "simulated": True}
        result = getattr(self, f"_op_{tool}")(full)
        produced = [] if result.pop("_withhold", False) else list(op.produces)
        self.artifacts.update(produced)
        self.history.append(tool)
        result.update({"produced": produced, "simulated": True})
        return result

    # ---- operation implementations (illustrative) --------------------------

    def _op_import_geometry(self, a):
        self.ctx["geometry"] = a["file_path"]
        return {"file": a["file_path"], "length_unit": a["length_unit"], "faces": 1840, "bounding_box_m": [4.2, 1.1, 0.9]}

    def _op_repair_geometry(self, a):
        return {"gaps_closed": 37, "sliver_faces_removed": 12, "watertight": True, "tolerance_mm": a["tolerance"]}

    def _op_generate_mesh(self, a):
        size, bl = a["global_size"], a["boundary_layers"]
        cells = int(4.0e6 * (25 / size) ** 3 * (1 + bl / 20))
        self.ctx["mesh"] = {"size": size, "cells": cells}
        return {"cells": cells, "mesh_type": a["mesh_type"], "boundary_layers": bl, "est_wall_time_min": round(cells / 2.5e5, 1)}

    def _op_check_mesh_quality(self, a):
        size = self.ctx.get("mesh", {}).get("size", 25)
        sk = round(min(0.95, 0.35 + 0.012 * size), 3)
        ok = sk <= a["max_skewness"]
        return {"_withhold": not ok, "max_skewness": sk, "limit": a["max_skewness"], "passed": ok,
                "advice": None if ok else "reduce global_size and regenerate the mesh"}

    def _op_set_boundary_conditions(self, a):
        self.ctx["bc"] = a
        return {"inlet_velocity_m_s": a["inlet_velocity"], "angle_of_attack_deg": a["angle_of_attack"],
                "turbulence_model": a["turbulence_model"], "mach": round(a["inlet_velocity"] / 340.3, 3)}

    def _op_configure_solver(self, a):
        self.ctx["solver"] = a
        return dict(a)

    def _op_run_solver(self, a):
        s = self.ctx["solver"]
        r = _rng("solve", self.ctx["bc"]["inlet_velocity"], self.ctx["bc"]["angle_of_attack"], self.ctx["mesh"]["size"])
        needed = int(300 + 90 * abs(math.log10(s["convergence_tolerance"])) + r.randint(0, 80))
        iters = min(needed, s["max_iterations"])
        self.ctx["converged"] = needed <= s["max_iterations"]
        self.ctx["iters"] = iters
        return {"iterations": iters, "converged": self.ctx["converged"], "cores": a["num_cores"],
                "final_residual": s["convergence_tolerance"] * (0.5 if self.ctx["converged"] else 40)}

    def _op_monitor_convergence(self, a):
        return {"status": "converged" if self.ctx["converged"] else "not_converged",
                "iterations": self.ctx["iters"], "window": a["window"]}

    def _op_extract_forces(self, a):
        bc = self.ctx["bc"]
        cl, cd = _aero(bc["inlet_velocity"], bc["angle_of_attack"])
        q = 0.5 * 1.225 * bc["inlet_velocity"] ** 2
        self.ctx["forces"] = (bc["inlet_velocity"], bc["angle_of_attack"], cl, cd)
        return {"CL": round(cl, 4), "CD": round(cd, 5), "lift_N": round(q * a["reference_area"] * cl, 1),
                "drag_N": round(q * a["reference_area"] * cd, 1)}

    def _op_export_results(self, a):
        return {"path": a["output_path"], "format": a["format"], "overwritten": a["overwrite"]}

    def _op_record_design_point(self, a):
        self.dataset_rows += 1
        return {"dataset": a["dataset_path"], "rows": self.dataset_rows}

    def _op_train_surrogate(self, a):
        n = max(self.dataset_rows, 1)
        r = _rng("train", a["random_seed"], a["model_type"], n)
        rmse = round((0.04 / math.sqrt(n)) * (0.8 + 0.4 * r.random()), 5)
        self.ctx["surrogate"] = a
        out = {"model_type": a["model_type"], "training_points": n, "validation_rmse_CL": rmse, "seed": a["random_seed"]}
        if n < 10:
            out["warning"] = f"only {n} design point(s); error estimates are not trustworthy below ~10"
        return out

    def _op_predict_with_surrogate(self, a):
        cl, cd = _aero(a["inlet_velocity"], a["angle_of_attack"])
        r = _rng("pred", a["inlet_velocity"], a["angle_of_attack"])
        return {"CL": round(cl * (1 + 0.02 * (r.random() - 0.5)), 4), "CD": round(cd * (1 + 0.03 * (r.random() - 0.5)), 5),
                "inputs": {"inlet_velocity_m_s": a["inlet_velocity"], "angle_of_attack_deg": a["angle_of_attack"]}}

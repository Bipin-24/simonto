# Agentic-readiness report

**Overall: 99.1 / 100** across 13 operations.

| Operation | Score | Findings |
|---|---:|---|
| `train_surrogate` | 92 | missing min/max: random_seed |
| `set_boundary_conditions` | 96 | missing min/max: outlet_pressure |
| `check_mesh_quality` | 100 | - |
| `configure_solver` | 100 | - |
| `export_results` | 100 | - |
| `extract_forces` | 100 | - |
| `generate_mesh` | 100 | - |
| `import_geometry` | 100 | - |
| `monitor_convergence` | 100 | - |
| `predict_with_surrogate` | 100 | - |
| `record_design_point` | 100 | - |
| `repair_geometry` | 100 | - |
| `run_solver` | 100 | - |

## Rubric

| Check | Points | Meaning |
|---|---:|---|
| description | 15 | Description is specific (>= 60 chars) so an LLM can pick the right tool |
| parameters_documented | 15 | Every parameter has a description of >= 20 chars |
| units | 10 | Every numeric parameter declares a unit |
| bounds | 15 | Every numeric parameter declares min and max (safe ranges) |
| enums | 10 | Enum parameters list allowed values (checked by SHACL; partial credit otherwise) |
| side_effects | 10 | Destructive / long-running flags are declared |
| outputs | 10 | At least one typed output artifact is declared |
| prerequisites | 15 | Every consumed artifact's producer is a declared (transitive) prerequisite |

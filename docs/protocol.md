# Protocol reference (schema 1)

TEVIEW files use TOML syntax and the `.tev` extension. The parser rejects unsupported fields and malformed references.

## Top-level declarations

| Field | Description |
| --- | --- |
| `schema = 1` | Protocol format version |
| `title`, `description` | Descriptive metadata |
| `seed` | Base deterministic seed |
| `replicates` | Number of executions per arm |
| `paired` | Use common replication seeds for arms |
| `[parameters]` | Shared parameter values |
| `[arms.NAME]` | Experimental alternatives |
| `[datasets]` | Named relative input files |
| `[[steps]]` | Ordered-by-dependency operations |
| `[[metrics]]` | Numeric observations taken from step outputs |
| `[[guards]]` | Runtime correctness and safety conditions |
| `[[claims]]` | Cross-arm comparison criteria |

## Step declarations

A step has `id`, `uses`, `with` and `out` fields. `out` specifies every field and its required type. Supported types are `number`, `integer`, `string`, `boolean`, `array` and `object`.

The `uses` field identifies `builtin:NAME` or `python:relative_path.py:function_name`. Python steps must be explicitly approved using `--allow-python`.

A Python extension has the contract:

```python
def execute(inputs: dict, *, seed: int) -> dict:
    return {"value": inputs["x"] * 2}
```

The return dictionary must match the step's `out` contract exactly. Extension modules can have side effects and are trusted code, not sandboxed plugins.

## References

Values may reference `${parameters.NAME}`, `${arm.NAME}`, `${run.seed}`, `${run.replicate}`, `${run.arm}`, `${datasets.NAME}` or `${steps.STEP_ID.FIELD}`.

Stage dependencies are derived from `steps` references and sorted topologically. Circular dependencies and unknown fields fail validation.

## Measurements and claims

A metric has an `id`, a numeric `source` reference and an optional `unit` label. Unit labels are not validated dimensionally. Guards use one of `==`, `!=`, `<`, `<=`, `>` and `>=`.

Claims compare a selected metric between two arms using a direction, effect threshold and optional confidence level. Inference uses a basic percentile bootstrap on variable outcomes. Deterministic repeated computations are not treated as independent statistical replicates.

## Evidence and caching

The `run` command snapshots declared files and records input/output hashes and measurements. `verify` re-executes the snapshot with caching disabled and compares observations and claim assessments. `--cache DIRECTORY` enables stage result caching; `--no-cache` disables it.

Only explicitly declared files are included in the bundle. For full reproducibility, separately control OS, interpreter version, Python environment, packages, external services and third-party solvers.

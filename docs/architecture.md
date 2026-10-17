# Architecture and trust model

TEVIEW v0.2 is a Python command-line prototype. The primary source is `tev.py`; `tests/test_core.py` is its regression suite. The `.tev` file format is documented in `protocol.md`.

## Execution lifecycle

1. **Parse and validate.** Read a TOML `.tev` specification; check declared arms, steps, parameter references and output contracts.
2. **Plan.** Resolve dependency ordering and prepare deterministic inputs for configured runs.
3. **Execute.** Run built-in stages or opt-in Python extensions. Built-ins are local computational functions; Python extensions receive host interpreter permissions.
4. **Record.** Snapshot the declared protocol and inputs; emit measurements, lineage, report and human-readable summary.
5. **Verify.** Replay saved declared computations and compare results without using a cache; changed declared inputs cause verification to fail.

## Boundaries

- This is an **execution and provenance** tool, not a numerical simulator for every discipline.
- The verification command checks replay equivalence; it does not validate empirical accuracy, scientific assumptions, data selection or causality.
- Declared files and plugin source may be snapshotted, but undeclared plugin dependencies, network responses and environment state are not automatically captured.
- `--allow-python` executes trusted code in the host process. No permission model, container sandbox or timeout is included.
- Metrics' unit strings are labels rather than dimensionally checked quantities.

## Non-goals for this release

Distributed execution, cloud accounts, hosted services, autonomous experiment design, production-grade statistical certification and an unrestricted natural-language-to-experiment engine are not implemented.

## Extending safely

A new built-in step requires clear input/output typing, deterministic behavior where feasible, validation of malformed values, documented semantics, and unit tests. Schema changes should be explicit and versioned; avoid implicit migrations.

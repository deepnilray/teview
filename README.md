# TEVIEW

**Run an experiment. Preserve the evidence. Reject regressions.**

TEVIEW is an open-source, Python 3.11+ command-line tool for computational experiments. It records source and declared data, runs candidate approaches, checks measurable acceptance criteria, and produces replayable evidence bundles. You can start with an existing script or define a full experimental protocol.

TEVIEW runs locally, needs no server account, and its core has no third-party runtime dependencies. It is an **alpha**: it does not establish scientific validity, automatically reproduce untracked dependencies, or safely execute untrusted code.

## Start with code you already have

From a clone of this repository:

```bash
python -m pip install -e .
tev capture --root examples/command --out runs/integration-v1 \
  --code integrate.py --data measurements.csv \
  -- python integrate.py
tev verify runs/integration-v1
```

The example integrates a sampled function and writes `metrics.json`. `capture` executes `python integrate.py` in a separate temporary directory containing only the explicitly declared files, saves numerical measurements and source snapshots, and produces a report. `verify` re-executes the saved command and checks that measurements and declared artifact hashes match. The command runs **with your user permissions**, not inside a security sandbox.

To capture your own existing program:

```bash
tev capture --root my-project --out runs/baseline \
  --code analyze.py --data observations.csv \
  --metrics metrics.json -- python analyze.py
```

Your script needs to write a JSON object containing finite numeric values, such as `{"error": 0.012, "runtime_ms": 43.2}`. Declare **all** source code and data files required for replay with repeated `--code` and `--data` options; undeclared imports, packages, OS dependencies, API responses and external services are **not** captured automatically. You can track output files using `--artifact results.csv`. See [capture specification](docs/capture.md).

## Decide whether a change is acceptable

Create a second run after changing the implementation (without changing the experiment or dataset):

```bash
tev capture --root examples/command --out runs/integration-v2 \
  --code integrate.py --data measurements.csv \
  -- python integrate.py
tev gate runs/integration-v1 runs/integration-v2 \
  --policy examples/command/gate.toml --verify-evidence
```

The gate compares candidate metrics to a baseline and applies explicit regression budgets. The provided example policy requires numerical error not to regress by more than 0.0001 and the sample count not to decrease. A rejected candidate returns exit code **2**, so it can fail CI; invalid evidence or a command failure returns **1**. Both runs must have the same command specification, datasets, design and measurement units unless explicitly overridden for a reviewed change. The gate measures a **defined policy**, not statistical significance.

You can inspect the machine-readable verdict or write it to a file:

```bash
tev gate runs/integration-v1 runs/integration-v2 \
  --policy examples/command/gate.toml --json-out gate-result.json
```

Without `--verify-evidence`, the gate reads the reports but does not re-execute them. For high-trust decisions, use `--verify-evidence` with reviewed code. Captured commands and Python plugins are not sandboxed.

## Design experiments with structured protocols

If you want multiple experimental arms, seeded replications, step dependencies, declared datasets and exploratory hypotheses, use a `.tev` protocol (TOML). You don't need to learn a proprietary language.

```bash
tev init my-study
tev validate my-study/experiment.tev
tev run my-study/experiment.tev --out runs/study --allow-python
tev verify runs/study --allow-python
```

`init` generates an editable sample project, including the protocol, Python function, and regression policy. Replace the sample computation with your actual research code. Use `--allow-python` **only for trusted scripts**.

A non-Python synthetic A/B experiment runs without executing extension code:

```bash
tev plan examples/ab_test/experiment.tev
tev run examples/ab_test/experiment.tev --out runs/ab
tev verify runs/ab
```

The tool currently has built-in operators `bernoulli`, `ratio`, `mean`, `linear`, and `csv_column`. For your own logic, specify `python:relative_file.py:function` and opt into Python execution. Full syntax: [protocol specification](docs/protocol.md).

## What a TEVIEW run contains

- `report.json` and `REPORT.md`: measurements and accurately limited claim/guard assessments
- Snapshots of explicitly declared source and data under `source/`
- Captured commands: `capture.json`, `metrics.json`, `stdout.txt`, `stderr.txt`
- Structured protocols: `protocol.json`, `measurements.csv`, `lineage.json`

A passing `tev verify` means declared computations replayed in the **current environment**. It does not prove the model is correct, that all dependencies were captured, that the reported effect is causal, or that a different machine will reproduce it.

## Where TEVIEW fits

Experiment platforms such as MLflow and DVC already offer sophisticated metrics, pipelines and experiment tracking; ReproZip offers more extensive dependency capture. TEVIEW is smaller. Its focus is a text-first **measurable acceptance gate backed by replayable evidence**, usable with ordinary local command-line programs and without mandatory infrastructure. It is not a replacement for those mature systems or for specialized physics, statistics, hardware, or workflow engines.

## Development

```bash
python -m unittest discover -s tests -v
```

CI exercises Windows, macOS and Linux with Python 3.11 and 3.13, including command capture, replay and the gate. See [architecture](docs/architecture.md), [security policy](SECURITY.md) and [contributing](CONTRIBUTING.md). Licensed under MIT.

**Status: v0.3.0 alpha.** Backward compatibility is not yet guaranteed. External user adoption and independent scientific validation have not been established.

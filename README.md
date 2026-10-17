# TEVIEW

**Text-defined computational experiments with reproducible execution records.**

TEVIEW is a command-line tool for describing experiments in a versioned, machine-readable file. An experiment declares inputs, alternative conditions, execution steps, measurements, constraints and comparison criteria. The runner produces a record of the procedure, results, code and declared input files so another developer can rerun the computation.

TEVIEW is an early-stage research prototype. It is not a physics engine, laboratory hardware controller, statistical certification tool or replacement for mature workflow systems.

## Quick start

Requires Python 3.11 or newer. The core and included examples use only the standard library.

```bash
python tev.py validate examples/ab_test/experiment.tev
python tev.py plan examples/ab_test/experiment.tev
python tev.py run examples/ab_test/experiment.tev --out results/ab
python tev.py verify results/ab
```

For an installable command:

```bash
python -m pip install -e .
tev --help
```

Some examples call user-provided Python functions. These require the explicit `--allow-python` option:

```bash
python tev.py run examples/physics/experiment.tev --out results/physics --allow-python
python tev.py verify results/physics --allow-python
```

Only enable this option for code you trust. Python extensions are not isolated or sandboxed.

## Experiment format

An experiment is a TOML document saved with the `.tev` extension. This is a small, inspectable configuration format, not a proprietary programming language.

```toml
schema = 1
title = "Checkout conversion comparison"
seed = 20261017
replicates = 32
paired = true

[parameters]
sessions = 1600

[arms.control]
probability = 0.20

[arms.variant]
probability = 0.30

[[steps]]
id = "sample"
uses = "builtin:bernoulli"
with = { n = "${parameters.sessions}", p = "${arm.probability}" }
out = { successes = "integer", total = "integer", rate = "number" }

[[metrics]]
id = "conversion"
source = "${steps.sample.rate}"
unit = "proportion"

[[claims]]
id = "conversion_increase"
metric = "conversion"
control = "control"
treatment = "variant"
direction = "increase"
threshold = 0.05
confidence = 0.95
```

The example generates **synthetic** outcomes. It does not constitute evidence about real users. Claims produced by the experimental inference module are exploratory; the tool does not automatically establish causality or validity of a statistical design.

## Commands

| Command | Purpose |
| --- | --- |
| `tev validate <file>` | Check structure, references and declared contracts |
| `tev plan <file>` | Display execution order, steps and declared resources |
| `tev run <file> --out <directory>` | Execute and save an evidence bundle |
| `tev verify <directory>` | Re-execute the saved source without cache and compare results |
| `tev compare <run-a> <run-b>` | Compare recorded metric means |

The runner supports dependency-ordered steps, typed outputs, seeded replications, guarded conditions, declared datasets, content-hash caching and opt-in Python extensions. Available built-in functions are `bernoulli`, `ratio`, `mean`, `linear` and `csv_column`.

## Run artifacts

Each run contains a copy of its protocol and declared inputs, `protocol.json`, `report.json`, `lineage.json`, `measurements.csv` and a readable `REPORT.md`. A successful `verify` means recorded computational results replayed under the available environment; it does **not** prove that the scientific method, model or data were correct.

## Examples

| Directory | Experiment |
| --- | --- |
| `examples/ab_test` | Synthetic paired A/B comparison |
| `examples/physics` | Analytical free-fall calculation |
| `examples/software` | Comparison-count study of sorting algorithms |
| `examples/data` | CSV-based measurement analysis |

## Development

```bash
python -m unittest discover -s tests -v
```

The CI workflow runs the test suite and an example execution/replay on supported Python versions. See [protocol reference](docs/protocol.md) and [security and limitations](SECURITY.md) for details.

**Status:** v0.2.0 alpha. The core is intended for trusted local experimentation; compatibility and model interfaces may change. Licensed under MIT.

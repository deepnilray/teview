# Contributing

TEVIEW is an experimental computational experiment runner. Contributions must preserve the distinction between **reproducing a computation** and **validating a scientific conclusion**.

## Local development

Python 3.11 or newer is required. The core has no runtime third-party dependencies.

```bash
python -m unittest discover -s tests -v
python tev.py validate examples/ab_test/experiment.tev
python tev.py run examples/ab_test/experiment.tev --out results/ab
python tev.py verify results/ab
```

Before a pull request, add or update tests for changed behavior; test malformed input, missing dependencies and portability where relevant. Document all new built-in functions, `.tev` schema changes and command-line options. Never silently claim that a replay verifies a model, source data, or causal conclusion.

## Pull requests

Keep changes focused. Explain behavior, tests performed, compatibility concerns and security implications. Do not commit experiment outputs, virtual environments, local credentials, generated wheels, caches or machine-specific paths.

## Running plugins

Extensions run arbitrary Python when `--allow-python` is supplied. Do not execute plugin code from untrusted contributors while reviewing a pull request. No sandbox is provided.

## Code of conduct

Discuss technical disagreements respectfully and focus criticism on observable behavior and reproducible evidence. Security concerns should follow SECURITY.md.

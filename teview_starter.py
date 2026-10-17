"""Create a complete, small, editable real-code TEVIEW project."""
from pathlib import Path

PROTOCOL = '''schema = 1
title = "Candidate-versus-baseline calculation"
seed = 73
replicates = 8
paired = true

[parameters]
size = 100

[arms.baseline]
method = "baseline"

[arms.candidate]
method = "candidate"

[[steps]]
id = "evaluate"
uses = "python:model.py:evaluate"
with = { method = "${arm.method}", size = "${parameters.size}" }
out = { error = "number", operations = "integer", correct = "boolean" }

[[metrics]]
id = "error"
source = "${steps.evaluate.error}"
unit = "score"

[[metrics]]
id = "operations"
source = "${steps.evaluate.operations}"
unit = "count"

[[guards]]
id = "must_be_correct"
source = "${steps.evaluate.correct}"
op = "=="
value = true
'''

MODEL = '''"""Replace evaluate() with your actual calculation or trained model evaluation.

The same Python function runs for each experimental arm with the provided input.
Use the seed to create any random state, rather than using global randomness.
"""
import random


def evaluate(inputs, *, seed):
    rng = random.Random(seed)
    size = inputs["size"]
    method = inputs["method"]
    # EXAMPLE ONLY: replace these computations with your own code.
    observations = [rng.random() for _ in range(size)]
    target = sum(observations) / len(observations)
    if method == "baseline":
        approximation = round(target, 1)
        operations = 3 * size
    elif method == "candidate":
        approximation = round(target, 3)
        operations = 5 * size
    else:
        raise ValueError(f"Unknown method: {method}")
    return {"error": abs(approximation - target),
            "operations": operations, "correct": True}
'''

POLICY = '''schema = 1
title = "No degradation of numerical quality"

[[checks]]
id = "error_budget"
arm = "candidate"
metric = "error"
direction = "decrease"
max_absolute_regression = 0.001

[[checks]]
id = "operation_budget"
arm = "candidate"
metric = "operations"
direction = "decrease"
max_relative_regression = 0.05
'''

README = '''# My TEVIEW experiment

This is a working starter using your own Python function in `model.py`.
The supplied model is a toy illustration; replace it with meaningful code.

```sh
python -m pip install -e /path/to/teview  # run once, from a local clone
tev validate experiment.tev
tev run experiment.tev --out runs/first --allow-python
tev verify runs/first --allow-python
```

Edit `model.py` or the experiment parameters and rerun to a new directory.
To check for regressions against the first run:

```sh
tev gate runs/first runs/second --policy gate.toml
```

The gate checks observed metrics against explicit budgets, and returns exit code
2 if a budget is violated. It does not establish statistical significance.
'''


def create_starter(directory):
    target=Path(directory).resolve()
    if target.exists():
        raise ValueError(f'Refusing to modify existing path: {target}')
    target.mkdir(parents=True)
    try:
        for name, content in [('experiment.tev',PROTOCOL),('model.py',MODEL),
                              ('gate.toml',POLICY),('README.md',README)]:
            (target/name).write_text(content, encoding='utf-8')
    except Exception:
        import shutil
        shutil.rmtree(target)
        raise
    return {'created':str(target),'files':['experiment.tev','model.py','gate.toml','README.md'],
            'next':f'tev run {target / "experiment.tev"} --out {target / "runs" / "first"} --allow-python'}

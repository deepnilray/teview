# Command capture and replay

`tev capture` integrates existing programs that write a JSON metrics file. It does not need to import or edit user code. Run the command from your project checkout using `--root PATH` as its working directory.

```sh
tev capture --root path/to/project --out runs/first \
  --code experiment.py --code helpers.py --data dataset.csv \
  --metrics metrics.json --artifact figure.svg --timeout 120 --seed 3 \
  -- python experiment.py
```

## Contract

1. Explicitly declare each input source file using `--code` and input dataset using `--data`. Paths are relative to `--root` and must be regular files located within that directory. Files are limited to 64 MiB each and 256 MiB total. A missing or changed file fails the capture.
2. The command executes in a fresh temporary directory holding those declared files. Shell interpolation is **not** performed; pass a shell explicitly if your trusted experiment requires it. Captured programs have your current user permissions and environment variables and are **not sandboxed**.
3. The program must exit with status 0 within `--timeout` (default 60 seconds). It must create `metrics.json` (or the path given by `--metrics`) containing a nonempty JSON object with only finite numeric metric values. Use `--artifact FILE` to include a SHA-256 check for other generated output files.
4. The output directory must not already exist. A successful run stores source snapshots, a command manifest, metrics and plaintext execution logs. Failures remove temporary output rather than publishing partial evidence.
5. `tev verify RUN` replays the captured command in a fresh work directory and checks the exact metrics and declared artifact hashes. It does **not** require stdout/stderr or execution time to match.

`TEVIEW_SEED` is set to the supplied `--seed` value for reproducible scripts, but TEVIEW cannot force external libraries, hardware, clocks or network requests to be deterministic. An absolute command path or untracked dependency may prevent replay on other machines. For stronger portability, use a dependency-locked environment or a container maintained separately.

## Experiment gate

`tev gate BASE CANDIDATE --policy policy.toml` compares the runs. Files under `--code` are permitted to change, while `--data` content, experiment command and seed must normally be identical. `--verify-evidence` verifies both bundles **by executing the captured commands** before comparing them. Gate exit codes are 0 (accepted), 2 (rejected by policy), and 1 (invalid or failed execution). A gate is not a substitute for randomized trial design or statistical power calculations.

```toml
schema = 1
title = "Numerical quality"

[[checks]]
id = "accuracy"
arm = "default"
metric = "error"
direction = "decrease"
max_absolute_regression = 0.0001
```

`direction = "decrease"` means smaller is better; `increase` means larger is better. A check can use `statistic = "mean"`, `"worst"` or `"p95"`, with optional `max_relative_regression`. For a single run, these statistics coincide. Unverified reports are just user-modifiable JSON files; they are not signed attestations.

# Changelog

## 0.3.0-alpha — Adoption workflow

- Capture existing command-line computations with declared files, numeric metrics and artifact hashes.
- Replay captured commands from source snapshots and reject modified inputs or metrics.
- Bootstrap an editable experiment with `tev init`.
- Compare baseline and candidate with policy-controlled `tev gate` (CI exit status 2 on regression).
- Optional evidence replay before gating; unit-consistency enforcement for structured protocols.
- Add capture contract, examples and end-to-end tests across CI environments.

# Changelog

## 0.2.0-alpha — 2026-10-17

Initial public alpha of the code-first experiment runner. Supports TOML experiment definitions, built-in and trusted Python stages, typed output contracts, declared datasets, constraints, observations, basic experimental comparisons, replay and provenance records. Includes four examples and an automated test suite.

This release is experimental and is not a production scientific validation platform.

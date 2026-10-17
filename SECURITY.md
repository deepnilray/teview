# Security and limitations

TEVIEW executes local computational workflows. It does not provide isolation from the host operating system.

## Trusted code execution

- `python:path/to/plugin.py:function` runs Python with the permissions of the user invoking TEVIEW.
- `--allow-python` grants permission for those extensions. Use it only with source code you have inspected and trust.
- Extension code may access undeclared files, external packages, environment variables and networks. Those side effects are not captured by the experiment bundle.
- Do not run untrusted protocols with `--allow-python` on a personal or production machine. Use a separately configured, isolated environment.

## Reproducibility guarantees

- The runner snapshots and hashes the protocol, explicitly declared datasets and explicitly declared Python plugin files.
- Verification reruns the saved protocol and compares recorded computations. It does not authenticate malicious or tampered files and cannot recreate packages, services or random side effects not included in the snapshot.
- SHA-256 digests protect against accidental changes; the bundle is not a signed provenance statement.
- Replaying a result does not validate the physics, causal model, data selection, statistical assumptions or external measurements.

## Experimental and statistical limitations

- Statistical intervals are exploratory percentile bootstrap summaries; they are not universally calibrated confidence guarantees.
- Measurement units are labels and are not dimension-checked.
- Plugin execution has no sandbox, time limit or resource quota.
- No regulatory controls, hardware safety interlocks, user authentication or remote execution service are supplied.

Do not use this alpha for untrusted shared execution, safety-critical systems or regulated research decisions.

For a suspected security problem, avoid posting exploit details in a public issue. Contact the repository maintainer privately through a channel listed on their GitHub profile until a formal security contact is established.

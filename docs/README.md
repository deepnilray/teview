# Public TEVIEW Studio demonstration

This folder can be published through GitHub Pages. The site plays precomputed scenes using the numerical TEVIEW kernel and its existing visual player. There is no public simulation backend; editing source requires installing TEVIEW locally.

To reproduce samples: install TEVIEW (Python >=3.11), run `tev simulate <scene.tev> --out <directory>`, `tev scene-verify <directory>`, and `tev visualize <directory>`. The checked snapshots are archived in the `samples/` folders.

The dynamic local Studio implementation is available in the packaged desktop source; do not attempt to expose its loopback HTTP service on the public Internet.

Each experiment is reported as `simulated_not_validated`: replay does not establish physical accuracy.

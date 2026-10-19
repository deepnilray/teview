# Installing TEVIEW with pip

Requires Python 3.11 or newer.

## From the attached wheel (works without internet)

```bash
python -m pip install teview_evidence_core-0.5.2a0-py3-none-any.whl
teview --help
teview --run ball
```

On Windows you may run `py -3 -m pip install <wheel-file>` and `teview --run ball`.

## From GitHub (gets the version currently on the repository)

```bash
python -m pip install 'git+https://github.com/deepnilray/teview.git'
tev --help
```

The remote source may be a different version from the included wheel.

## From source folder

```bash
python -m pip install .
teview --run lamp
```

The `tev` command exposes the low-level physics / evidence CLI.
The `teview` command opens a user-facing experiment menu or runs named examples.

## Windows executable

Source for automated Windows builds is in `.github/workflows/windows-exe.yml`.
A Windows executable must be built on Windows; this package is not itself a Windows EXE.
When the workflow runs successfully, download its `TEVIEW-Windows-x64` artifact.

**PyPI status:** This package has not been uploaded to the public PyPI index.
Therefore `pip install teview` should not be assumed to install this software.

"""TEVIEW user-facing launcher, shared by pip installs and packaged executables.

Works without a separately installed Python when frozen with PyInstaller.
Scientific execution always calls the same TEVIEW engine as the `tev` CLI.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime
from importlib import resources
from pathlib import Path
import os
import shutil
import sys
import uuid
import webbrowser

import tev

_EXPERIMENTS = {
    'ball': ('Ball, water and spring', 'ball_water_spring.tev'),
    'lamp': ('Battery, switch and lamp', 'electrothermal.tev'),
    'charges': ('Charged particles and probes', 'electrostatic_field.tev'),
    'combined': ('Mechanics, fluids, circuits and light', 'combined_lab.tev'),
}


def workspace_folder(explicit: str | None = None) -> Path:
    path = Path(explicit or os.environ.get('TEVIEW_WORKSPACE', '') or Path.home() / 'TEVIEW').expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def experiment_source(name: str, workspace: Path):
    if name == 'custom':
        path = workspace / 'my_experiment.tev'
        if not path.is_file():
            raise FileNotFoundError(f'No personal experiment at {path}. Use --init-custom first.')
        yield path
    else:
        filename = _EXPERIMENTS[name][1]
        target = resources.files('teview_examples').joinpath(filename)
        with resources.as_file(target) as extracted:
            yield extracted


def engine(*arguments: str) -> None:
    code = tev.main([str(x) for x in arguments])
    if code not in (None, 0):
        raise RuntimeError(f'Engine command {arguments[0]!r} returned exit status {code}')


def run_experiment(name: str, workspace: Path, open_browser: bool, converge: bool) -> Path:
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6]
    output = workspace / 'runs' / f'{name}-{stamp}'
    with experiment_source(name, workspace) as path:
        engine('scene-check', str(path))
        engine('scene-explain', str(path))
        engine('simulate', str(path), '--out', str(output))
        engine('scene-verify', str(output))
        if converge:
            engine('scene-converge', str(path), '--rtol', '0.001', '--atol', '0.000001')
        engine('visualize', str(output))
    viewer = output / 'viewer.html'
    if not viewer.is_file():
        raise RuntimeError('Simulation completed, but viewer.html was not produced')
    print(f'\nViewer: {viewer}\nMeasurements: {output / "measurements.csv"}')
    print('Results are predictions of idealized models, not laboratory validation.')
    if open_browser and not webbrowser.open(viewer.as_uri(), new=2):
        print('Browser did not open automatically. Open the viewer path above manually.')
    return output


def initialize_custom(workspace: Path) -> Path:
    dst = workspace / 'my_experiment.tev'
    if dst.exists():
        print(f'Personal experiment already exists; nothing overwritten: {dst}')
        return dst
    with experiment_source('ball', workspace) as template:
        shutil.copyfile(template, dst)
    print(f'Created: {dst}. Edit with any text editor, then run --run custom.')
    return dst


def menu(workspace: Path, open_browser: bool, converge: bool) -> int:
    if not sys.stdin.isatty():
        raise RuntimeError('The interactive menu requires a terminal. Try --run ball or --help.')
    while True:
        print('\nTEVIEW — Scientific experiments (alpha)')
        options = list(_EXPERIMENTS)
        for i, key in enumerate(options, 1):
            print(f'  {i}. {_EXPERIMENTS[key][0]}')
        print('  5. Create a personal experiment\n  6. Run personal experiment\n  0. Quit')
        try:
            choice = input('Choice: ').strip()
        except EOFError:
            return 0
        if choice == '0':
            return 0
        try:
            if choice in ('1', '2', '3', '4'):
                run_experiment(options[int(choice)-1], workspace, open_browser, converge)
            elif choice == '5':
                initialize_custom(workspace)
            elif choice == '6':
                run_experiment('custom', workspace, open_browser, converge)
            else:
                print('Choose a number from 0 through 6.')
        except (OSError, ValueError, RuntimeError) as exc:
            print(f'Experiment failed: {exc}', file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='TEVIEW — a text-first scientific simulation environment')
    parser.add_argument('--run', choices=(*_EXPERIMENTS, 'custom'), help='simulate the selected experiment and generate its viewer')
    parser.add_argument('--init-custom', action='store_true', help='create a personal experiment in your workspace')
    parser.add_argument('--smoke-test', action='store_true', help='run and replay a small example')
    parser.add_argument('--no-browser', action='store_true', help='do not launch the browser')
    parser.add_argument('--converge', action='store_true', help='check time-step refinement after the experiment')
    parser.add_argument('--workspace', help='directory for personal experiments and run outputs')
    args = parser.parse_args(argv)
    try:
        workspace = workspace_folder(args.workspace)
        if args.init_custom:
            initialize_custom(workspace)
            return 0
        if args.smoke_test:
            result = run_experiment('lamp', workspace, False, False)
            assert (result / 'measurements.csv').is_file()
            print('TEVIEW SMOKE TEST PASSED')
            return 0
        if args.run:
            run_experiment(args.run, workspace, not args.no_browser, args.converge)
            return 0
        return menu(workspace, not args.no_browser, args.converge)
    except (OSError, ValueError, RuntimeError, AssertionError, KeyError) as exc:
        print(f'TEVIEW ERROR: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

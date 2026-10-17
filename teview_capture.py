"""Explicit-input capture for existing command-line experiments.

No sandbox, automatic dependency discovery, or cross-machine environment replay is
claimed. The command runs as the invoking user, in a work directory containing
only files explicitly supplied by the user.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import subprocess
import sys
import tempfile
import time

from tev import ExperimentError, canonical, digest, filehash, relative_file, require, save_json, VERSION

MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_LOG_BYTES = 2 * 1024 * 1024


def clean_path(raw, what):
    require(isinstance(raw, str) and bool(raw), f'{what} requires a path')
    p = PurePosixPath(raw.replace('\\', '/'))
    require(not p.is_absolute() and all(x not in ('..', '.') for x in p.parts) and p.parts,
            f'{what} must stay within the experiment directory: {raw!r}')
    require(':' not in p.parts[0], f'{what} must be relative: {raw!r}')
    return p.as_posix()


def inputs_info(root, files):
    out = {}
    total = 0
    for raw in files:
        rel = clean_path(raw, 'input file')
        require(rel not in out, f'duplicate declared input: {rel}')
        p = relative_file(root, rel)
        size = p.stat().st_size
        require(size <= MAX_FILE_BYTES, f'input exceeds 64 MiB: {rel}')
        total += size
        require(total <= MAX_TOTAL_BYTES, 'captured inputs exceed 256 MiB')
        out[rel] = {'sha256': filehash(p), 'bytes': size}
    return out


def check_metric_file(path):
    require(path.is_file(), f'command did not produce declared metrics JSON: {path.name}')
    require(path.stat().st_size <= 1024 * 1024, 'metrics JSON exceeds 1 MiB')
    try:
        metrics = json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, UnicodeError) as exc:
        raise ExperimentError(f'invalid metrics JSON: {exc}') from exc
    require(isinstance(metrics, dict) and metrics, 'metrics must be a nonempty JSON object')
    for name, value in metrics.items():
        require(isinstance(name, str) and name and len(name) <= 80, 'metric keys must be short nonempty strings')
        require(type(value) in (int, float) and math.isfinite(value), f'metric {name!r} must be a finite number')
    return metrics


def execute(manifest, snapshot):
    cmd = manifest['command']
    require(isinstance(cmd, list) and cmd and all(type(v) is str and v for v in cmd), 'command must be nonempty arguments')
    timeout = manifest['timeout']
    with tempfile.TemporaryDirectory(prefix='tev-capture-') as td:
        work = Path(td)
        for rel in manifest['code'] + manifest['data']:
            src = relative_file(snapshot, rel)
            dest = work / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
        start = time.monotonic()
        stdout = work / '__tev_stdout__.txt'
        stderr = work / '__tev_stderr__.txt'
        # Run without shell expansion. This is NOT sandboxed; user commands have
        # the current user's OS permissions and can access resources outside work.
        try:
            with stdout.open('wb') as so, stderr.open('wb') as se:
                p = subprocess.run(cmd, cwd=work, stdout=so, stderr=se, timeout=timeout, check=False,
                                   env={**os.environ, 'TEVIEW_SEED': str(manifest['seed'])})
        except FileNotFoundError as exc:
            raise ExperimentError(f'command executable missing: {cmd[0]}') from exc
        except subprocess.TimeoutExpired as exc:
            raise ExperimentError(f'command exceeded {timeout}s timeout') from exc
        duration = time.monotonic() - start
        require(stdout.stat().st_size <= MAX_LOG_BYTES and stderr.stat().st_size <= MAX_LOG_BYTES,
                'captured log exceeds 2 MiB per stream')
        require(p.returncode == 0,
                f'command exited {p.returncode}; stderr: {stderr.read_text(encoding="utf-8", errors="replace")[-500:]}')
        metricpath = work / manifest['metrics']
        metrics = check_metric_file(metricpath)
        artifacts = {}
        for rel in manifest['artifacts']:
            path = work / rel
            require(path.is_file(), f'missing declared artifact: {rel}')
            require(path.stat().st_size <= MAX_FILE_BYTES, f'artifact exceeds 64 MiB: {rel}')
            artifacts[rel] = filehash(path)
        return metrics, artifacts, stdout.read_text(encoding='utf-8', errors='replace'), stderr.read_text(encoding='utf-8', errors='replace'), duration


def capture(root, out, *, code, data, command, metrics='metrics.json', artifacts=(), timeout=60, seed=0):
    root = Path(root).resolve()
    target = Path(out).resolve()
    require(not target.exists(), f'output exists (refusing to overwrite): {target}')
    require(root.is_dir(), 'experiment root must be an existing directory')
    require(type(timeout) is int and 1 <= timeout <= 3600, 'timeout must be 1..3600 seconds')
    require(type(seed) is int and 0 <= seed <= 2**32 - 1, 'seed must be in 0..2^32-1')
    require(code, 'declare at least one --code file for replay')
    code = [clean_path(x, 'code') for x in code]
    data = [clean_path(x, 'data') for x in data]
    metrics = clean_path(metrics, 'metrics')
    artifacts = [clean_path(x, 'artifact') for x in artifacts]
    require(len(set(code+data)) == len(code+data), 'files must not be duplicated across --code and --data')
    require(len(set(artifacts)) == len(artifacts), 'duplicate artifact')
    require(metrics not in code+data, 'metrics must be an output, not a declared input')
    require(not set(artifacts).intersection(code+data+[metrics]), 'artifact names must not collide with inputs/metrics')
    forbidden = {'__tev_stdout__.txt', '__tev_stderr__.txt'}
    require(not forbidden.intersection(code+data+artifacts+[metrics]), 'reserved capture file name')
    ci = inputs_info(root, code)
    di = inputs_info(root, data)
    protocol = {'schema': 1, 'command': command, 'code': code, 'data': data,
                'metrics': metrics, 'artifacts': artifacts, 'timeout': timeout, 'seed': seed}
    require(isinstance(command, list) and command and all(type(x) is str and x for x in command), 'command is required')
    temp = target.with_name(target.name + '.tmp-' + str(os.getpid()))
    require(not temp.exists(), f'temporary output exists: {temp}')
    try:
        (temp / 'source').mkdir(parents=True)
        for rel in code+data:
            dest = temp / 'source' / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(relative_file(root, rel), dest)
        actual_ci = inputs_info(temp/'source', code)
        actual_di = inputs_info(temp/'source', data)
        require(ci == actual_ci and di == actual_di, 'source inputs changed during capture')
        measured, produced, stdout, stderr, seconds = execute(protocol, temp/'source')
        report = {'version': VERSION, 'mode': 'capture', 'title': ' '.join(command),
                  'protocol_sha256': digest(protocol),
                  'inputs_sha256': {name: row['sha256'] for name, row in di.items()},
                  'plugins_sha256': {name: row['sha256'] for name, row in ci.items()},
                  'metric_units': {key: '' for key in measured},
                  'design': {'arms': ['default'], 'replicates': 1, 'paired': False, 'seed': seed},
                  'observations': [{'arm':'default','replicate':0,'seed':seed,'metrics':measured,'guards':{}}],
                  'claims': [], 'verdict': 'unverified_no_claims',
                  'artifacts_sha256': produced,
                  'environment': {'python': platform.python_version(), 'platform': platform.platform()},
                  'limitations': ['No sandbox or automatic discovery of file/process dependencies.',
                                  'Replay compares declared numeric metrics and declared artifact hashes only.',
                                  'A replay does not prove scientific correctness or portability.']}
        save_json(temp/'capture.json', protocol)
        save_json(temp/'report.json', report)
        save_json(temp/'metrics.json', measured)
        (temp/'stdout.txt').write_text(stdout, encoding='utf-8')
        (temp/'stderr.txt').write_text(stderr, encoding='utf-8')
        (temp/'REPORT.md').write_text('# TEVIEW command capture\n\n'
            + f'Command: `{protocol["command"]!r}`\n\n'
            + 'Mode: deterministic replay check of declared metrics and artifacts.\n\n'
            + '\n'.join(f'- {k}: {v}' for k,v in measured.items()) + '\n', encoding='utf-8')
        target.parent.mkdir(parents=True, exist_ok=True)
        temp.rename(target)
        return {'out':str(target), 'mode':'capture', 'metrics':measured,
                'duration_seconds':seconds,'verdict':'unverified_no_claims'}
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def verify_capture(folder):
    folder = Path(folder).resolve()
    protocol = json.loads((folder/'capture.json').read_text(encoding='utf-8'))
    report = json.loads((folder/'report.json').read_text(encoding='utf-8'))
    require(report.get('mode') == 'capture', 'not a captured experiment')
    require(digest(protocol) == report.get('protocol_sha256'), 'captured protocol was changed')
    root = folder / 'source'
    for kind, record in [('code','plugins_sha256'), ('data','inputs_sha256')]:
        current = {p:filehash(relative_file(root,p)) for p in protocol[kind]}
        require(current == report.get(record), f'{kind} source snapshots changed')
    measured, artifacts, _, _, seconds = execute(protocol, root)
    require(report.get('observations') == [{'arm':'default','replicate':0,'seed':protocol['seed'],
            'metrics':measured,'guards':{}}], 'captured measurement replay differs')
    require(artifacts == report.get('artifacts_sha256'), 'captured artifact replay differs')
    require(report.get('verdict') == 'unverified_no_claims', 'capture verdict was modified')
    require(report.get('metric_units') == {key:'' for key in measured}, 'capture metric units changed')
    require(report.get('design') == {'arms':['default'],'replicates':1,'paired':False,'seed':protocol['seed']},
            'capture experimental design changed')
    return {'verified_replay':True, 'mode':'capture', 'metric_count':len(measured),
            'interpretation':'declared outputs replayed; not scientific or environment validation',
            'duration_seconds':seconds}

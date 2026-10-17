"""Explicit, deterministic regression policies for TEVIEW evidence bundles.

A gate is a project-defined acceptance rule, not a statistical hypothesis test.
No user code is executed during a gate check.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import statistics
import tomllib


class GateError(ValueError):
    """Invalid gate policy or incomparable evidence."""


def ensure(condition, message):
    if not condition:
        raise GateError(message)


def load_report(path):
    p = Path(path).resolve() / 'report.json'
    try:
        document = json.loads(p.read_text(encoding='utf-8'))
    except (OSError, ValueError) as e:
        raise GateError(f'Cannot read evidence report {p}: {e}') from e
    ensure(isinstance(document, dict), 'Evidence report must be a JSON object')
    for name in ('protocol_sha256', 'inputs_sha256', 'design', 'observations'):
        ensure(name in document, f'Evidence report missing {name}')
    return document


def load_policy(path):
    try:
        policy = tomllib.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise GateError(f'Cannot read gate policy: {e}') from e
    ensure(isinstance(policy, dict), 'Policy must be a TOML table')
    ensure(set(policy).issubset({'schema', 'title', 'checks'}), 'Unexpected gate policy keys')
    ensure(policy.get('schema') == 1, 'Gate policy schema must be 1')
    checks = policy.get('checks')
    ensure(isinstance(checks, list) and checks, 'At least one [[checks]] entry is required')
    names = set()
    for idx, check in enumerate(checks):
        where = f'checks[{idx}]'
        ensure(isinstance(check, dict), f'{where} must be a table')
        ensure(set(check).issubset({'id', 'arm', 'metric', 'direction', 'statistic',
                                    'max_absolute_regression', 'max_relative_regression'}), f'{where} contains unknown keys')
        for key in ('id', 'arm', 'metric'):
            ensure(isinstance(check.get(key), str) and check[key].strip(), f'{where}.{key} required')
        ensure(check['id'] not in names, f'Duplicate check id {check["id"]}')
        names.add(check['id'])
        ensure(check.get('direction') in ('increase', 'decrease'), f'{where}.direction must be increase or decrease')
        ensure(check.get('statistic', 'mean') in ('mean', 'worst', 'p95'), f'{where}.statistic must be mean, worst or p95')
        for key in ('max_absolute_regression', 'max_relative_regression'):
            value = check.get(key, 0)
            ensure(type(value) in (int, float) and math.isfinite(value) and value >= 0,
                   f'{where}.{key} must be a nonnegative finite number')
    return policy


def percentile(values, p):
    ordered = sorted(values)
    position = (len(ordered) - 1) * p
    a, b = math.floor(position), math.ceil(position)
    return ordered[a] + (ordered[b] - ordered[a]) * (position - a)


def measure(observations, arm, metric, statistic, direction):
    values = []
    for obs in observations:
        if obs.get('arm') != arm:
            continue
        point = obs.get('metrics', {}).get(metric)
        ensure(type(point) in (int, float) and math.isfinite(point),
               f'Invalid or missing {arm}.{metric} metric')
        values.append(float(point))
    ensure(values, f'No measurements for {arm}.{metric}')
    if statistic == 'mean':
        return statistics.fmean(values), len(values)
    if statistic == 'worst':
        return (max(values) if direction == 'decrease' else min(values)), len(values)
    return percentile(values, 0.95 if direction == 'decrease' else 0.05), len(values)


def gate(baseline_path, candidate_path, policy_path,
         allow_protocol_change=False, allow_input_change=False):
    base, cand = load_report(baseline_path), load_report(candidate_path)
    policy = load_policy(policy_path)
    # A changed implementation is allowed; changed experimental definitions are not by default.
    ensure(allow_protocol_change or base['protocol_sha256'] == cand['protocol_sha256'],
           'Protocol definitions differ; pass --allow-protocol-change only after reviewing changes')
    ensure(allow_input_change or base['inputs_sha256'] == cand['inputs_sha256'],
           'Declared dataset contents differ; pass --allow-input-change only when intentional')
    if 'metric_units' in base and 'metric_units' in cand:
        ensure(base['metric_units'] == cand['metric_units'],
               'Metric units differ; cannot compare physical quantities with incompatible units')
    for key in ('arms', 'replicates', 'paired', 'seed'):
        ensure(base['design'].get(key) == cand['design'].get(key),
               f'Experimental designs differ in {key}; cannot compare')
    records = []
    for check in policy['checks']:
        arm, metric = check['arm'], check['metric']
        direction = check['direction']
        stat = check.get('statistic', 'mean')
        b, nb = measure(base['observations'], arm, metric, stat, direction)
        c, nc = measure(cand['observations'], arm, metric, stat, direction)
        ensure(nb == nc, f'Replication counts differ for {arm}.{metric}')
        # A positive regression is undesirable in the policy's chosen direction.
        regression = c - b if direction == 'decrease' else b - c
        permitted = (check.get('max_absolute_regression', 0) +
                     check.get('max_relative_regression', 0) * abs(b))
        passed = regression <= permitted + 1e-12 * max(1, abs(b), abs(c))
        records.append({'id': check['id'], 'arm': arm, 'metric': metric,
                        'statistic': stat, 'direction': direction,
                        'baseline': b, 'candidate': c,
                        'change': c - b, 'regression': regression,
                        'permitted_regression': permitted, 'count': nb,
                        'status': 'pass' if passed else 'fail'})
    return {
        'status': 'pass' if all(c['status'] == 'pass' for c in records) else 'fail',
        'title': policy.get('title', 'TEVIEW regression gate'),
        'comparability': {'same_protocol': base['protocol_sha256'] == cand['protocol_sha256'],
                          'same_datasets': base['inputs_sha256'] == cand['inputs_sha256'],
                          'same_design': True},
        'checks': records,
        'note': 'Policy evaluation of recorded measurements; not a statistical significance test or proof of scientific validity.'
    }

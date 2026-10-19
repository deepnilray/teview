"""Numerical time-step refinement diagnostics for TEVIEW scene simulations.

Replay checks computational determinism; this module checks whether selected final
observables change appreciably with a smaller integration step. Neither property
alone demonstrates physical-model validity or convergence to the true solution.
"""
from __future__ import annotations

from dataclasses import replace
import math

from teview_physics import PhysicsError, simulate


def _observables(scene, final):
    """Select dynamical channels, not constant or presentation-only outputs."""
    keys = []
    for name in scene.bodies:
        keys.extend(f'{name}.{attribute}' for attribute in ('x', 'y', 'vx', 'vy'))
    for component in scene.components.values():
        if component['kind'] == 'lamp' or (component['kind'] == 'sphere' and component['heat_capacity'] is not None):
            keys.append(f"{component['id']}.temperature")
        if component['kind'] == 'field_probe':
            keys.extend(f"{component['id']}.{a}" for a in ('electric_field_x', 'electric_field_y', 'potential'))
    return {key: float(final[key]) for key in keys if key in final}


def _comparison(left, right, initial, abs_tol, rel_tol):
    result = {}
    for key in sorted(left):
        a, b = left[key], right[key]
        delta = abs(b-a)
        # Symmetric scaling is independent of whether a or b is the reference.
        variation = max(abs(a-initial[key]), abs(b-initial[key]))
        permitted = abs_tol + rel_tol*variation
        result[key] = {
            'coarser': a,
            'finer': b,
            'absolute_change': delta,
            'reference_variation': variation,
            'permitted_change': permitted,
            'within_tolerance': delta <= permitted,
        }
    return result


def check_convergence(scene, *, relative_tolerance=1e-3, absolute_tolerance=1e-6):
    """Run dt, dt/2, dt/4 on the same scene; check the two finest outputs.

    Fail on under-resolved outputs or insufficient resources. The result is a
    heuristic *time-step sensitivity* diagnostic, not a proof of global error.
    """
    for name, value in (('relative_tolerance', relative_tolerance),
                        ('absolute_tolerance', absolute_tolerance)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise PhysicsError(f'{name}: expected a finite nonnegative number')
    if relative_tolerance == 0 and absolute_tolerance == 0:
        raise PhysicsError('At least one convergence tolerance must be positive')

    levels = []
    for factor in (1, 2, 4):
        finer_dt = scene.dt / factor
        steps = math.ceil(scene.duration / finer_dt)
        if steps > 100000:
            raise PhysicsError(f'dt/{factor}: exceeds the 100000-step limit; shorten duration or raise initial dt')
        configured = replace(scene, dt=finer_dt, steps=steps)
        report, _ = simulate(configured)
        levels.append({'dt_s': finer_dt, 'steps': steps, 'observables': _observables(scene, report['final']),
                       'initial': _observables(scene, report['initial'])})

    names = list(levels[0]['observables'])
    if not names:
        raise PhysicsError('No supported dynamical observables to check for convergence')
    coarse = _comparison(levels[0]['observables'], levels[1]['observables'], levels[0]['initial'], absolute_tolerance, relative_tolerance)
    fine = _comparison(levels[1]['observables'], levels[2]['observables'], levels[0]['initial'], absolute_tolerance, relative_tolerance)
    failing = [k for k, v in fine.items() if not v['within_tolerance']]
    result = {
        'status': 'sensitive_to_time_step' if failing else 'refinement_stable',
        'source_sha256': scene.source_hash,
        'comparison': 'same scene, final simulated time; dt/2 against dt/4',
        'tolerances': {'absolute': absolute_tolerance, 'relative': relative_tolerance},
        'levels': [{'dt_s': k['dt_s'], 'steps': k['steps']} for k in levels],
        'coarse_to_medium': coarse,
        'medium_to_fine': fine,
        'failing_observables': failing,
        'limitations': [
            'Agreement between successive resolutions is not independent scientific validation.',
            'Two similar results can share the same modeling or numerical bias.',
            'Impacts, topology changes and chaotic dynamics may fail pointwise final-state agreement.',
            'Relative tolerance scales with change from initial state, not absolute coordinate or Kelvin offset.',
            'Absolute tolerance applies to native SI values and may require quantity-specific calibration.',
            'No automatic estimate of truncation error order or guarantee of stability between samples.',
        ],
    }
    return result

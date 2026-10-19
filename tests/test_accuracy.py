"""Tests for observable-specific refinement checks and failure boundaries."""
import math
import unittest

from teview_accuracy import check_convergence
from teview_physics import PhysicsError, compile_scene


def scene(*, sphere=True, dt=.05, duration=1., spring=False):
    components = []
    if sphere:
        components.append(dict(kind='sphere', id='moving', mass=1.0, radius=.1,
                               position=[0., 1.], velocity=[2., 0.]))
    if spring:
        components += [dict(kind='anchor', id='anchor', position=[0., 1.]),
                       dict(kind='spring', id='spring', a='anchor', b='moving',
                            stiffness=40., rest_length=.2)]
    if not components:
        components = [dict(kind='battery', id='cell', voltage=3.)]
    return compile_scene({'schema':1,'world':{'duration':duration,'dt':dt,
                       'gravity':[0., -9.81] if not spring else [0., 0.]},'components':components})


class AccuracyTests(unittest.TestCase):
    def test_ballistic_refinement_stable(self):
        report = check_convergence(scene())
        self.assertEqual(report['status'], 'refinement_stable')
        self.assertEqual(report['failing_observables'], [])
        self.assertEqual(len(report['levels']), 3)
        self.assertIn('moving.y', report['medium_to_fine'])

    def test_stiff_oscillation_detects_under_resolution(self):
        s=scene(dt=.02,duration=.85,spring=True)
        report = check_convergence(s, relative_tolerance=1e-12,
                                   absolute_tolerance=1e-12)
        self.assertEqual(report['status'], 'sensitive_to_time_step')
        self.assertIn('moving.x', report['failing_observables'])

    def test_tolerance_makes_acceptance_explicit(self):
        s=scene(dt=.02,duration=.85,spring=True)
        loose = check_convergence(s, relative_tolerance=1., absolute_tolerance=1.)
        self.assertEqual(loose['status'], 'refinement_stable')

    def test_no_dynamical_objects_rejected(self):
        with self.assertRaisesRegex(PhysicsError, 'No supported dynamical'):
            check_convergence(scene(sphere=False))

    def test_invalid_tolerances_rejected(self):
        for kw in [{'relative_tolerance':float('nan')},
                   {'relative_tolerance':-1},
                   {'absolute_tolerance':float('inf')},
                   {'absolute_tolerance':0, 'relative_tolerance':0}]:
            with self.subTest(kw=kw), self.assertRaises(PhysicsError):
                check_convergence(scene(), **kw)

    def test_excessive_refinement_rejected_before_run(self):
        with self.assertRaisesRegex(PhysicsError, '100000-step'):
            check_convergence(scene(dt=.00005,duration=2.))

if __name__ == '__main__':
    unittest.main()

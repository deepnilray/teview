"""Cross-domain electrostatic composition tests."""
import math
import unittest

from teview_physics import COULOMB, PhysicsError, compile_scene, simulate


def sphere(name, x, charge, mass=1.0):
    return dict(id=name, kind='sphere', position=[x, 0], radius=.01,
                mass=mass, charge=charge)


def charge(name, x, q):
    return dict(id=name, kind='fixed_charge', position=[x, 0], charge=q)


def probe(name, x):
    return dict(id=name, kind='field_probe', position=[x, 0])


def scene(parts, **world):
    return dict(schema=1, components=parts, world=dict(
        gravity=[0, 0], duration=.01, dt=.001, **world))


class ElectrostaticTests(unittest.TestCase):
    def test_inverse_square_and_potential(self):
        r, _ = simulate(compile_scene(scene([
            charge('q', 0, 1e-9), probe('near', 1), probe('far', 2)])))
        a = r['initial']
        self.assertAlmostEqual(a['near.electric_field_x'], COULOMB * 1e-9)
        self.assertAlmostEqual(a['near.electric_field_x'] / a['far.electric_field_x'], 4)
        self.assertAlmostEqual(a['near.potential'] / a['far.potential'], 2)

    def test_superposition(self):
        r, _ = simulate(compile_scene(scene([
            charge('left', -1, 1e-9), charge('right', 1, 1e-9),
            probe('center', 0)], electric_field=[30, 0])))
        self.assertAlmostEqual(r['initial']['center.electric_field_x'], 30)

    def test_sign_reversal(self):
        a = simulate(compile_scene(scene([charge('q', 0, 1e-8), probe('p', 1)])))[0]
        b = simulate(compile_scene(scene([charge('q', 0, -1e-8), probe('p', 1)])))[0]
        self.assertAlmostEqual(a['initial']['p.electric_field_x'], -
                               b['initial']['p.electric_field_x'])

    def test_permittivity(self):
        parts = [charge('q', 0, 1e-8), probe('p', 1)]
        x = simulate(compile_scene(scene(parts)))[0]['initial']['p.electric_field_x']
        y = simulate(compile_scene(scene(parts, relative_permittivity=4)))[0]['initial']['p.electric_field_x']
        self.assertAlmostEqual(x / y, 4)

    def test_pair_momentum(self):
        r, _ = simulate(compile_scene(scene([
            sphere('a', -.5, 3e-7, 2), sphere('b', .5, -4e-7, 3)],
            duration=.3, dt=.0002)))
        v = r['final']
        self.assertAlmostEqual(2 * v['a.vx'] + 3 * v['b.vx'], 0, places=10)

    def test_pair_energy(self):
        r, _ = simulate(compile_scene(scene([
            sphere('a', -.5, 3e-7), sphere('b', .5, 5e-7)],
            duration=.2, dt=.001)))
        def energy(row):
            kinetic = .5 * (row['a.vx'] ** 2 + row['a.vy'] ** 2 +
                            row['b.vx'] ** 2 + row['b.vy'] ** 2)
            d = math.hypot(row['a.x'] - row['b.x'], row['a.y'] - row['b.y'])
            return kinetic + COULOMB * 3e-7 * 5e-7 / d
        self.assertAlmostEqual(energy(r['initial']), energy(r['final']), delta=1e-10)

    def test_charge_accelerates_without_special_experiment(self):
        r, _ = simulate(compile_scene(scene([
            charge('fixture', 0, 1e-6), sphere('unfamiliar_payload', 1, 1e-6)],
            duration=.001, dt=.00001)))
        self.assertGreater(r['final']['unfamiliar_payload.x'], 1)

    def test_neutral_sphere_does_not_accelerate(self):
        r, _ = simulate(compile_scene(scene([
            charge('fixture', 0, 1e-6), sphere('neutral', 1, 0)],
            duration=1, dt=.01)))
        self.assertEqual(r['final']['neutral.x'], 1)

    def test_singular_probe_rejected(self):
        with self.assertRaisesRegex(PhysicsError, 'inside/on charged object'):
            simulate(compile_scene(scene([charge('q', 0, 1e-6), probe('p', 0)])))

    def test_invalid_dielectric_rejected(self):
        for value in [0, -1, True]:
            with self.subTest(value=value), self.assertRaises(PhysicsError):
                compile_scene(scene([charge('q', 0, 1e-6)],
                                    relative_permittivity=value))

    def test_explicit_probe_law_discovery(self):
        model = compile_scene(scene([
            charge('source', 0, 1e-8), sphere('moving', 1, 2e-8),
            probe('meter', 2)]))
        relationships = [x['objects'] for x in model.interactions
                         if x['law'] == 'electric_probe']
        self.assertIn(['meter', 'source'], relationships)
        self.assertIn(['meter', 'moving'], relationships)

    def test_interaction_budget(self):
        parts = [sphere('q' + str(i), i + 1, 1e-10) for i in range(10)]
        with self.assertRaisesRegex(PhysicsError, 'workload'):
            simulate(compile_scene(scene(parts, duration=100, dt=.001)))


if __name__ == '__main__':
    unittest.main()

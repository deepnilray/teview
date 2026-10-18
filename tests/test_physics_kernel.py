"""Selected analytical, compositional, and adversarial tests for the scene kernel."""
import copy
import json
import math
import tempfile
import unittest
from pathlib import Path
from teview_physics import PhysicsError, compile_scene, displaced_volume, load_scene, simulate, verify_scene


def sphere(name='body', x=0, y=2, mass=1, charge=0, vx=0):
    return dict(kind='sphere', id=name, position=[x,y], velocity=[vx,0],
                radius=.1, mass=mass, charge=charge)


def model(components, world=None, connections=None, definitions=None):
    return compile_scene(dict(schema=1, title='independent assembly',
                              components=components,
                              world=world if world is not None else {'duration':.2,'dt':.001},
                              connections=connections or [],
                              definitions=definitions or []))


def circuit(closed=True):
    parts = [dict(id='cell',kind='battery',voltage=12),
             dict(id='gate',kind='switch',closed=closed),
             dict(id='lamp',kind='lamp',resistance=24,light_fraction=.2)]
    wires = [dict(a='cell.positive',b='gate.a'),dict(a='gate.b',b='lamp.a'),
             dict(a='lamp.b',b='cell.negative')]
    return parts,wires


class MechanicalLawTests(unittest.TestCase):
    def test_gravity_follows_analytical_motion(self):
        obj=sphere('unanticipated_object',y=8)
        s=model([obj],{'duration':.6,'dt':.01})
        r,_=simulate(s)
        self.assertAlmostEqual(r['final']['unanticipated_object.y'],
                               8-.5*9.81*.6**2, places=9)

    def test_free_fall_independent_of_mass(self):
        a=simulate(model([sphere(mass=1)]))[0]['final']['body.y']
        b=simulate(model([sphere(mass=20)]))[0]['final']['body.y']
        self.assertAlmostEqual(a,b,places=10)

    def test_uniform_electric_force_charge_mass(self):
        w={'gravity':[0,0],'electric_field':[40,0],'duration':1,'dt':.01}
        r,_=simulate(model([sphere(charge=.5,mass=2,y=0)],w))
        self.assertAlmostEqual(r['final']['body.x'],5,places=8)

    def test_neutral_body_ignores_field(self):
        w={'gravity':[0,0],'electric_field':[100,0],'duration':1,'dt':.01}
        self.assertEqual(simulate(model([sphere(y=0)],w))[0]['final']['body.x'],0)

    def test_spherical_cap_formula(self):
        r=.2;v=4/3*math.pi*r**3
        self.assertAlmostEqual(displaced_volume(r,0,-1,1),v)
        self.assertAlmostEqual(displaced_volume(r,0,-1,0),v/2)

    def test_neutral_buoyancy(self):
        r=.1;rho=1000
        m=4/3*math.pi*r**3*rho
        obj=sphere(y=0,mass=m);obj['radius']=r
        water=dict(id='fluid',kind='fluid',surface=2,bottom=-2,density=rho)
        r,_=simulate(model([obj,water],{'duration':.5,'dt':.005}))
        self.assertAlmostEqual(r['final']['body.y'],0,places=8)

    def test_sphere_rises_in_dense_fluid(self):
        obj=sphere(y=0,mass=.2)
        fluid=dict(id='water',kind='fluid',surface=2,bottom=-2,density=1000)
        r,_=simulate(model([obj,fluid]))
        self.assertGreater(r['final']['body.y'],0)

    def test_spring_acts_without_named_template(self):
        objs=[sphere('equipment',x=1,y=0),
              dict(id='mount',kind='anchor',position=[0,0]),
              dict(id='element',kind='spring',a='mount',b='equipment',
                   rest_length=.5,stiffness=20)]
        s=model(objs,{'gravity':[0,0],'duration':.1,'dt':.001})
        self.assertIn('hooke',[law['law'] for law in s.interactions])
        self.assertLess(simulate(s)[0]['final']['equipment.x'],1)

    def test_rope_only_carries_tension(self):
        objs=[sphere(x=.4,y=0),
              dict(id='anchor',kind='anchor',position=[0,0]),
              dict(id='line',kind='rope',a='anchor',b='body',length=.6,stiffness=40)]
        s=model(objs,{'gravity':[0,0],'duration':.1,'dt':.002})
        self.assertAlmostEqual(simulate(s)[0]['final']['body.x'],.4)

    def test_impact_preserves_momentum(self):
        a=sphere('left',x=-.25,y=0,mass=2,vx=1)
        b=sphere('right',x=.25,y=0,mass=3,vx=0)
        final=simulate(model([a,b],{'gravity':[0,0],'duration':.4,'dt':.001}))[0]['final']
        momentum=2*final['left.vx']+3*final['right.vx']
        energy=.5*2*final['left.vx']**2+.5*3*final['right.vx']**2
        self.assertAlmostEqual(momentum,2,places=8)
        self.assertAlmostEqual(energy,1,places=8)

    def test_floor_rebounds(self):
        body=sphere(y=.2)
        body['velocity']=[0,-3]
        floor=dict(id='ground',kind='floor',height=0,restitution=.5)
        end=simulate(model([body,floor],{'duration':.09,'dt':.0005}))[0]['final']
        self.assertGreaterEqual(end['body.y'],.1)
        self.assertGreater(end['body.vy'],0)


class ElectrothermalTests(unittest.TestCase):
    def test_closed_circuit_powers_lamp(self):
        parts,wires=circuit()
        end=simulate(model(parts,connections=wires))[0]['final']
        self.assertAlmostEqual(abs(end['lamp.current']),.5)
        self.assertAlmostEqual(end['lamp.power'],6)
        self.assertAlmostEqual(end['lamp.light_power'],1.2)
        self.assertGreater(end['lamp.temperature'],293.15)

    def test_open_switch_no_light(self):
        parts,wires=circuit(False)
        end=simulate(model(parts,connections=wires))[0]['final']
        self.assertEqual(end['lamp.power'],0)
        self.assertEqual(end['lamp.light_power'],0)

    def test_electric_field_not_a_fictional_battery(self):
        parts,wires=circuit(False)
        w={'electric_field':[100,0],'duration':.2,'dt':.01}
        self.assertEqual(simulate(model(parts,w,wires))[0]['final']['lamp.light_power'],0)

    def test_unwired_lamp_is_dark(self):
        end=simulate(model([dict(id='lamp',kind='lamp',resistance=20)]))[0]['final']
        self.assertEqual(end['lamp.power'],0)

    def test_change_resistance_changes_power(self):
        parts,wires=circuit()
        before=simulate(model(parts,connections=wires))[0]['final']['lamp.power']
        parts=copy.deepcopy(parts)
        parts[-1]['resistance']=48
        after=simulate(model(parts,connections=wires))[0]['final']['lamp.power']
        self.assertAlmostEqual(before,2*after)

    def test_series_resistance_and_kirchhoff(self):
        parts=[dict(id='cell',kind='battery',voltage=12),
               dict(id='A',kind='lamp',resistance=10),
               dict(id='B',kind='lamp',resistance=20)]
        wires=[dict(a='cell.positive',b='A.a'),dict(a='A.b',b='B.a'),
               dict(a='B.b',b='cell.negative')]
        end=simulate(model(parts,connections=wires))[0]['final']
        self.assertAlmostEqual(abs(end['A.current']),.4)
        self.assertAlmostEqual(abs(end['B.current']),.4)
        self.assertAlmostEqual(end['A.power']+end['B.power'],4.8)

    def test_ideal_source_short_rejected(self):
        parts=[dict(id='cell',kind='battery',voltage=12)]
        with self.assertRaisesRegex(PhysicsError,'short-circuited'):
            simulate(model(parts,connections=[dict(a='cell.positive',b='cell.negative')]))

    def test_independent_domains_can_coexist(self):
        parts,wires=circuit()
        parts.append(sphere(name='charged',y=0,charge=.5))
        w={'gravity':[0,0],'electric_field':[20,0],'duration':1,'dt':.01}
        end=simulate(model(parts,w,wires))[0]['final']
        self.assertAlmostEqual(end['charged.x'],5)
        self.assertGreater(end['lamp.light_power'],0)


class CompilerAndReplayTests(unittest.TestCase):
    def test_reusable_definition(self):
        s=model([dict(id='sample',kind='our_lamp')],
                definitions=[dict(name='our_lamp',base='lamp',resistance='10 ohm')])
        self.assertEqual(s.components['sample']['resistance'],10)

    def test_wrong_units_rejected(self):
        b=sphere();b['mass']='8 V'
        with self.assertRaisesRegex(PhysicsError,'incompatible'):
            model([b])

    def test_unknown_property_rejected(self):
        b=sphere();b['teleport']=True
        with self.assertRaisesRegex(PhysicsError,'unknown properties'):
            model([b])

    def test_negative_mass_rejected(self):
        with self.assertRaises(PhysicsError):
            model([sphere(mass=-3)])

    def test_unsupported_physics_rejected(self):
        with self.assertRaisesRegex(PhysicsError,'unknown settings'):
            model([sphere()],{'magnetic_field':[0,1]})

    def test_overlapping_fluids_rejected(self):
        a=dict(id='a',kind='fluid',bottom=0,surface=2,density=1000)
        b=dict(id='b',kind='fluid',bottom=1,surface=3,density=500)
        with self.assertRaisesRegex(PhysicsError,'overlaps'):
            model([sphere(),a,b])

    def test_large_step_rejected_for_stiff_link(self):
        parts=[sphere(),dict(id='fixture',kind='anchor',position=[0,0]),
               dict(id='link',kind='spring',a='body',b='fixture',
                    stiffness=100000,rest_length=1)]
        with self.assertRaisesRegex(PhysicsError,'dt too large'):
            simulate(model(parts,{'duration':1,'dt':.1}))

    def test_replay_rejects_modified_output(self):
        src=Path(__file__).resolve().parents[1]/'examples/scenes/electrothermal.tev'
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)
            simulate(load_scene(src),dest)
            (dest/'scene.tev').write_bytes(src.read_bytes())
            self.assertEqual(verify_scene(dest)['status'],'replayed')
            (dest/'measurements.csv').write_text('falsified')
            with self.assertRaisesRegex(PhysicsError,'Replay mismatch'):
                verify_scene(dest)

    def test_replay_rejects_modified_source(self):
        src=Path(__file__).resolve().parents[1]/'examples/scenes/electrothermal.tev'
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)
            simulate(load_scene(src),dest)
            (dest/'scene.tev').write_bytes(src.read_bytes()+b'\n# altered')
            with self.assertRaisesRegex(PhysicsError,'hash mismatch'):
                verify_scene(dest)

    def test_optical_flux_warms_separate_absorber(self):
        root=Path(__file__).resolve().parents[1]/'examples/scenes'
        model=load_scene(root/'opto_thermal.tev')
        report,_=simulate(model)
        end=report['final']
        self.assertIn('radiative_absorption',[i['law'] for i in model.interactions])
        self.assertAlmostEqual(end['emitter.light_power'],3.)
        self.assertAlmostEqual(end['receiver.absorbed_power'],.075)
        self.assertAlmostEqual(end['receiver.temperature']-293.15,1.5,places=6)

    def test_inverse_square_optical_distance(self):
        root=Path(__file__).resolve().parents[1]/'examples/scenes'
        import tomllib
        raw=tomllib.loads((root/'opto_thermal.tev').read_text())
        close=simulate(compile_scene(raw))[0]['final']['receiver.absorbed_power']
        raw['components'][2]['position']=[.6,0]
        far=simulate(compile_scene(raw))[0]['final']['receiver.absorbed_power']
        self.assertAlmostEqual(close,4*far,places=10)

    def test_absorber_requires_thermal_properties(self):
        body=sphere();body['absorptivity']=.8
        with self.assertRaisesRegex(PhysicsError,'heat_capacity'):
            model([body])

    def test_no_power_no_light_no_absorber_heating(self):
        root=Path(__file__).resolve().parents[1]/'examples/scenes'
        import tomllib
        raw=tomllib.loads((root/'opto_thermal.tev').read_text())
        raw['connections']=[]
        end=simulate(compile_scene(raw))[0]['final']
        self.assertEqual(end['emitter.light_power'],0)
        self.assertEqual(end['receiver.absorbed_power'],0)

    def test_example_compositions_execute(self):
        root=Path(__file__).resolve().parents[1]/'examples/scenes'
        for filename in ('electrothermal.tev','ball_water_spring.tev','opto_thermal.tev'):
            with self.subTest(filename=filename):
                report,rows=simulate(load_scene(root/filename))
                self.assertEqual(report['status'],'simulated_not_validated')
                self.assertGreater(len(rows),1)


if __name__=='__main__':
    unittest.main()

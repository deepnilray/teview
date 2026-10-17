import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import tev

class TEVTest(unittest.TestCase):
    def setUp(self):
        self.work=tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root=Path(self.work.name)
        self.examples=self.root/'examples'
        shutil.copytree(ROOT/'examples',self.examples)
        self.ab=self.examples/'ab_test'/'experiment.tev'
        self.physics=self.examples/'physics'/'experiment.tev'
        self.data=self.examples/'data'/'experiment.tev'

    def textedit(self,path,a,b):
        text=path.read_text();self.assertIn(a,text);path.write_text(text.replace(a,b))

    def test_01_all_four_specs_validate(self):
        for f in self.examples.glob('*/experiment.tev'):
            tev.plan(f)

    def test_02_ab_dag(self):
        x=tev.plan(self.ab)
        self.assertEqual([s['id'] for s in x['steps']],['sample','normalize'])
        self.assertEqual(x['total_step_invocations'],128)

    def test_03_four_distinct_domains(self):
        for k in ('ab_test','physics','software','data'):
            path=self.examples/k/'experiment.tev'
            report,_=tev.run(path,self.root/k,allow_python=k!='ab_test')
            self.assertEqual(len(report['observations']),report['design']['replicates']*len(report['design']['arms']))

    def test_04_simulated_aba_effect(self):
        report,_=tev.run(self.ab,self.root/'ab')
        self.assertEqual(report['claims'][0]['status'],'supported_by_interval')
        self.assertGreater(report['claims'][0]['oriented_effect'],0.08)

    def test_05_paired_same_seed(self):
        rep,_=tev.run(self.ab,self.root/'ab')
        obs=rep['observations']
        self.assertEqual(obs[0]['seed'],obs[1]['seed'])

    def test_06_unpaired_different_seed(self):
        self.textedit(self.ab,'paired = true','paired = false')
        rep,_=tev.run(self.ab,self.root/'ab')
        obs=rep['observations']
        self.assertNotEqual(obs[0]['seed'],obs[1]['seed'])

    def test_07_replay(self):
        tev.run(self.ab,self.root/'ab')
        self.assertTrue(tev.verify(self.root/'ab')['verified_replay'])

    def test_08_copy_and_replay(self):
        tev.run(self.physics,self.root/'physics_run',allow_python=True)
        shutil.copytree(self.root/'physics_run',self.root/'other')
        self.assertTrue(tev.verify(self.root/'other',allow_python=True)['verified_replay'])

    def test_09_source_change_detected(self):
        tev.run(self.ab,self.root/'ab')
        p=self.root/'ab/source/experiment.tev';p.write_text(p.read_text()+'\n# corruption')
        with self.assertRaises(tev.ExperimentError):tev.verify(self.root/'ab')

    def test_10_data_change_detected(self):
        tev.run(self.data,self.root/'d',allow_python=True)
        with open(self.root/'d/source/study.csv','a') as f:f.write('101\n')
        with self.assertRaises(tev.ExperimentError):tev.verify(self.root/'d',allow_python=True)

    def test_11_plugin_change_detected(self):
        tev.run(self.physics,self.root/'p',allow_python=True)
        with open(self.root/'p/source/physics.py','a') as f:f.write('\n# altered\n')
        with self.assertRaises(tev.ExperimentError):tev.verify(self.root/'p',allow_python=True)

    def test_12_report_tampering_detected(self):
        tev.run(self.ab,self.root/'ab')
        p=self.root/'ab/report.json';x=json.loads(p.read_text())
        x['observations'][0]['metrics']['conversion']=999
        p.write_text(json.dumps(x))
        with self.assertRaises(tev.ExperimentError):tev.verify(self.root/'ab')

    def test_13_python_disabled_by_default(self):
        with self.assertRaises(tev.ExperimentError):tev.run(self.physics,self.root/'p')
        self.assertFalse((self.root/'p').exists())

    def test_14_python_cache_cannot_bypass_trust_flag(self):
        cache=self.root/'cache'
        tev.run(self.physics,self.root/'p',allow_python=True,cache=cache)
        with self.assertRaises(tev.ExperimentError):tev.run(self.physics,self.root/'q',cache=cache)

    def test_15_cache_hit_same_inputs(self):
        cache=self.root/'cache'
        tev.run(self.ab,self.root/'a',cache=cache)
        _,counts=tev.run(self.ab,self.root/'b',cache=cache)
        self.assertEqual(counts['miss'],0)
        self.assertEqual(counts['hit'],128)

    def test_16_cache_invalidated_input_change(self):
        cache=self.root/'cache'; tev.run(self.ab,self.root/'a',cache=cache)
        self.textedit(self.ab,'sessions = 1600','sessions = 700')
        _,count=tev.run(self.ab,self.root/'b',cache=cache)
        self.assertGreater(count['miss'],0)

    def test_17_cache_invalidated_plugin_change(self):
        cache=self.root/'cache'; tev.run(self.physics,self.root/'a',cache=cache,allow_python=True)
        with open(self.examples/'physics/physics.py','a') as f:f.write('\n# new code version')
        _,count=tev.run(self.physics,self.root/'b',cache=cache,allow_python=True)
        self.assertGreater(count['miss'],0)

    def test_18_tampered_cache_recomputed(self):
        cache=self.root/'cache'; tev.run(self.ab,self.root/'a',cache=cache)
        one=next(cache.glob('*.json'))
        one.write_text('{"key":"bad","result":{"value":999},"digest":"bad"}')
        _,c=tev.run(self.ab,self.root/'b',cache=cache)
        self.assertGreaterEqual(c['miss'],1)

    def test_19_no_cache(self):
        cache=self.root/'cache'; tev.run(self.ab,self.root/'a',cache=cache)
        _,c=tev.run(self.ab,self.root/'b',cache=cache,no_cache=True)
        self.assertEqual(c['hit'],0)

    def test_20_forbid_duplicate_output_dir(self):
        tev.run(self.ab,self.root/'a')
        with self.assertRaises(tev.ExperimentError):tev.run(self.ab,self.root/'a')

    def test_21_unsupported_top_level_key(self):
        self.textedit(self.ab,'schema = 1','schema = 1\nexploit = true')
        with self.assertRaises(tev.ExperimentError):tev.plan(self.ab)

    def test_22_unsupported_step_key(self):
        self.textedit(self.ab,'uses = "builtin:bernoulli"','uses = "builtin:bernoulli"\ntimeout = 2')
        with self.assertRaises(tev.ExperimentError):tev.plan(self.ab)

    def test_23_unresolved_reference(self):
        self.textedit(self.ab,'${parameters.sessions}','${parameters.missing}')
        with self.assertRaises(tev.ExperimentError):tev.plan(self.ab)

    def test_24_malformed_reference(self):
        self.textedit(self.ab,'${parameters.sessions}','x${parameters.sessions}')
        with self.assertRaises(tev.ExperimentError):tev.plan(self.ab)

    def test_25_bad_output_field(self):
        self.textedit(self.ab,'${steps.sample.successes}','${steps.sample.missing}')
        with self.assertRaises(tev.ExperimentError):tev.plan(self.ab)

    def test_26_cycle_detection(self):
        self.textedit(self.ab,'p = "${arm.probability}"','p = "${steps.normalize.value}"')
        with self.assertRaises(tev.ExperimentError):tev.plan(self.ab)

    def test_27_invalid_claim(self):
        self.textedit(self.ab,'metric = "conversion"','metric = "not_a_metric"')
        with self.assertRaises(tev.ExperimentError):tev.plan(self.ab)

    def test_28_invalid_confidence(self):
        self.textedit(self.ab,'confidence = 0.95','confidence = 1.0')
        with self.assertRaises(tev.ExperimentError):tev.plan(self.ab)

    def test_29_output_must_be_finite(self):
        with self.assertRaises(tev.ExperimentError):tev.check_type(float('nan'),'number','x')
        with self.assertRaises(tev.ExperimentError):tev.check_type(True,'integer','x')

    def test_30_csv_path_escape_rejected(self):
        self.textedit(self.data,'study = "study.csv"','study = "../../outside.csv"')
        with self.assertRaises(tev.ExperimentError):tev.plan(self.data)

    def test_31_relative_plugin_escape_rejected(self):
        self.textedit(self.physics,'python:physics.py:projectile','python:../../bad.py:projectile')
        with self.assertRaises(tev.ExperimentError):tev.plan(self.physics)

    def test_32_builtin_csv_rejects_untracked_file(self):
        self.textedit(self.ab,'uses = "builtin:bernoulli"','uses = "builtin:csv_column"')
        with self.assertRaises(tev.ExperimentError):tev.plan(self.ab)

    def test_33_wrong_step_type_fails(self):
        self.textedit(self.ab,'successes = "integer"','successes = "boolean"')
        with self.assertRaises(tev.ExperimentError):tev.run(self.ab,self.root/'a')

    def test_34_bounded_reps(self):
        self.textedit(self.ab,'replicates = 32','replicates = 10001')
        with self.assertRaises(tev.ExperimentError):tev.plan(self.ab)

    def test_35_declared_dataset_hash(self):
        r,_=tev.run(self.data,self.root/'d',allow_python=True)
        self.assertIn('study',r['inputs_sha256'])
        self.assertEqual(len(r['inputs_sha256']['study']),64)

    def test_36_deterministic_physics_not_statistical_evidence(self):
        r,_=tev.run(self.physics,self.root/'p',allow_python=True)
        self.assertEqual(r['claims'][0]['status'],'computational_comparison_only')
        self.assertEqual(r['verdict'],'inconclusive')

    def test_37_unverified_no_claim(self):
        self.ab.write_text(self.ab.read_text().split('[[claims]]')[0])
        r,_=tev.run(self.ab,self.root/'a')
        self.assertEqual(r['verdict'],'unverified_no_claims')

    def test_38_comparison(self):
        tev.run(self.ab,self.root/'a')
        tev.run(self.ab,self.root/'b')
        comp=tev.compare(self.root/'a',self.root/'b')
        self.assertTrue(comp['same_protocol'])
        self.assertEqual(comp['metric_means']['control.conversion']['difference'],0.0)

    def test_39_lineage_and_csv(self):
        tev.run(self.ab,self.root/'a')
        report=json.loads((self.root/'a/lineage.json').read_text())
        self.assertEqual(len(report['steps']),64)
        self.assertEqual(len((self.root/'a/measurements.csv').read_text().splitlines()),65)

    def test_40_explicit_negative_threshold(self):
        self.textedit(self.ab,'threshold = 0.05','threshold = 0.99')
        r,_=tev.run(self.ab,self.root/'a')
        self.assertEqual(r['claims'][0]['status'],'contradicted_by_interval')

    def test_41_opaque_string_not_evaluated(self):
        injection='__import__(\\"os\\").system(\\"touch /tmp/pwned_tev\\")'
        self.assertEqual(tev.resolve(injection,{}),injection)

    def test_42_paired_seed_independent_of_arm(self):
        self.assertEqual(tev.seed_for(2,3,'x',True),tev.seed_for(2,3,'y',True))
        self.assertNotEqual(tev.seed_for(2,3,'x',False),tev.seed_for(2,3,'y',False))

    def test_43_exact_declaration_of_claim_metric(self):
        self.textedit(self.ab,'source = "${steps.normalize.value}"','source = "${steps.sample.total}"')
        self.assertEqual(tev.plan(self.ab)['declared_hypotheses'],['variant_improves_conversion'])

    def test_45_guards_executed_all_runs(self):
        r,_=tev.run(self.ab,self.root/'a')
        self.assertEqual(r['guard_count'],2)
        self.assertTrue(all(len(o['guards'])==2 for o in r['observations']))

    def test_46_failed_guard_prevents_published_results(self):
        self.textedit(self.ab,'value = 1.0','value = 0.01')
        with self.assertRaisesRegex(tev.ExperimentError,'guard probability_upper_bound failed'):
            tev.run(self.ab,self.root/'a')
        self.assertFalse((self.root/'a').exists())

    def test_47_unsupported_guard_op(self):
        self.textedit(self.ab,'op = ">="','op = "eval"')
        with self.assertRaises(tev.ExperimentError):tev.plan(self.ab)

    def test_48_invalid_guard_output(self):
        self.textedit(self.ab,'source = "${steps.sample.rate}"','source = "${steps.sample.no_such_field}"')
        with self.assertRaises(tev.ExperimentError):tev.plan(self.ab)

    def test_49_guard_mixed_type_rejected(self):
        self.textedit(self.ab,'value = 0.0','value = "abc"')
        with self.assertRaises(tev.ExperimentError):tev.run(self.ab,self.root/'a')

    def test_50_randomized_protocols_are_deterministic(self):
        a,_=tev.run(self.ab,self.root/'a')
        b,_=tev.run(self.ab,self.root/'b')
        self.assertEqual(a['observations'],b['observations'])
        self.assertEqual(a['claims'],b['claims'])

    def test_51_outputs_not_necessarily_verified(self):
        s=self.ab.read_text().split('[[claims]]')[0]
        self.ab.write_text(s)
        report,_=tev.run(self.ab,self.root/'a')
        self.assertEqual(report['verdict'],'unverified_no_claims')
        self.assertTrue(tev.verify(self.root/'a')['verified_replay'])

    def test_52_plugin_output_nonjson_rejected(self):
        physics=self.examples/'physics/physics.py'
        physics.write_text(physics.read_text().replace("return {'height':float(y)","return {'height':float('nan')"))
        with self.assertRaises(tev.ExperimentError):tev.run(self.physics,self.root/'a',allow_python=True)

    def test_53_stage_lineage_tamper_detected(self):
        tev.run(self.ab,self.root/'a')
        p=self.root/'a/lineage.json';content=json.loads(p.read_text())
        content['steps'][0]['steps'][0]['outputs']['rate']=0.999
        p.write_text(json.dumps(content))
        with self.assertRaises(tev.ExperimentError):tev.verify(self.root/'a')

    def test_54_data_study_is_relocatable(self):
        tev.run(self.data,self.root/'data_run',allow_python=True)
        shutil.copytree(self.root/'data_run',self.root/'relocated')
        self.assertTrue(tev.verify(self.root/'relocated',allow_python=True)['verified_replay'])

    def test_44_no_output_on_failing_experiment(self):
        self.textedit(self.ab,'sessions = 1600','sessions = 0')
        with self.assertRaises(tev.ExperimentError):tev.run(self.ab,self.root/'bad')
        self.assertFalse((self.root/'bad').exists())

if __name__=='__main__':unittest.main()

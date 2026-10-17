"""Product-level tests: scaffold -> execute -> replay -> policy gate."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import tev
from teview_gate import gate, GateError, load_policy
from teview_starter import create_starter


class ProductTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root/'example'
        create_starter(self.project)
        self.proto=self.project/'experiment.tev'
        self.policy=self.project/'gate.toml'
        self.base=self.root/'base'
        tev.run(self.proto, self.base, allow_python=True)

    def candidate(self, update=None):
        if update:
            p=self.project/'model.py'
            s=p.read_text(); self.assertIn(update[0],s)
            p.write_text(s.replace(*update),encoding='utf-8')
        name=self.root/('candidate-'+str(len(list(self.root.glob('candidate-*')))))
        tev.run(self.proto, name, allow_python=True)
        return name

    def test_scaffold_is_a_replayable_experiment(self):
        self.assertEqual(len(tev.plan(self.proto)['steps']),1)
        self.assertEqual(len(tev.verify(self.base,allow_python=True)['protocol_sha256']),64)

    def test_scaffold_refuses_existing_target(self):
        with self.assertRaises(ValueError):create_starter(self.project)
        self.assertTrue(self.proto.exists())

    def test_unchanged_candidate_passes(self):
        result=gate(self.base,self.candidate(),self.policy)
        self.assertEqual(result['status'],'pass')
        self.assertTrue(all(c['status']=='pass' for c in result['checks']))

    def test_worse_accuracy_fails(self):
        other=self.candidate(('round(target, 3)','round(target, 1)'))
        result=gate(self.base,other,self.policy)
        self.assertEqual(result['status'],'fail')
        self.assertEqual(result['checks'][0]['status'],'fail')
        self.assertTrue(result['checks'][1]['status']=='pass')

    def test_operation_regression_fails(self):
        other=self.candidate(('operations = 5 * size','operations = 9 * size'))
        result=gate(self.base,other,self.policy)
        self.assertEqual(result['status'],'fail')
        self.assertEqual(result['checks'][1]['status'],'fail')

    def test_cli_exit_codes_and_json_report(self):
        other=self.candidate(('operations = 5 * size','operations = 9 * size'))
        report=self.root/'gate-result.json'
        result=subprocess.run([sys.executable,str(ROOT/'tev.py'),'gate',str(self.base),str(other),
                               '--policy',str(self.policy),'--json-out',str(report)],capture_output=True,text=True)
        self.assertEqual(result.returncode,2,result.stderr)
        self.assertEqual(json.loads(report.read_text())['status'],'fail')
        good=subprocess.run([sys.executable,str(ROOT/'tev.py'),'gate',str(self.base),str(self.base),
                             '--policy',str(self.policy)],capture_output=True,text=True)
        self.assertEqual(good.returncode,0,good.stderr)

    def test_changed_protocol_rejected_by_default(self):
        src=self.proto.read_text()
        self.proto.write_text(src.replace('size = 100','size = 200'))
        other=self.candidate()
        with self.assertRaisesRegex(GateError,'Protocol definitions differ'):
            gate(self.base,other,self.policy)
        self.assertTrue(gate(self.base,other,self.policy,allow_protocol_change=True)['checks'])

    def test_changed_data_rejected_by_default(self):
        candidate=self.candidate()
        p=candidate/'report.json'; data=json.loads(p.read_text());data['inputs_sha256']={'fake':'changed'}
        p.write_text(json.dumps(data))
        with self.assertRaisesRegex(GateError,'Declared dataset contents differ'):
            gate(self.base,candidate,self.policy)

    def test_changed_design_rejected_even_with_overrides(self):
        candidate=self.candidate()
        p=candidate/'report.json'; data=json.loads(p.read_text());data['design']['seed']=999
        p.write_text(json.dumps(data))
        with self.assertRaisesRegex(GateError,'designs differ'):
            gate(self.base,candidate,self.policy,True,True)

    def test_policy_rejects_unknown_key(self):
        self.policy.write_text(self.policy.read_text()+'\nstrange = true\n')
        with self.assertRaises(GateError):load_policy(self.policy)

    def test_policy_rejects_negative_budgets(self):
        self.policy.write_text(self.policy.read_text().replace('0.001','-10'))
        with self.assertRaises(GateError):load_policy(self.policy)

    def test_worst_and_p95_measures(self):
        source=self.policy.read_text()
        self.policy.write_text(source.replace('metric = "error"','metric = "error"\nstatistic = "worst"'))
        other=self.candidate(('round(target, 3)','round(target, 1)'))
        self.assertEqual(gate(self.base,other,self.policy)['status'],'fail')
        self.policy.write_text(source.replace('metric = "error"','metric = "error"\nstatistic = "p95"'))
        self.assertEqual(gate(self.base,other,self.policy)['status'],'fail')

    def test_missing_metric_fails_closed(self):
        self.policy.write_text(self.policy.read_text().replace('metric = "error"','metric = "does_not_exist"'))
        with self.assertRaisesRegex(GateError,'Invalid or missing'):
            gate(self.base,self.base,self.policy)

    def test_tampered_verdict_caught_by_replay(self):
        p=self.base/'report.json'; report=json.loads(p.read_text());report['verdict']='claims_supported_exploratory'
        p.write_text(json.dumps(report))
        with self.assertRaisesRegex(tev.ExperimentError,'verdict was modified'):
            tev.verify(self.base,allow_python=True)

    def test_tampered_design_caught_by_replay(self):
        p=self.base/'report.json'; report=json.loads(p.read_text());report['design']['seed']=1
        p.write_text(json.dumps(report))
        with self.assertRaisesRegex(tev.ExperimentError,'design was modified'):
            tev.verify(self.base,allow_python=True)

if __name__=='__main__':unittest.main()

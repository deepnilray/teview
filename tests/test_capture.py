"""End-to-end tests for integrating existing commands with TEVIEW."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import tev
from teview_capture import capture, verify_capture
from teview_gate import gate, GateError


PROGRAM='''import json
import os
from pathlib import Path
xs=[int(i) for i in Path("data/numbers.txt").read_text().split()]
penalty=int(os.getenv("TEVIEW_SEED", "0"))
Path("metrics.json").write_text(json.dumps({"result":sum(xs)+penalty,"count":len(xs)}))
Path("artifact.txt").write_text(str(sum(xs)))
print("experiment complete")
'''

class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.work=self.root/'src';(self.work/'data').mkdir(parents=True)
        (self.work/'experiment.py').write_text(PROGRAM,encoding='utf8')
        (self.work/'data/numbers.txt').write_text('2 3 5',encoding='utf8')
        self.one=self.root/'run1'

    def run_capture(self, dest=None, **opts):
        return capture(self.work, dest or self.one,
                       code=['experiment.py'], data=['data/numbers.txt'],
                       command=[sys.executable,'experiment.py'],
                       artifacts=['artifact.txt'],seed=13,**opts)

    def test_capture_verify_and_compare(self):
        result=self.run_capture()
        self.assertEqual(result['metrics']['result'],23)
        self.assertTrue(tev.verify(self.one)['verified_replay'])
        self.assertIn('experiment complete',(self.one/'stdout.txt').read_text())
        second=self.root/'two';self.run_capture(second)
        comparison=tev.compare(self.one,second)
        self.assertEqual(comparison['metric_means']['default.result']['difference'],0)

    def test_capture_does_not_edit_user_workspace(self):
        self.run_capture()
        self.assertFalse((self.work/'metrics.json').exists())
        self.assertFalse((self.work/'artifact.txt').exists())
        self.assertEqual((self.work/'experiment.py').read_text(),PROGRAM)

    def test_code_snapshot_allows_new_version_and_gate(self):
        self.run_capture()
        before=(self.one/'report.json')
        src=self.work/'experiment.py'
        src.write_text(PROGRAM.replace('sum(xs)+penalty','sum(xs)+penalty-10'))
        second=self.root/'run2';self.run_capture(second)
        self.assertNotEqual(json.loads(before.read_text())['plugins_sha256'],
                            json.loads((second/'report.json').read_text())['plugins_sha256'])
        policy=self.root/'gate.toml'
        policy.write_text('''schema=1
[[checks]]
id="result"
arm="default"
metric="result"
direction="increase"
max_absolute_regression=0
''')
        assessed=gate(self.one,second,policy)
        self.assertEqual(assessed['status'],'fail')
        self.assertTrue(verify_capture(second)['verified_replay'])

    def test_data_mismatch_rejected_by_gate(self):
        self.run_capture()
        (self.work/'data/numbers.txt').write_text('7 8 9')
        second=self.root/'run2';self.run_capture(second)
        policy=self.root/'gate.toml'
        policy.write_text('''schema=1
[[checks]]
id="result"
arm="default"
metric="result"
direction="increase"
''')
        with self.assertRaisesRegex(GateError,'Declared dataset contents differ'):
            gate(self.one,second,policy)

    def test_detects_tampered_inputs_or_outputs(self):
        self.run_capture()
        (self.one/'source/experiment.py').write_text('print(1)')
        with self.assertRaisesRegex(tev.ExperimentError,'source snapshots changed'):
            verify_capture(self.one)

    def test_detects_tampered_metric(self):
        self.run_capture()
        report=self.one/'report.json'
        d=json.loads(report.read_text());d['observations'][0]['metrics']['result']=999
        report.write_text(json.dumps(d))
        with self.assertRaisesRegex(tev.ExperimentError,'measurement replay differs'):
            verify_capture(self.one)

    def test_disallows_path_escape_and_existing_output(self):
        for value in ('../escape.py','/tmp/file.py','C:\\Windows\\file.py'):
            with self.subTest(value=value):
                with self.assertRaises(tev.ExperimentError):
                    capture(self.work,self.one,code=[value],data=[],
                            command=['python','experiment.py'])
        self.run_capture()
        with self.assertRaisesRegex(tev.ExperimentError,'output exists'):
            self.run_capture()

    def test_missing_metrics_and_script_failure_leave_no_output(self):
        (self.work/'experiment.py').write_text('print("nothing")')
        with self.assertRaisesRegex(tev.ExperimentError,'did not produce'):
            self.run_capture()
        self.assertFalse(self.one.exists())
        (self.work/'experiment.py').write_text('raise RuntimeError("broken")')
        with self.assertRaisesRegex(tev.ExperimentError,'command exited'):
            self.run_capture()
        self.assertFalse(self.one.exists())

    def test_cli_capture_verify(self):
        args=[sys.executable,str(ROOT/'tev.py'),'capture','--root',str(self.work),
              '--out',str(self.one),'--code','experiment.py','--data','data/numbers.txt',
              '--seed','13','--artifact','artifact.txt','--',sys.executable,'experiment.py']
        result=subprocess.run(args,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(json.loads(result.stdout)['metrics'])
        check=subprocess.run([sys.executable,str(ROOT/'tev.py'),'verify',str(self.one)],capture_output=True,text=True)
        self.assertEqual(check.returncode,0,check.stderr)

    def test_verify_evidence_gate_rejects_tampered_record(self):
        self.run_capture()
        policy = self.root / 'gate.toml'
        policy.write_text('schema=1\n[[checks]]\nid="result"\narm="default"\nmetric="result"\ndirection="increase"\n')
        report = self.one/'report.json'
        data=json.loads(report.read_text())
        data['observations'][0]['metrics']['result'] += 3
        report.write_text(json.dumps(data))
        args = [sys.executable,str(ROOT/'tev.py'),'gate',str(self.one),str(self.one),
                '--policy',str(policy),'--verify-evidence']
        result=subprocess.run(args,capture_output=True,text=True)
        self.assertEqual(result.returncode,1)
        self.assertIn('measurement replay differs',result.stderr)

    def test_gate_checks_metric_units(self):
        self.run_capture()
        second=self.root/'second';self.run_capture(second)
        d=json.loads((second/'report.json').read_text())
        d['metric_units']['result']='meters'
        (second/'report.json').write_text(json.dumps(d))
        policy=self.root/'gate.toml'
        policy.write_text('schema=1\n[[checks]]\nid="result"\narm="default"\nmetric="result"\ndirection="increase"\n')
        with self.assertRaisesRegex(GateError,'Metric units differ'):
            gate(self.one,second,policy)

    def test_metrics_nonfinite_rejected(self):
        (self.work/'experiment.py').write_text('from pathlib import Path\nPath("metrics.json").write_text("{\\"loss\\": NaN}")\n')
        with self.assertRaisesRegex(tev.ExperimentError,'finite'):
            self.run_capture()


if __name__=='__main__':unittest.main()

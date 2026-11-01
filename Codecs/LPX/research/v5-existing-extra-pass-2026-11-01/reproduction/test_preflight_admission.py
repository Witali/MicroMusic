"""Strict admission contracts, with no production code or numerical helper."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from admit_preflight import Inputs,SOURCE_COMMIT,sha,verify_preflight


class Admission(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name);self.manifest=self.root/'prepared.json';self.manifest.write_bytes(b'{"prepared":true}')
        self.expected=dict(source_commit=SOURCE_COMMIT,source_root=str(self.root/'production'),
            production_sources={'source':'bound'},research_sources={'producer':'bound'},runtime={'python':'same'},
            native_bridge={'library':'bound'},source_context='exact-context')
        proof=copy.deepcopy(self.expected)
        proof.update(arm=None,assigned_jobs=[],baselines_path=str(self.manifest.resolve()),
            input_files_sha256={str(self.manifest.resolve()):sha(self.manifest.read_bytes())})
        self.documents={
            'binding-private.json':proof,
            'summary.json':dict(status='PASS',preflight_only=True,arm=None,arm_records=0,corpus_helper_calls=0,
                actual_cap_views=0,synthetic_helper_calls=6,initial_fits=0,native_builds=0,target_jobs=0),
            'attempt-private.json':dict(status='complete',helper_calls=[],records=[],forbidden_fit_or_build_attempts=0,
                synthetic_calls=[dict(status='complete') for _ in range(6)]),
            'synthetic-private.json':dict(status='PASS',helper_calls=6,calls=[{} for _ in range(6)]),
            'results-private.json':[]}

    def check(self):
        for name,value in self.documents.items():(self.root/name).write_text(json.dumps(value))
        return verify_preflight(self.root,self.manifest,Inputs(),self.expected)

    def test_complete_identical_context_passes(self):
        result=self.check();self.assertTrue(result['exact_production_native_research_runtime'])
        self.assertEqual(result['prepared_manifest_sha256'],sha(self.manifest.read_bytes()))

    def test_wrong_recorded_runtime_is_rejected(self):
        self.documents['binding-private.json']['runtime']['python']='different'
        with self.assertRaisesRegex(ValueError,'runtime'):self.check()

    def test_different_prepared_path_is_rejected_even_for_identical_bytes(self):
        other=self.root/'other.json';other.write_bytes(self.manifest.read_bytes())
        self.documents['binding-private.json']['baselines_path']=str(other.resolve())
        with self.assertRaisesRegex(ValueError,'path'):self.check()

    def test_missing_or_wrong_manifest_digest_is_rejected(self):
        for pins in ({},{str(self.manifest.resolve()):'wrong'}):
            with self.subTest(pins=bool(pins)):
                self.documents['binding-private.json']['input_files_sha256']=pins
                with self.assertRaisesRegex(ValueError,'digest'):self.check()

    def test_incomplete_or_real_work_cannot_masquerade_as_preflight(self):
        original=copy.deepcopy(self.documents)
        mutations=(('summary.json','preflight_only',False),('summary.json','corpus_helper_calls',1),
            ('attempt-private.json','status','started'),('attempt-private.json','helper_calls',[{}]),
            ('attempt-private.json','synthetic_calls',[dict(status='complete')]*5+[dict(status='started')]),
            ('results-private.json',None,[{}]))
        for name,key,value in mutations:
            with self.subTest(file=name,field=key):
                self.documents=copy.deepcopy(original)
                if key is None:self.documents[name]=value
                else:self.documents[name][key]=value
                with self.assertRaises(ValueError):self.check()

    def test_all_source_and_native_fields_are_exact(self):
        original=copy.deepcopy(self.documents)
        for field in ('source_commit','source_root','production_sources','research_sources','native_bridge','source_context'):
            with self.subTest(field=field):
                self.documents=copy.deepcopy(original);self.documents['binding-private.json'][field]='different'
                with self.assertRaises(ValueError):self.check()

    def test_entry_import_alone_does_not_load_production_modules(self):
        script=('import sys; import admit_preflight; '
            'assert not any(getattr(m,"__file__",None) and "/01_ACTIVE_Q0_CODEC/tools/" in '
            'str(m.__file__).replace(chr(92),"/") for m in list(sys.modules.values()))')
        subprocess.run([sys.executable,'-c',script],cwd=Path(__file__).parent,check=True,capture_output=True)


if __name__=='__main__':unittest.main()

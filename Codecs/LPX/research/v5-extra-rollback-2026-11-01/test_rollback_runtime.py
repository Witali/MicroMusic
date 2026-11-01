"""Passive source/operator/preflight contracts; no numerical or corpus calls."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from rollback_runtime import Inputs,SOURCE_COMMIT,function_span,sha,verify_preflight


class Runtime(unittest.TestCase):
    def test_operator_ast_ignores_comments_but_never_a_changed_trial_expression(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'operator.py'
            path.write_text('@njit(cache=True)\ndef refit_extra_group(a):\n    return a+1\n')
            original=function_span(path,'refit_extra_group')
            path.write_text('@njit(cache=True)\ndef refit_extra_group(a):\n    # explanation\n    return a+1\n')
            commented=function_span(path,'refit_extra_group')
            self.assertEqual(original['ast_sha256'],commented['ast_sha256'])
            self.assertNotEqual(original['source_sha256'],commented['source_sha256'])
            path.write_text('def refit_extra_group(a):\n    return a+2\n')
            self.assertNotEqual(original['ast_sha256'],function_span(path,'refit_extra_group')['ast_sha256'])

    def test_runtime_import_does_not_bind_an_old_production_module(self):
        script=('import sys; import rollback_runtime; '
            'assert not any(getattr(m,"__file__",None) and "/01_ACTIVE_Q0_CODEC/tools/" in '
            'str(m.__file__).replace(chr(92),"/") for m in list(sys.modules.values()))')
        subprocess.run([sys.executable,'-c',script],cwd=Path(__file__).parent,check=True,capture_output=True)

    def test_preflight_requires_exact_runtime_and_prepared_path_digest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);manifest=root/'prepared.json';manifest.write_bytes(b'{}')
            expected=dict(source_commit=SOURCE_COMMIT,source_root=str(root/'production'),production_sources={},
                research_sources={},runtime={'python':'same'},native_bridge={},source_context='same')
            proof=dict(copy.deepcopy(expected),mode='preflight',assigned_jobs=[],baselines_path=str(manifest.resolve()),
                input_files_sha256={str(manifest.resolve()):sha(manifest.read_bytes())})
            documents={'binding-private.json':proof,
                'summary.json':dict(status='PASS',mode='preflight',real_arm_records=0,real_pass_instances=0,real_stage_events=0,real_cap_views=0,
                    synthetic_arm_records=6,synthetic_pass_instances=8,synthetic_stage_events=24,synthetic_cap_views=18,
                    initial_fits=0,native_builds=0,target_jobs=0),
                'attempt-private.json':dict(status='complete',real_instances=[],synthetic_instances=[dict(status='complete') for _ in range(8)],
                    forbidden_fit_or_build_attempts=0,records=[dict(phase='synthetic',status='complete') for _ in range(6)]),
                'synthetic-results-private.json':[{} for _ in range(6)],'results-private.json':[]}
            def check(docs):
                hashes={}
                for name,value in docs.items():
                    path=root/name;path.write_text(json.dumps(value));hashes[name]=sha(path.read_bytes())
                (root/'complete-private.json').write_text(json.dumps(dict(status='complete',output_sha256=hashes)))
                return verify_preflight(root,manifest,Inputs(),expected)
            self.assertEqual(check(documents)['status'],'PASS')
            for field in ('runtime','production_sources','research_sources','native_bridge','source_context'):
                changed=copy.deepcopy(documents);changed['binding-private.json'][field]={'different':True}
                with self.assertRaises(ValueError):check(changed)
            changed=copy.deepcopy(documents);changed['binding-private.json']['baselines_path']=str(root/'other.json')
            with self.assertRaisesRegex(ValueError,'path'):check(changed)
            changed=copy.deepcopy(documents);changed['binding-private.json']['input_files_sha256']={}
            with self.assertRaisesRegex(ValueError,'digest'):check(changed)
            changed=copy.deepcopy(documents);changed['attempt-private.json']['status']='started'
            with self.assertRaises(ValueError):check(changed)
            check(documents);(root/'summary.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'marker'):verify_preflight(root,manifest,Inputs(),expected)


if __name__=='__main__':unittest.main()

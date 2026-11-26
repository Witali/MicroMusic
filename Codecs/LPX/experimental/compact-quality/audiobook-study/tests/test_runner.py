"""Runner unit/artifact tests using generated silence, never audiobook encodes."""
from __future__ import annotations
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import study as s
import runner as r


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.smoke=s.ROOT/'build/audiobook-training/synthetic-smoke'
        self.report=s.read(self.smoke/'encode.json')

    def test_independent_long_artifacts_and_malformed_packets(self):
        artifacts,waveform=s.check_artifacts(self.report,self.smoke/'zero.source.pcm',self.smoke/'zero')
        self.assertEqual(len(artifacts),9)
        self.assertTrue(all(x['pcm_sse']==0 for x in waveform.values()))
        blob=(self.smoke/'zero-baseline.lpx').read_bytes()
        for data in (blob[:-1],blob+b'\0',b'X'+blob[1:],blob[:5]+(159999).to_bytes(4,'little')+blob[9:]):
            with self.assertRaises(ValueError):s.packet(data)
        changed=deepcopy(self.report);changed['selected_output']['quality']['pwm_sse']+=1
        with self.assertRaises(ValueError):s.check_artifacts(changed,self.smoke/'zero.source.pcm',self.smoke/'zero')
        s.check_verification(s.read(self.smoke/'verify.json'),self.report)

    def test_whitelist_and_nonshrinking_stoi_denominator(self):
        contaminated=deepcopy(self.report);contaminated['private_path']='PRIVATE_CANARY'
        contaminated['baseline']['private_recording_hash']='PRIVATE_CANARY'
        self.assertNotIn('PRIVATE_CANARY',json.dumps(s.public_report(contaminated)))
        report=deepcopy(self.report)
        for label in s.LABELS:report[label]['quality']['stoi']=[0.5,0.6]
        row=dict(status='PASS',report=report,stoi_eligible=[True,True],
            waveform={k:dict(reference_energy=100,pcm_sse=10,pwm_sse=20) for k in s.LABELS},
            subprocess_wall_seconds=1,verification_wall_seconds=1)
        result=s.aggregate([row],2);self.assertFalse(result['complete'])
        self.assertIsNone(result['outputs']['baseline']['paths'][0]['mean_stoi'])
        report['raw_candidate']['quality']['stoi'][0]=None
        result=s.aggregate([row],1)
        self.assertEqual(result['outputs']['raw_candidate']['paths'][0]['baseline_eligible_stoi_cases'],1)
        self.assertEqual(result['outputs']['raw_candidate']['paths'][0]['missing_eligible_stoi_cases'],1)
        self.assertIsNone(result['outputs']['raw_candidate']['paths'][0]['mean_stoi'])

    def test_phase_locks_and_development_only_pilot(self):
        with tempfile.TemporaryDirectory(dir=s.ROOT/'build') as tmp:
            folder=Path(tmp);freeze=dict(max_workers=2,first_development_ordinal=1,cases=[
                dict(ordinal=0,split='heldout'),dict(ordinal=1,split='development')])
            args=SimpleNamespace(output=folder,workers=1,phase='development',pilot_audit=None,
                policy_freeze=None,public=folder/'public.json')
            with patch.object(r,'load',return_value=(folder,freeze,{})),patch.object(r,'run_case') as child:
                with self.assertRaises(ValueError):r.phase_run(args)
                args.phase='heldout'
                with self.assertRaises(ValueError):r.phase_run(args)
                child.assert_not_called()
            args.phase='pilot'
            with patch.object(r,'load',return_value=(folder,freeze,{})),patch.object(r,'run_case',return_value=dict(status='PASS')) as child,patch.object(r,'export',return_value=dict(aggregate=dict(complete=True))):
                r.phase_run(args)
                self.assertEqual(child.call_args.args[3]['ordinal'],1)
            r.case_folder(folder,1).mkdir();(r.case_folder(folder,1)/'attempt-private.json').write_text('{}')
            with patch.object(r,'load',return_value=(folder,freeze,{})),patch.object(r,'run_case') as child:
                with self.assertRaises(ValueError):r.phase_run(args)
                child.assert_not_called()

    def test_private_path_and_immutable_record(self):
        with self.assertRaises(ValueError):s.private(s.ROOT/'Codecs')
        with tempfile.TemporaryDirectory(dir=s.ROOT/'build') as tmp:
            path=Path(tmp)/'lock.json';s.write(path,dict(a=1),immutable=True)
            s.write(path,dict(a=1),immutable=True)
            with self.assertRaises(ValueError):s.write(path,dict(a=2),immutable=True)
            self.assertEqual(s.read(path),dict(a=1))


if __name__=='__main__':unittest.main()

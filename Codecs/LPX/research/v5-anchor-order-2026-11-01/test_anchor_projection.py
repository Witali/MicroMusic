"""Saved-only branch and pair projection contracts."""
import unittest
import subprocess
import sys
import os
import json
from pathlib import Path
from project_anchor import branch_work,outcome,rejected,COMPARISONS,audit_job_settings


class Projection(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('ANCHOR_STUDY'),'Private terminal study is opt-in')
    def test_all_terminal_jobs_match_the_separate_manifest_schema(self):
        root=Path(os.environ['ANCHOR_STUDY'])
        manifest=json.loads((root/'baselines-v1/binding-private.json').read_text())
        rows=[]
        for profile in (4,6):rows.extend(json.loads((root/('pilot-v1-p%d'%profile)/'results-private.json').read_text()))
        self.assertEqual(len(rows),48)
        for row in rows:audit_job_settings(row,manifest)

    def test_clean_interpreter_bootstrap_has_no_codec_preload(self):
        package=Path(__file__).resolve().parent
        code='import sys;sys.path.insert(0,sys.argv[1]);import project_anchor;assert "speech_compact" not in sys.modules'
        result=subprocess.run([sys.executable,'-c',code,str(package)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,'Standalone saved-only projector bootstrap failed')

    def test_branch_starts_are_not_completed_work(self):
        r=dict(planned_anchors=[4,0,1],started_anchors=[4],completed_anchors=[],
            repeat_spectrum_proposals=1,completed_rate_allocation_calls=0,rate_allocation_calls_started=1,
            refit_calls_started=2,refit_calls_completed=2,refit_candidates_completed=1,joint_candidates_completed=3)
        result=branch_work([r])
        self.assertEqual(result['helpers_first_nonzero_anchor'],1)
        self.assertEqual(result['started_anchors'],1);self.assertEqual(result['completed_anchors'],0)
        self.assertEqual(result['refit_calls_completed'],2);self.assertEqual(result['refit_candidates_completed'],1)
        self.assertEqual(result['rate_allocation_calls_started'],1);self.assertEqual(result['completed_rate_allocation_calls'],0)

    def test_no_started_anchor_is_honestly_counted(self):
        r=dict(planned_anchors=[0],started_anchors=[],completed_anchors=[],repeat_spectrum_proposals=0,
            completed_rate_allocation_calls=0)
        self.assertEqual(branch_work([r])['helpers_without_started_anchor'],1)

    def test_fixed_primary_pairs(self):
        self.assertEqual(COMPARISONS[:2],(('old-order','T-time-0','T-priority-0'),('new-order','G-time-0','G-priority-0')))
        self.assertEqual(len(COMPARISONS),4)

    def test_fit_and_score_byte_ties_stay_distinct(self):
        self.assertEqual(outcome(None,None),'neither-admitted')
        self.assertEqual(outcome(dict(score=1.,stream_bytes=99),dict(score=1.,stream_bytes=100)),'left-smaller-score-tie')


if __name__=='__main__':unittest.main()

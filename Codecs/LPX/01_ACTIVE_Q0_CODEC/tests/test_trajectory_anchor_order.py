"""Fixed nomination, useful visitation, and honest interrupted-call counters."""
import unittest
from unittest.mock import patch

import numpy as np

from batch_decoder import BatchSession
import refine_speech_trajectory as trajectory
from search_cpu_budget import CpuBudgetExceeded
import speech_compact as compact
from speech_rate_allocation import bit_accounting
from standard_metrics import pwm_duties
from test_refine_speech_trajectory import seed, altered


class AnchorOrderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session = BatchSession('batch', speech=True, speech_compact=True, compact_only=True)
        cls.decoder = cls.session.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.session.__exit__()

    def test_late_useful_anchor_wins_with_the_same_render_limit(self):
        for profile in (4, 6):
            blob = seed(profile, 960)
            target = altered(blob, [2])
            reference = compact.decode_model(target)
            def objective(pcm):
                return 0 if np.array_equal(pcm, reference) else 10
            results = {}
            for order in ('time', 'priority'):
                seen = []
                chosen, pcm, report, _ = trajectory.refine(reference, blob, self.decoder, len(blob)+8,
                    frame_limit=2, window_frames=2, beam_width=1, spectral_candidates=1,
                    excitation_candidates=0, max_evaluations=45, screening='full', speech=False,
                    selection='objective', objective=objective, anchor_order=order,
                    candidate_sink=lambda stream, score: seen.append(stream))
                results[order] = chosen, report
                self.assertEqual(report['nominated_anchors'], [0, 2])
                self.assertEqual(report['full_synthesis_evaluations'], 45)
                self.assertTrue(report['search_limit_reached'])
                self.assertEqual(len(set(report['started_anchors'])), len(report['started_anchors']))
                self.assertIn(chosen, seen)
            self.assertNotEqual(results['time'][0], target)
            self.assertEqual(results['priority'][0], target)
            self.assertEqual(results['time'][1]['planned_anchors'], [0, 2])
            self.assertEqual(results['priority'][1]['planned_anchors'], [2, 0])
            np.testing.assert_array_equal(compact.decode_model(target)[:640], compact.decode_model(blob)[:640])
            with BatchSession('batch', speech=True, speech_compact=True) as common:
                np.testing.assert_array_equal(common.decode_one_s16(target, 960), reference)
                np.testing.assert_array_equal(common.decode_one(target, 960), pwm_duties(reference))

    def test_rate_priority_takes_next_unseen_from_each_queue(self):
        parts = list(compact.unpack(seed(6, 1600)))
        parts[2][1][3] += 1
        parts[2][1][6] += 1
        parts[2][3][4] += 1
        fields = trajectory.Fields(*(np.asarray(x, np.int64) for x in (parts[2],parts[3],parts[4],parts[7])))
        reference, pcm = np.zeros(1600, np.int64), np.zeros(1600, np.int64)
        reference[1280:] = 3
        reference[320:640] = 2
        reference[640:960] = 1
        savings = trajectory._repeat_savings(fields, 6)
        self.assertEqual(sorted(savings,key=lambda f:(-savings[f],f)),[1,3,2,4])
        self.assertGreater(savings[1], savings[3])
        for frame, bits in savings.items():
            repeated = fields.copy()
            repeated.spectra[frame] = repeated.spectra[frame-1].copy()
            self.assertEqual(bits, bit_accounting(fields.spectra,6,fields.extras)['spectrum_bits']-
                bit_accounting(repeated.spectra,6,repeated.extras)['spectrum_bits'])
        anchors = list(range(5))
        self.assertEqual(trajectory.priority_frame_order(reference,pcm,anchors,fields,6,False),[4,1,2,0,3])
        self.assertEqual(trajectory.priority_frame_order(reference,pcm,anchors,fields,6,True),[1,4,3,2,0])
        self.assertEqual(anchors,list(range(5)))
        # Equal errors and absent savings use deterministic frame order.
        fields.spectra[:] = fields.spectra[0]
        self.assertEqual(trajectory.priority_frame_order(pcm,pcm,[4,2,0],fields,6,True),[0,2,4])
        reference[:320]=0
        reference[320:640]=1
        reference[640:960]=2
        reference[960:1280]=3
        with patch.object(trajectory,'_repeat_savings',return_value={3:2,1:1}):
            self.assertEqual(trajectory.priority_frame_order(reference,pcm,[0,1,2,3],fields,6,True),[3,2,1,0])
            self.assertEqual(trajectory.priority_frame_order(reference,pcm,[],fields,6,True),[])
            self.assertEqual(trajectory.priority_frame_order(reference,pcm,[1],fields,6,True),[1])

    def test_new_generation_keeps_the_same_nominated_set(self):
        blob=seed(6,960)
        reference=compact.decode_model(altered(blob,[2]))
        reports=[]
        for order in ('time','priority'):
            report=trajectory.refine(reference,blob,self.decoder,len(blob)+8,rate_search=True,
                frame_limit=2,spectral_candidates=1,excitation_candidates=0,max_evaluations=24,
                allocation_evaluations=8,speech=False,anchor_order=order)[2]
            reports.append(report)
            self.assertEqual(sorted(report['planned_anchors']),report['nominated_anchors'])
            self.assertLessEqual(report['completed_rate_allocation_calls'],report['rate_allocation_calls_started'])
        self.assertEqual(reports[0]['nominated_anchors'],reports[1]['nominated_anchors'])

    def test_refit_interruption_retains_prior_complete_candidates(self):
        blob=seed(4,641)
        reference=compact.decode_model(altered(blob,[0]))
        seen=[]
        with patch.object(trajectory,'adapt_excitation',side_effect=CpuBudgetExceeded):
            chosen,pcm,report,_=trajectory.refine(reference,blob,self.decoder,len(blob)+8,
                frame_limit=1,spectral_candidates=0,excitation_candidates=1,max_evaluations=64,
                speech=False,candidate_sink=lambda stream,score:seen.append(stream),anchor_order='priority')
        self.assertEqual(report['refit_calls_started'],1)
        self.assertEqual(report['refit_calls_completed'],0)
        self.assertEqual(report['started_anchors'],[0])
        self.assertEqual(report['completed_anchors'],[])
        self.assertGreater(report['joint_candidates_completed'],0)
        self.assertIn(chosen,seen)
        np.testing.assert_array_equal(pcm,compact.decode_model(chosen))

    def test_allocator_interruption_counts_started_not_completed(self):
        import speech_rate_allocation as allocation
        blob=seed(6,321)
        reference=compact.decode_model(blob)
        real=allocation.allocation_frontier
        def interrupted(*args,**kwargs):
            real(*args,**kwargs)
            raise CpuBudgetExceeded
        with patch.object(allocation,'allocation_frontier',side_effect=interrupted):
            report=trajectory.refine(reference,blob,self.decoder,len(blob),rate_search=True,
                frame_limit=1,spectral_candidates=0,excitation_candidates=0,
                allocation_evaluations=8,max_evaluations=16,speech=False)[2]
        self.assertEqual(report['rate_allocation_calls_started'],1)
        self.assertEqual(report['completed_rate_allocation_calls'],0)
        self.assertGreater(report['rate_allocation_points'],0)

    def test_completed_refit_is_distinct_from_an_interrupted_candidate(self):
        blob=seed(6,641)
        reference=compact.decode_model(altered(blob,[0]))
        candidate=trajectory.Search.candidate
        def interrupted(search,parent,fields,coefficients,move):
            if move[0]=='refit':
                raise CpuBudgetExceeded
            return candidate(search,parent,fields,coefficients,move)
        with patch.object(trajectory.Search,'candidate',new=interrupted):
            report=trajectory.refine(reference,blob,self.decoder,len(blob)+8,
                frame_limit=1,spectral_candidates=0,excitation_candidates=1,
                max_evaluations=64,speech=False,anchor_order='priority')[2]
        self.assertEqual(report['refit_calls_started'],1)
        self.assertEqual(report['refit_calls_completed'],1)
        self.assertEqual(report['refit_candidates_completed'],0)
        self.assertEqual(report['completed_anchors'],[])

    def test_invalid_order_fails_before_decoding(self):
        blob=seed(4,321)
        for order in ('other',None,True,1):
            with self.assertRaisesRegex(ValueError,'anchor order'):
                trajectory.refine(compact.decode_model(blob),blob,None,len(blob),anchor_order=order)


if __name__=='__main__':unittest.main()

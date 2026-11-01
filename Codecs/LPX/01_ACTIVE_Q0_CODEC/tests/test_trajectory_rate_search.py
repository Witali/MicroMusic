"""Joint credit, exact prefix state, and completed endpoints on interruption."""
import unittest
from unittest.mock import patch

import numpy as np

from batch_decoder import BatchSession
import refine_speech_trajectory as trajectory
from search_cpu_budget import CpuBudgetExceeded
import speech_compact as compact
import speech_rate_allocation as allocation
from standard_metrics import pwm_duties
from test_refine_speech_trajectory import seed


class TrajectoryRateSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session=BatchSession('batch',speech=True,speech_compact=True,compact_only=True)
        cls.decoder=cls.session.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.session.__exit__()

    def test_repeat_and_new_extra_win_jointly_at_the_same_actual_cap(self):
        for profile in (4,6):
            parts=list(compact.unpack(seed(profile,641)))
            parts[2][1][3]+=1;parts[2][1][6]+=1
            # Avoid an unrelated equivalent cheaper file from unused tail extras.
            parts[7][16:]=[(-1,0)]*len(parts[7][16:])
            parts[7][8]=(-1,0)
            original=compact.pack(*parts[:7],extras=parts[7])[0]
            repeated=[row.copy() for row in parts[2]];repeated[1]=repeated[0].copy()
            added=list(parts[7]);added[8]=(0,2)
            repeat_only=compact.pack(parts[0],profile,repeated,*parts[3:7],extras=parts[7])[0]
            extra_only=compact.pack(*parts[:7],extras=added)[0]
            target=compact.pack(parts[0],profile,repeated,*parts[3:7],extras=added)[0]
            self.assertLessEqual(len(target),len(original))
            self.assertGreater(len(extra_only),len(original))
            waves=[(compact.decode_model(blob),score) for blob,score in
                   ((original,10),(repeat_only,11),(extra_only,11),(target,0))]
            reference=waves[-1][0]
            def objective(pcm):
                return next((score for wave,score in waves if np.array_equal(wave,pcm)),100)
            capacities=[]
            def refit(ref,co,pp,ii,ee,steps,pre,bright,p,start,end,horizon,h,dd,cc,ring,capacity):
                out=ee.copy();capacities.append(capacity)
                if capacity>np.count_nonzero(out[:,1]):out[8]=(0,2)
                return pp.copy(),ii.copy(),out,1
            options=dict(frame_limit=1,beam_width=1,spectral_candidates=1,excitation_candidates=1,
                max_evaluations=96,allocation_evaluations=32,objective=objective,
                selection='objective',speech=False)
            with patch.object(trajectory,'frame_order',return_value=[1]), \
                 patch.object(trajectory,'rate_frame_order',return_value=[1]), \
                 patch.object(trajectory,'adapt_excitation',side_effect=refit):
                chosen,pcm,report,_=trajectory.refine(reference,original,self.decoder,len(original),
                    rate_search=True,**options)
                old=trajectory.refine(reference,original,self.decoder,len(original),**options)[0]
            self.assertEqual(chosen,target)
            self.assertNotEqual(old,target)
            self.assertGreater(report['repeat_spectrum_proposals'],0)
            self.assertEqual(report['screening'],'full')
            self.assertIn('repeat-spectrum',repr(report['checkpoints']))
            self.assertIn('refit',repr(report['checkpoints']))
            self.assertGreaterEqual(max(capacities),np.count_nonzero(np.asarray(added)[:,1]))
            np.testing.assert_array_equal(pcm,reference)
            np.testing.assert_array_equal(pcm[:320],waves[0][0][:320])
            with BatchSession('batch',speech=True,speech_compact=True) as common:
                np.testing.assert_array_equal(common.decode_one_s16(chosen,641),reference)
                np.testing.assert_array_equal(common.decode_one(chosen,641),pwm_duties(reference))

    def test_repeat_credit_includes_following_spectrum(self):
        parts=list(compact.unpack(seed(6,960)))
        parts[2][1][3]+=1;parts[2][1][6]+=1
        parts[2][2]=parts[2][1].copy()
        fields=trajectory.Fields(*(np.asarray(x,np.int64) for x in (parts[2],parts[3],parts[4],parts[7])))
        before=allocation.bit_accounting(fields.spectra,6,fields.extras)
        repeated=fields.copy();repeated.spectra[1]=repeated.spectra[0].copy()
        after=allocation.bit_accounting(repeated.spectra,6,repeated.extras)
        self.assertEqual(before['file_bytes'],after['file_bytes'])
        self.assertEqual(before['spectrum_bits'],after['spectrum_bits'])
        with patch.object(trajectory,'frame_order',return_value=[0,2]):
            self.assertEqual(trajectory.rate_frame_order(np.zeros(960,np.int16),
                np.zeros(960,np.int16),fields,6,2),[0,2])

    def test_completed_cheaper_endpoint_survives_allocator_interruption(self):
        parts=list(compact.unpack(seed(6,641)))
        parts[7]=[(-1,0)]*len(parts[7]);parts[7][-1]=(39,2)
        blob=compact.pack(*parts[:7],extras=parts[7])[0]
        reference=compact.decode_model(blob);seen=[]
        real=allocation.allocation_frontier
        def interrupted(*args,**kwargs):
            real(*args,**kwargs)
            raise CpuBudgetExceeded
        with patch.object(allocation,'allocation_frontier',side_effect=interrupted):
            result,pcm,report,_=trajectory.refine(reference,blob,self.decoder,len(blob),
                rate_search=True,frame_limit=1,spectral_candidates=0,excitation_candidates=0,
                max_evaluations=32,allocation_evaluations=16,speech=False,
                candidate_sink=lambda stream,score:seen.append(stream))
        self.assertIsNotNone(result)
        self.assertLess(len(result),len(blob))
        self.assertIn(result,seen)
        self.assertGreater(report['rate_allocation_points'],0)
        self.assertEqual(report['completed_rate_allocation_calls'],0)
        np.testing.assert_array_equal(pcm,reference)

    def test_rate_search_requires_boolean_and_default_has_no_rate_report(self):
        blob=seed(4,321);reference=compact.decode_model(blob)
        for value in (None,1,'yes'):
            with self.assertRaisesRegex(ValueError,'boolean'):
                trajectory.refine(reference,blob,self.decoder,len(blob),rate_search=value)
        result,pcm,report,_=trajectory.refine(reference,blob,self.decoder,len(blob),speech=False)
        self.assertEqual(result,blob)
        self.assertNotIn('rate_search',report)


if __name__=='__main__':unittest.main()

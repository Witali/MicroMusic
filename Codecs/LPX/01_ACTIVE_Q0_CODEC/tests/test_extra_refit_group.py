"""Optional phase ownership, native replay, and unplayed-tail tie behavior."""
import unittest

import numpy as np

from batch_decoder import BatchSession
from enhance_speech_compact import advance, sse
from q0_model import coefficient_trace, table
from refine_speech_extras import refit_extra_group
import speech_compact as compact
from standard_metrics import pwm_duties
from test_refine_speech_trajectory import seed, altered
from wav_lpc import pack_frames


def inputs(blob, start):
    n,profile,spectra,pp,ii,pre,bright,ee=compact.unpack(blob)
    shift=5 if profile==4 else 4
    vectors=[[(v<<shift)+(1<<(shift-1)) for v in row] for row in spectra for _ in range(2)]
    co=coefficient_trace(pack_frames(vectors[:(n+159)//160]),n)
    params,pulses,extras=(np.asarray(x,np.int64) for x in (pp,ii,ee))
    _,h,dd,cc,ring=advance(co,params,pulses,extras,table('scale_table.inc'),pre,bright,0,start,
        np.zeros(10,np.int64),0,0,np.zeros(256,np.int64))
    return n,profile,spectra,params,pulses,extras,pre,bright,co,h,dd,cc,ring


class ExtraGroupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.only=BatchSession('batch',speech=True,speech_compact=True,compact_only=True)
        cls.decoder=cls.only.__enter__()
        cls.common=BatchSession('batch',speech=True,speech_compact=True)
        cls.other=cls.common.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.common.__exit__();cls.only.__exit__()

    def test_group_restores_inputs_and_returned_cost_matches_integer_native_replay(self):
        for p in (4,6):
            blob=seed(p,641);reference=compact.decode_model(altered(blob,[0])).astype(np.int64)
            n,profile,spectra,pp,ii,ee,pre,bright,co,h,dd,cc,ring=inputs(blob,200)
            arrays=(pp,ii,ee,co,h,ring);before=[x.copy() for x in arrays]
            pos,amp,loss,count=refit_extra_group(reference,co,pp,ii,ee,table('scale_table.inc'),
                pre,bright,200,360,h,dd,cc,ring,int(np.count_nonzero(ee[:,1])),len(ee))
            for old,new in zip(before,arrays):np.testing.assert_array_equal(old,new)
            self.assertGreater(count,1);self.assertLessEqual(count,33)
            chosen=ee.copy();chosen[5]=(pos,amp)
            local=advance(co,pp,ii,chosen,table('scale_table.inc'),pre,bright,200,360,h,dd,cc,ring)[0]
            self.assertEqual(loss,int(sse(reference[200:360],local)))
            result=compact.pack(n,profile,spectra,pp,ii,pre,bright,extras=chosen.tolist())[0]
            self.assertLessEqual(len(result),len(blob))
            model=compact.decode_model(result)
            np.testing.assert_array_equal(model[:200],compact.decode_model(blob)[:200])
            np.testing.assert_array_equal(model[200:360],local)
            for decoder in (self.decoder,self.other):
                np.testing.assert_array_equal(decoder.decode_one_s16(result,n),model)
                np.testing.assert_array_equal(decoder.decode_one(result,n),pwm_duties(model))

    def test_zero_loss_keeps_unplayed_stored_extra_even_when_other_aliases_tie(self):
        for profile in (4,6):
            parts=list(compact.unpack(seed(profile,641)));parts[7][16]=(39,-8)
            blob=compact.pack(*parts[:7],extras=parts[7])[0]
            reference=compact.decode_model(blob).astype(np.int64)
            n,p,spectra,pp,ii,ee,pre,bright,co,h,dd,cc,ring=inputs(blob,640)
            before=ee.copy()
            pos,amp,loss,count=refit_extra_group(reference,co,pp,ii,ee,table('scale_table.inc'),
                pre,bright,640,641,h,dd,cc,ring,int(np.count_nonzero(ee[:,1])),len(ee))
            self.assertEqual((pos,amp,loss),(39,-8,0))
            self.assertGreater(count,1)
            np.testing.assert_array_equal(ee,before)


if __name__=='__main__':unittest.main()

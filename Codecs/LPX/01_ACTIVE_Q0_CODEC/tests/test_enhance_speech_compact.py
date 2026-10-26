import unittest
import numpy as np
from batch_decoder import BatchSession
from speech_v4 import pack
from speech_compact import components,pack as pack5,unpack,decode_model
from enhance_speech_compact import advance,enhance
from q0_model import coefficient_trace,table
from wav_lpc import pack_frames


def source(profile,n=640):
    packets=(n+319)//320
    spectra=[[2+3*i for i in range(10)] if profile==4 else [4+6*i for i in range(10)]]*packets
    return pack(n,profile,spectra,[(18,55,0)]*(packets*2),
                [(5,(8 if profile==4 else 7) if i&1 else -8) for i in range(packets*16)])


class EnhanceCompactSpeechTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session=BatchSession('batch',speech=True,speech_compact=True)
        cls.decoder=cls.session.__enter__()

    @classmethod
    def tearDownClass(cls):cls.session.__exit__()

    def test_snapshot_matches_model_including_collisions_and_partial_tail(self):
        for profile in (4,6):
            blob=source(profile,641);args=components(blob);n,p,spectra,params,pulses,pre,bright=args
            extras=[(5,7) if i%3==0 else (25,-8) if i%3==1 else (39,4) for i in range(len(spectra)*8)]
            packed,_=pack5(*args,extras=extras);shift=5 if p==4 else 4
            vectors=[[(v<<shift)+(1<<(shift-1)) for v in vec] for vec in spectra for _ in range(2)]
            co=coefficient_trace(pack_frames(vectors[:(n+159)//160]),n)
            actual,_,_,_,_=advance(co,np.asarray(params,np.int64),np.asarray(pulses,np.int64),
                np.asarray(extras,np.int64),table('scale_table.inc'),pre,bright,0,n,
                np.zeros(10,np.int64),0,0,np.zeros(256,np.int64))
            np.testing.assert_array_equal(actual,decode_model(packed))
            np.testing.assert_array_equal(actual,self.decoder.decode_one_s16(packed,n))

    def test_perfect_reference_retains_plain_exact_stream_and_cap(self):
        blob=source(4);base,_=pack5(*components(blob));ref=decode_model(base)
        result,pcm,report=enhance(ref,blob,self.decoder,len(base))
        self.assertEqual(result,base);self.assertEqual(report['extra_pulses'],0)
        np.testing.assert_array_equal(pcm,ref)
        with self.assertRaises(ValueError):enhance(ref,blob,self.decoder,len(base)-1)

    def test_known_innovation_improves_with_frozen_fields_and_whole_file_budget(self):
        blob=source(4);args=components(blob);extras=[(-1,0)]*16;extras[0]=(5,3);extras[4]=(12,-2)
        target,_=pack5(*args,extras=extras);ref=decode_model(target)
        marked,info=pack5(*args,force_extras=True);cap=len(marked)+3
        result,pcm,report=enhance(ref,blob,self.decoder,cap,position_candidates=4,
                                  batch_size=4,max_full_evaluations=32)
        self.assertLessEqual(len(result),cap);self.assertEqual(unpack(result)[:7],args)
        self.assertGreater(report['extra_pulses'],0)
        self.assertLess(report['selected']['error_energy'],report['baseline']['error_energy'])
        self.assertGreaterEqual(report['selected']['stoi'],report['baseline']['stoi']-1e-12)
        self.assertLessEqual(report['full_evaluations'],32)
        np.testing.assert_array_equal(pcm,decode_model(result))

    def test_invalid_search_settings_and_reference_count(self):
        blob=source(6);reference=decode_model(pack5(*components(blob))[0])
        for options in ({'horizon':80},{'position_candidates':0},{'max_full_evaluations':0},
                        {'batch_size':65},{'max_bytes':21}):
            kw={'max_bytes':80,**options}
            with self.assertRaises(ValueError):enhance(reference,blob,self.decoder,**kw)
        with self.assertRaises(ValueError):enhance(reference[:-1],blob,self.decoder,80)


if __name__=='__main__':unittest.main()

"""A target budget is independent of seed size and its unattainable quality."""
from pathlib import Path
import sys,unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from batch_decoder import BatchSession
from test_beam_excitation import raw_fixture
from budget_search import search_budget,spectrum_seeds
from lpx4 import decode


class BudgetSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.session=BatchSession('batch',v3_features=24);cls.decoder=cls.session.__enter__()
    @classmethod
    def tearDownClass(cls):cls.session.__exit__(None,None,None)

    def test_oversized_seed_reaches_cap_without_dropping_samples(self):
        seed=raw_fixture(samples=319);ref=np.zeros(319,np.int16)
        blob,pcm,r=search_budget([seed],ref,self.decoder,50,'music',lambdas=(0.,1.),refinement_trials=0)
        self.assertGreater(len(seed),50);self.assertTrue(r['started_above_budget']);self.assertEqual(r['status'],'ok')
        self.assertLessEqual(len(blob),50);self.assertEqual(len(decode(blob)[2]),319)
        np.testing.assert_array_equal(pcm,ref)

    def test_exhausted_search_reports_no_fit_and_feasible_seed_rolls_back(self):
        seed=raw_fixture(samples=160);ref=self.decoder.decode_one_s16(seed,160)
        out,pcm,r=search_budget([seed],ref,self.decoder,20,'music',lambdas=(1.,),refinement_trials=0)
        self.assertIsNone(out);self.assertIsNone(pcm);self.assertEqual(r['status'],'no_fit');self.assertGreater(r['minimum_observed_bytes'],20)
        out,pcm,r=search_budget([seed],ref,self.decoder,len(seed),'music',lambdas=(1.,),refinement_trials=0)
        self.assertLessEqual(len(out),len(seed));np.testing.assert_array_equal(pcm,ref)
        self.assertEqual(r['selected']['full_sse'],0)

    def test_nonmonotone_candidates_and_validation(self):
        seed=raw_fixture(samples=160);ref=np.zeros(160,np.int16)
        def oversize(seed,ref,decoder,lam,**kwargs):
            # Deliberately nonmonotone achieved sizes must not discard a valid
            # low-lambda candidate or assume all later points will fit.
            from rate_distortion import encode_rate
            b,p,r=encode_rate(seed,ref,decoder,lam=1.,allow_zero=True,compact_features=24,kind='music')
            return (b if lam==0 else seed), (p if lam==0 else decoder.decode_one_s16(seed,len(ref))), r
        out,pcm,r=search_budget([seed],ref,self.decoder,50,'music',lambdas=(0.,1.,3.),refinement_trials=0,encoder=oversize)
        self.assertEqual(r['status'],'ok');self.assertLessEqual(len(out),50)
        self.assertTrue(any(not c['fits_budget'] for c in r['candidates']))
        for opts in ({'max_bytes':19},{'lambdas':()},{'lambdas':(float('nan'),)},{'refinement_trials':17}):
            kw={'max_bytes':50,**opts}
            with self.assertRaises(ValueError):search_budget([seed],ref,self.decoder,kind='music',**kw)

    def test_spectrum_repeat_templates_preserve_length_and_audit_fixed_point(self):
        from lpx4 import encode
        from wav_lpc import pack_frames
        n=641;vectors=[[round(1023*i/11)+j for i in range(1,11)] for j in range(5)]
        raw=bytearray(raw_fixture(samples=n)[:20]);raw[:5]=b'L3AV\x01'
        blocks=[{'bits':3,'scale':150,'q':[0]*min(80,n-at)} for at in range(0,n,80)]
        seed=encode({'raw':bytes(raw),'frames':pack_frames(vectors),'blocks':blocks},fast=True)[0]
        variants,audit=spectrum_seeds(seed,(2,4));self.assertTrue(variants);self.assertTrue(audit)
        for b in variants:
            frames,_,q=decode(b);self.assertEqual(len(q),n)
            self.assertTrue(any(f==b'\x00' for f in frames))
            self.assertIsNotNone(self.decoder.decode_one_s16(b,n))
        self.assertTrue(all(a['unstable_subframes']==0 for a in audit if a['accepted']))
        with self.assertRaises(ValueError):spectrum_seeds(seed,(3,))

    def test_guard_does_not_accept_a_muted_file_just_because_it_fits(self):
        seed=raw_fixture(samples=160);ref=np.full(160,1000,np.int16)
        def silent(seed,ref,decoder,**options):
            from rate_distortion import encode_rate
            return encode_rate(seed,np.zeros_like(ref),decoder,lam=1.,allow_zero=True,compact_features=24,kind='music')
        out,pcm,report=search_budget([seed],ref,self.decoder,50,'music',lambdas=(1.,),refinement_trials=0,
            encoder=silent,candidate_guard=lambda candidate:bool(np.any(candidate)))
        self.assertIsNone(out);self.assertIsNone(pcm);self.assertEqual(report['status'],'no_fit')
        self.assertTrue(any(c['fits_budget'] and not c['quality_guard_passed'] for c in report['candidates']))


if __name__=='__main__':unittest.main()

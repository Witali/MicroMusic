"""Integer-headroom proposals preserve bitstream modes and decode correctly."""
from pathlib import Path
import sys,unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from gain_search import search_upshift,rescale_excitation
from batch_decoder import BatchSession
from lpx4 import decode
from q0_model import decode_pcm16
from test_beam_excitation import raw_fixture
from rate_distortion import serialize
from lossless_repack import layout
from perceptual_rate import expanded_v2


class GainSearchTests(unittest.TestCase):
    def test_headroom_shift_cannot_overflow_pcm16(self):
        for peak in (0,1,31,255,1000,16000,32767,-32768):
            x=np.array([peak,-peak if peak!=-32768 else 32767],np.int16)
            shift=search_upshift(x);scaled=x.astype(np.int64)*(1<<shift)
            self.assertTrue(np.all(scaled>=-32768));self.assertTrue(np.all(scaled<=32767))
            if peak:self.assertGreater(np.max(np.abs(scaled))*2,32767)

    def test_scale_proposal_keeps_sparse_payload_and_partial_tail(self):
        seed=raw_fixture(samples=81);frames=decode(seed)[0]
        q=np.zeros(81,np.int64);q[[0,20,40,80]]=1
        hints=np.array([[2,18,0,0]]*3,np.int64)
        blob,_=serialize(seed,frames,q,np.full(2,170),np.full(2,3),24,hints)
        with BatchSession('batch',v3_features=24) as decoder:
            for shift in (1,4):
                other=rescale_excitation(blob,shift)
                self.assertEqual(decode(other)[0],decode(blob)[0]);self.assertEqual(decode(other)[2],q.tolist())
                oldspans=layout(expanded_v2(blob))[3];newspans=layout(expanded_v2(other))[3]
                self.assertEqual([[c.mode for c in b.chunks] for b in oldspans],[[c.mode for c in b.chunks] for b in newspans])
                np.testing.assert_array_equal(decoder.decode_one_s16(other,81),decode_pcm16(other))
        self.assertIs(rescale_excitation(blob,0),blob)
        for value in (-1,16,1.5):
            with self.assertRaises(ValueError):rescale_excitation(blob,value)


if __name__=='__main__':unittest.main()

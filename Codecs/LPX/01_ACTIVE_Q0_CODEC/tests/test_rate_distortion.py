"""New encoder: exact serialized costs and native/state parity, no MCU changes."""
from pathlib import Path
import sys,unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from batch_decoder import BatchSession
from test_beam_excitation import raw_fixture
from rate_distortion import chunk_mode,block_bits,serialize,encode_rate,advance_history,scale_bits
from lpx4 import BitWriter,put_chunk,decode
from rice_v4_reference import write_scale


class RateCostTests(unittest.TestCase):
    def test_real_cost_matches_written_modes_including_zero_history(self):
        rng=np.random.default_rng(20261025)
        for bits in (0,2,3,4,5,6):
            for n in (1,17,40,79,80):
                q=(rng.integers(-(1<<(bits-1)),1<<(bits-1),n,dtype=np.int64) if bits else np.zeros(n,np.int64))
                history=np.zeros(145,np.int64);writer=BitWriter();old=[]
                writer.put(bits,3);write_scale(writer,17,210)
                for start in range(0,n,40):
                    y=q[start:start+40];cost,typ,lag,gain,k=chunk_mode(y,history,bits)
                    begin=writer.total;mode=('direct',int(k)) if typ==0 else ('exact',int(lag),int(gain),int(k))
                    put_chunk(writer,y.tolist(),old,bits,mode)
                    self.assertEqual(writer.total-begin,cost)
                    history=advance_history(history,y);old.extend(y)
                self.assertEqual(writer.total,block_bits(q,bits,210,17,np.zeros(145,np.int64)))
        for a,b in ((0,0),(0,255),(255,0),(127,128)):
            w=BitWriter();write_scale(w,a,b);self.assertEqual(w.total,scale_bits(a,b))

    def test_periodic_pitch_and_partial_chunk_reconstruct(self):
        seed=raw_fixture(samples=319);frames,_,_=decode(seed)
        q=np.resize(np.r_[np.ones(20,np.int64),-np.ones(20,np.int64)],319)
        out,bits=serialize(seed,frames,q,np.full(4,160),np.full(4,3))
        self.assertEqual(decode(out)[2],q.tolist());self.assertEqual(len(out),20+(bits+7)//8)


class NativeRateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.session=BatchSession('batch',v3_features=24);cls.decoder=cls.session.__enter__()
    @classmethod
    def tearDownClass(cls):cls.session.__exit__(None,None,None)

    def test_quantizer_cost_and_native_parity_on_clipping_and_partial_block(self):
        ref=np.resize(np.array([-32768,32767,0,-1,1,20000,-20000],np.int16),319)
        for compact in (0,24):
            out,pcm,r=encode_rate(raw_fixture(samples=len(ref)),ref,self.decoder,.003,False,compact,'music')
            self.assertEqual(len(pcm),len(ref));self.assertTrue(r['native_model_pcm_exact'])
            self.assertEqual(r['audio_packet_bytes'],len(out)-20)
            self.assertTrue(r['local_cost_exact_for_selected_v2_codes'])

    def test_determinism_silence_and_invalid_input(self):
        seed=raw_fixture(samples=160);ref=np.zeros(160,np.int16)
        a,pa,_=encode_rate(seed,ref,self.decoder,1.,True,24,'music')
        b,pb,_=encode_rate(seed,ref,self.decoder,1.,True,24,'music')
        self.assertEqual(a,b);np.testing.assert_array_equal(pa,pb);np.testing.assert_array_equal(pa,ref)
        for options in ({'lam':-1},{'lam':float('nan')},{'compact_features':4},{'kind':'bad'}):
            with self.assertRaises(ValueError):encode_rate(seed,ref,self.decoder,**options)
        with self.assertRaises(ValueError):encode_rate(seed,ref[:-1],self.decoder)


if __name__=='__main__':unittest.main()

import tempfile,unittest
from pathlib import Path
import numpy as np
import soundfile as sf
from batch_decoder import BatchSession
from test_beam_excitation import raw_fixture
from refine_bitrate_profile import refine,run

class BitrateProfileCliTests(unittest.TestCase):
    def test_perfect_input_retains_exact_rollback_and_written_audio(self):
        original=raw_fixture(samples=161)
        with BatchSession('batch',v3_features=24) as decoder:
            ref=decoder.decode_one_s16(original,161)
            b,p,r=refine(ref,original,decoder,len(original),12000,'music')
        self.assertEqual(b,original);np.testing.assert_array_equal(p,ref)
        self.assertFalse(r['changed']);self.assertEqual(r['search_trials'],0)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);sf.write(root/'ref.wav',ref,8000,subtype='PCM_16');(root/'base.l4hy').write_bytes(original)
            out=run(root/'ref.wav',root/'base.l4hy',root/'out',kind='music',max_bytes=len(original))
            self.assertFalse(out['changed']);self.assertEqual((root/'out/audio.l4hy').read_bytes(),original)
            pcm,sr=sf.read(root/'out/decoded.wav',dtype='int16');self.assertEqual(sr,8000);np.testing.assert_array_equal(pcm,ref)

    def test_rejects_infeasible_rollback_and_count_mismatch(self):
        original=raw_fixture(samples=40)
        with BatchSession('batch',v3_features=24) as decoder:
            for ref,cap in ((np.zeros(40,np.int16),20),(np.zeros(39,np.int16),len(original))):
                with self.assertRaises(ValueError):refine(ref,original,decoder,cap,kind='music')
            with self.assertRaises(ValueError):refine(np.zeros(40,np.int16),b'L4HY',decoder,100,kind='music')
            with self.assertRaises(ValueError):refine(np.zeros(40,np.int16),original,decoder,1000,kind='music',seeds=[b'L4HY'])

if __name__=='__main__':unittest.main()

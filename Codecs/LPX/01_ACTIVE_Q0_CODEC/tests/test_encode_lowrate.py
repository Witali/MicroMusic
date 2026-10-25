"""Public explicit encoder respects sample coverage, byte caps and source files."""
from pathlib import Path
import sys,tempfile,unittest
import numpy as np
import soundfile as sf
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from batch_decoder import BatchSession
from encode_lowrate import encode_lowrate,run
from lpx4 import decode


class LowrateEntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.session=BatchSession('batch',v3_features=24);cls.decoder=cls.session.__enter__()
    @classmethod
    def tearDownClass(cls):cls.session.__exit__(None,None,None)

    def test_public_pipeline_preserves_partial_segment_and_hard_cap(self):
        ref=np.rint(2000*np.sin(np.arange(641)*.14)).astype(np.int16)
        blob,pcm,r=encode_lowrate(ref,self.decoder,500,kind='music',stage='joint',lambdas=(.01,.3,1.),refinement_trials=0)
        self.assertEqual(r['status'],'ok');self.assertLessEqual(len(blob),500)
        self.assertEqual(len(decode(blob)[2]),641);self.assertEqual(len(pcm),641)
        np.testing.assert_array_equal(pcm,self.decoder.decode_one_s16(blob,641))
        self.assertEqual(r['metrics']['aligned_pcm16']['samples'],641)
        if r['legacy_target_available']:
            from wav_to_lpx4 import encode_segment
            _,old,_=encode_segment(ref,self.decoder,max_bytes=500,kind='music')
            self.assertLessEqual(np.sum((ref.astype(np.int64)-pcm)**2),np.sum((ref.astype(np.int64)-old)**2))

    def test_source_output_collision_and_invalid_profile_fail_before_writing(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'audio.l4hy';sf.write(path,np.zeros(160,np.int16),8000,format='WAV',subtype='PCM_16')
            original=path.read_bytes()
            with self.assertRaises(ValueError):run(path,Path(td),max_bytes=100)
            self.assertEqual(path.read_bytes(),original)
        with self.assertRaises(ValueError):encode_lowrate(np.zeros(160,np.int16),self.decoder,100,stage='bad')
        with self.assertRaises(ValueError):encode_lowrate(np.zeros(160,np.int16),self.decoder,19)


if __name__=='__main__':unittest.main()

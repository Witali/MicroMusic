"""Public explicit encoder respects sample coverage, byte caps and source files."""
from pathlib import Path
import sys,tempfile,unittest
from unittest.mock import patch
import numpy as np
import soundfile as sf
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from batch_decoder import BatchSession
from encode_lowrate import encode_lowrate,run
from lpx4 import decode
import encode_lowrate as entry


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


class JointSeedHandoffTests(unittest.TestCase):
    def test_joint_pipeline_rejects_a_large_level_error_without_mutes(self):
        ref=np.full(800,1000,np.int16);ref[0]=32767
        biased=np.full(800,25000,np.int16)
        with patch.object(entry,'_encode_core',return_value=(b'proposal',biased,{'status':'ok'})),patch.object(entry,'search_budget',return_value=(b'proposal',biased,{'status':'ok'})):
            blob,pcm,report=entry.encode_lowrate(ref,None,100)
        self.assertIsNone(blob);self.assertIsNone(pcm)
        self.assertEqual(report['status'],'no_fit')
        self.assertIn('waveform-error',report['no_fit_reason'])

    def test_joint_search_can_rescue_scalar_no_fit_with_bounded_diverse_seeds(self):
        # Isolate the public pipeline handoff, not bitstream arithmetic. The
        # scalar stage has no fit, while joint pitch/sparse can reach the cap.
        import hashlib
        ref=np.zeros(160,np.int16);calls=[]
        def blob(size,pre):
            out=bytearray(size);out[:4]=b'L4HY';out[8:12]=(160).to_bytes(4,'little');out[12:14]=pre.to_bytes(2,'little');return bytes(out)
        lpc=blob(150,13926);flat=blob(170,0);far=blob(201,0);fit=blob(90,13926)
        def segment(*args,**kw):
            if kw['max_bytes']!=65535:raise ValueError('No candidate fits the byte budget')
            kw['candidate_sink'](lpc,{'profile':'legacy','quality':{'rmse':1.}})
            kw['candidate_sink'](flat,{'profile':'flat','quality':{'rmse':2.}})
            return lpc,ref,{}
        def search(seeds,reference,decoder,max_bytes,kind,**kw):
            calls.append((seeds,kw))
            if len(calls)==1:
                for candidate,sse in [(lpc,200),(flat,100),(far,0)]:
                    kw['candidate_sink'](candidate,ref,{'full_sse':sse,'stream_sha256':hashlib.sha256(candidate).hexdigest()})
                return None,None,{'status':'no_fit'}
            self.assertEqual(set(seeds),{lpc,flat} if len(calls)==2 else {fit})
            self.assertGreaterEqual(max(kw['lambdas']),1.)
            self.assertEqual(kw['encoder_options']['level_floor_db'],-30.)
            return fit,ref,{'status':'ok'}
        with patch.object(entry,'encode_segment',side_effect=segment),patch.object(entry,'spectrum_seeds',return_value=([],[])),patch.object(entry,'search_budget',side_effect=search):
            out,pcm,report=entry.encode_lowrate(ref,None,100,kind='music',stage='joint')
        self.assertEqual(out,fit);np.testing.assert_array_equal(pcm,ref)
        self.assertEqual(report['target_search']['status'],'no_fit')
        self.assertEqual(report['status'],'ok');self.assertEqual(len(calls),4)


if __name__=='__main__':unittest.main()

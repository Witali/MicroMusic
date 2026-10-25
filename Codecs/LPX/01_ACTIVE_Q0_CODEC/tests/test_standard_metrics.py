from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from standard_metrics import error_metrics,delay_samples,compare,pwm_duties,ogg_accounting
from batch_decoder import BatchSession
from test_lossless_repack import fixture


class StandardMetricTests(unittest.TestCase):
    def test_candidate_observer_preserves_encoder_selection(self):
        from wav_to_lpx4 import encode_segment
        x=np.rint(5000*np.sin(2*np.pi*213*np.arange(320)/8000)).astype(np.int16)
        seen=[]
        def observer(blob,metadata):
            seen.append(blob);metadata['quality']['rmse']=123
        options={'lambdas':(0.,.1),'analysis_profiles':('flat',),'kind':'music'}
        with BatchSession('batch') as dec:
            a,p,r=encode_segment(x,dec,**options)
            b,q,s=encode_segment(x,dec,candidate_sink=observer,**options)
        self.assertEqual(a,b);np.testing.assert_array_equal(p,q)
        self.assertEqual(r,s);self.assertTrue(seen)

    def test_full_scale_error_does_not_overflow_int16(self):
        x=np.array([32767,-32768],np.int16);r=error_metrics(x,-x.astype(np.int32)-1)
        self.assertEqual(r['max_abs_error_pcm16'],65535)
        self.assertGreater(r['max_abs_error_percent_fs'],199.99)
        self.assertLess(r['ser_db'],-6.02)
        self.assertEqual(error_metrics(x,x)['ser_status'],'perfect')
        self.assertEqual(error_metrics([0,0],[1,-1])['ser_status'],'zero_reference')

    def test_delay_alignment_preserves_every_reference_sample(self):
        rng=np.random.default_rng(20261025);x=rng.integers(-20000,20000,8000,dtype=np.int16)
        y=np.r_[np.zeros(78,np.int16),x,np.zeros(640,np.int16)]
        self.assertEqual(delay_samples(x,y),78)
        report,aligned=compare(x,y)
        self.assertEqual(report['aligned_pcm16']['ser_status'],'perfect')
        self.assertEqual(report['aligned_pcm16']['samples'],len(x))
        np.testing.assert_array_equal(aligned,x)
        with self.assertRaises(ValueError):compare(x,y[:7000])

    def test_common_pwm_matches_native_lpx_including_clipping(self):
        blob=fixture([{'bits':6,'scale':255,'q':([-32,31,0,15,-16]*16)}])
        with BatchSession('batch') as dec:
            pcm=dec.decode_one_s16(blob,80);duties=dec.decode_one(blob,80)
        np.testing.assert_array_equal(pwm_duties(pcm),duties)
        self.assertEqual(pwm_duties([-32768,0,32767]).tolist(),[0,128,255])

    def test_ogg_accounts_continued_packets_and_rejects_truncation(self):
        def page(lace,payload,flags=0):
            h=bytearray(27);h[:5]=b'OggS\x00';h[5]=flags;h[14:18]=b'test';h[26]=len(lace)
            return bytes(h)+bytes(lace)+payload
        headers=page([8,3],b'OpusHeadtag')
        blob=headers+page([255],b'x'*255)+page([5],b'y'*5,1)
        r=ogg_accounting(blob)
        self.assertEqual(r['audio_packet_bytes'],260);self.assertEqual(r['codec_setup_bytes'],8)
        self.assertEqual(r['file_bytes'],sum(r[k] for k in ('audio_packet_bytes','codec_setup_bytes','comment_bytes','container_overhead_bytes')))
        with self.assertRaises(ValueError):ogg_accounting(blob[:-1])

    def test_encoder_cache_is_invalidated_by_input_or_binary_change(self):
        from benchmark_standards import external_encoder
        def encode(cmd,**kwargs):
            payload=Path(cmd[cmd.index('-i')+1]).read_bytes()
            h=bytearray(27);h[:5]=b'OggS\x00';h[26]=3
            Path(cmd[-1]).write_bytes(bytes(h)+bytes([8,3,len(payload)])+b'OpusHeadtag'+payload)
            return SimpleNamespace(returncode=0,stderr=b'')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/'input.wav';source.write_bytes(b'first')
            with patch('benchmark_standards.subprocess.run',side_effect=encode) as call,patch('benchmark_standards.encoder_revision',return_value='binary-A'):
                a=external_encoder(source,root/'out','opus_audio',8000)
                b=external_encoder(source,root/'out','opus_audio',8000)
                self.assertEqual(call.call_count,1);self.assertEqual(a,b)
                source.write_bytes(b'second')
                c=external_encoder(source,root/'out','opus_audio',8000)
                self.assertEqual(call.call_count,2);self.assertNotEqual(a['stream_sha256'],c['stream_sha256'])
            with patch('benchmark_standards.subprocess.run',side_effect=encode) as call,patch('benchmark_standards.encoder_revision',return_value='binary-B'):
                external_encoder(source,root/'out','opus_audio',8000)
                self.assertEqual(call.call_count,1)


if __name__=='__main__':unittest.main()

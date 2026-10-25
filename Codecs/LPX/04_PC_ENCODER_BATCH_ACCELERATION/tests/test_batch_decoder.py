"""Public, reproducible native LPC batch decoding and optimizer regression.

Inputs are synthetic (not private speech). The historical subprocess decoder
and the new in-memory C++ bridge execute the same, unmodified codec core.
"""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import warnings
import wave
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from batch_decoder import BatchSession
from refine_fixedrate import refine, parse_sections
from tune_header_fixedrate import run as tune_header


class BatchCodecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='lpx4batchtest_')
        cls.path = Path(cls.temporary.name)
        cls.host = cls.path/'reference_cpp_decoder'
        subprocess.run(['g++','-O3','-std=c++11','-I'+str(ROOT/'src'),
                        str(ROOT/'src'/'Lpx4HybridCore.cpp'),
                        str(ROOT/'tests'/'decode_host.cpp'),'-o',str(cls.host)],
                       check=True, capture_output=True)
        cls.session = BatchSession('batch')
        cls.batch = cls.session.__enter__()
        cls.pcm = {}
        for stem, relative in [
            ('sparse','examples/SYNTHETIC_CELP_BUDGET/synthetic_celp_budget.l4hy')]:
            blob=(ROOT/relative).read_bytes()
            cls.pcm[stem]=(blob,cls.reference(blob))
        cls.wav = cls.path/'reference.wav'
        arr=np.frombuffer(cls.pcm['sparse'][1],dtype=np.uint8)
        s16=((arr.astype(np.int16)-128)*256).astype('<i2')
        with wave.open(str(cls.wav),'wb') as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000)
            w.writeframes(s16.tobytes())

    @classmethod
    def tearDownClass(cls):
        cls.session.__exit__(None,None,None)
        cls.temporary.cleanup()

    @classmethod
    def reference(cls,blob):
        i=cls.path/'input.l4hy';o=cls.path/'output.pcm'
        i.write_bytes(blob)
        r=subprocess.run([str(cls.host),str(i),str(o)],capture_output=True)
        if r.returncode:raise RuntimeError(r.stderr.decode())
        return o.read_bytes()

    def test_native_decoder_pcm_exact(self):
        for stem,(blob,expected) in self.pcm.items():
            with self.subTest(stem=stem):
                actual=self.batch.decode_one(blob,len(expected))
                self.assertIsNotNone(actual)
                self.assertEqual(actual.tobytes(),expected)

    def test_invalid_candidate_isolated(self):
        blob,expected=self.pcm['sparse']
        trial=self.batch.decode_many([blob,b'bad',blob],len(expected))
        self.assertEqual(trial[0].tobytes(),expected)
        self.assertIsNone(trial[1])
        self.assertEqual(trial[2].tobytes(),expected)

    def test_header_quality_full_byte_equality(self):
        blob,_=self.pcm['sparse']
        start=self.path/'header_start.l4hy';start.write_bytes(blob)
        original=self.path/'header_ref.l4hy';optimized=self.path/'header_batch.l4hy'
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',RuntimeWarning)
            a=tune_header(start,self.wav,self.host,original,self.path/'h_ref.json',
                          max_trials=55,batch_decoder=None)
            b=tune_header(start,self.wav,self.host,optimized,self.path/'h_batch.json',
                          max_trials=55,batch_decoder=self.batch)
        self.assertEqual(original.read_bytes(),optimized.read_bytes())
        for key in ('final','baseline','output_header','decoded_trials','sha256'):
            self.assertEqual(a[key],b[key],key)

    def test_sparse_celp_trial_byte_equality(self):
        blob,_=self.pcm['sparse']
        self.assertGreater(len(parse_sections(blob)),0)
        inp=self.path/'pulse_input.l4hy';inp.write_bytes(blob)
        aout=self.path/'pulse_reference.l4hy';bout=self.path/'pulse_batch.l4hy'
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',RuntimeWarning)
            a=refine(inp,self.wav,self.host,aout,passes=1,max_eval=83,batch_decoder=None)
            b=refine(inp,self.wav,self.host,bout,passes=1,max_eval=83,batch_decoder=self.batch)
        self.assertEqual(a['trials'],83)
        self.assertEqual(b['trials'],83)
        self.assertEqual(aout.read_bytes(),bout.read_bytes())
        self.assertEqual(a,b)


if __name__=='__main__':unittest.main()

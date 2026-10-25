"""Regression suite for LPX4 v2 old-Q0 encoder-only refinements.

No private recordings required; synthetic LPX4 sample is included in source.
"""
from __future__ import annotations
import sys,unittest,tempfile,wave
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from batch_decoder import BatchSession
from lpx4 import decode
from refine_lsf_pcm16 import read_scanned_fields,patch_bits,optimize as tune_lsf
from refine_excitation_pcm16 import scan_tokens,optimize as tune_quant
from optimize_old_lpc import run

class OldLPCEncoderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stream=(ROOT/'examples'/'SYNTHETIC_CELP_BUDGET'/'synthetic_celp_budget.l4hy').read_bytes()
        cls.total=int.from_bytes(cls.stream[8:12],'little')

    def test_spectral_field_locations_and_bounds(self):
        fields,timeline=read_scanned_fields(self.stream)
        self.assertTrue(fields)
        self.assertTrue(np.all(np.diff(timeline,axis=1)>=10))
        f=fields[0]
        original=sum(((self.stream[(f.bit_offset+j)//8]>>((f.bit_offset+j)%8))&1)<<j for j in range(f.width))
        self.assertEqual(original,f.stored if f.kind=='absolute' else f.stored &255)
        self.assertEqual(len(patch_bits(self.stream,f.bit_offset,f.width,original)),len(self.stream))

    def test_excitation_codeword_length_preserved(self):
        tokens=scan_tokens(self.stream)
        self.assertTrue(tokens)
        cases=[t for t in tokens if t.possible(max_diff=2)]
        self.assertTrue(cases)
        for tok in cases[:20]:
            for value,(offset,width,bits) in tok.possible()[:2]:
                self.assertEqual(width,tok.width)
                self.assertEqual(len(patch_bits(self.stream,offset,width,bits)),len(self.stream))

    def test_perfect_reference_is_never_degraded(self):
        with BatchSession('batch') as decoder:
            original=decoder.decode_one_s16(self.stream,self.total)
            self.assertIsNotNone(original)
            a,p,q=tune_lsf(self.stream,original,decoder,max_trials=80,step_sizes=(2,1),min_stoi_delta=0.0)
            self.assertEqual(a,self.stream)
            self.assertTrue(np.array_equal(p,original))
            a,p,q=tune_quant(self.stream,original,decoder,max_trials=100,per_40=6,stoi_drop=0.0)
            self.assertEqual(a,self.stream)
            self.assertTrue(np.array_equal(p,original))

    def test_public_cli_end_to_end(self):
        with BatchSession('batch') as decoder:
            pcm=decoder.decode_one_s16(self.stream,self.total)
        with tempfile.TemporaryDirectory() as td:
            p=Path(td); src=p/'input.l4hy';src.write_bytes(self.stream)
            wav=p/'ref.wav'
            with wave.open(str(wav),'wb') as wf:
                wf.setnchannels(1);wf.setsampwidth(2);wf.setframerate(8000)
                wf.writeframes(pcm.astype('<i2').tobytes())
            report=run(src,wav,p/'output.l4hy',lsf_trials=60,excitation_trials=80,header_trials=0)
            self.assertEqual(report['input_sha256'],report['output_sha256'])
            self.assertTrue((p/'output.wav').is_file())
            self.assertTrue((p/'output.json').is_file())
            self.assertEqual((p/'output.l4hy').read_bytes(),self.stream)

if __name__=='__main__':unittest.main()

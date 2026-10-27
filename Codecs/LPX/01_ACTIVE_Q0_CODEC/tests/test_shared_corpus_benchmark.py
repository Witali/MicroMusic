"""Result caches must preserve exact references, extras and complete spans."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
import numpy as np
import soundfile as sf
from benchmark_shared_corpus import (canonical, sha, validate_saved, validated_inputs,
                                    quality)
from speech_compact import pack, decode_model
from standard_metrics import pwm_duties


class SharedCorpusBenchmarkTests(unittest.TestCase):
    def fixture(self, root):
        blob, _ = pack(1280, 4, [list(range(10))]*4, [(8,18,0)]*8, [(0,8)]*64,
                       extras=[(1,1)]+[(-1,0)]*31)
        pcm = decode_model(blob)
        digest = sha(pcm.astype('<i2').tobytes())
        inputs, dest = root/'inputs', root/'output'
        inputs.mkdir(); dest.mkdir()
        sf.write(inputs/'reference.wav', pcm, 8000, subtype='PCM_16')
        sf.write(dest/'decoded.wav', pcm, 8000, subtype='PCM_16')
        sf.write(dest/'complete.wav', pcm, 8000, subtype='PCM_16')
        (dest/'stream.l4hy').write_bytes(blob)
        segment = {'index':0,'start':0,'samples':1280,'reference':'reference.wav','pcm16_sha256':digest}
        case = {'id':'case-fixture','samples':1280,'reference':'reference.wav',
                'reference_pcm16_sha256':digest,'segments':[segment]}
        row = {'id':case['id'],'profile':4,'status':'complete','fingerprint':'identity',
               'environment':{},'reference_pcm16_sha256':digest,'file_bytes':len(blob),'pcm16_sha256':digest,
               'segments':[{'index':0,'start':0,'samples':1280,'stream':'stream.l4hy','decoded':'decoded.wav',
                            'stream_sha256':sha(blob),'pcm16_sha256':digest,'pwm_sha256':sha(pwm_duties(pcm).tobytes()),
                            'file_bytes':len(blob),'cap_bytes':100}]}
        row['report_sha256'] = sha(canonical(row))
        return case, row, inputs, dest, pcm

    def test_valid_enhanced_extras_cache_is_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            case,row,inputs,dest,_ = self.fixture(Path(folder))
            self.assertEqual((dest/'stream.l4hy').read_bytes()[5],132)
            self.assertIs(validate_saved(row,case,4,{},'identity',dest,inputs),row)

    def test_modified_whole_or_segment_reference_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            case,row,inputs,dest,pcm = self.fixture(Path(folder))
            changed=pcm.copy();changed[0]^=1
            sf.write(inputs/'reference.wav',changed,8000,subtype='PCM_16')
            with self.assertRaisesRegex(ValueError,'reference changed'):
                validate_saved(row,case,4,{},'identity',dest,inputs)

    def test_noncontiguous_span_and_wrong_slice_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            case,row,inputs,dest,pcm = self.fixture(Path(folder))
            bad=deepcopy(case);bad['segments'][0]['start']=1
            with self.assertRaisesRegex(ValueError,'accounting'):
                validated_inputs(inputs,bad)
            changed=pcm.copy();changed[0]^=1
            sf.write(inputs/'other.wav',changed,8000,subtype='PCM_16')
            bad=deepcopy(case);bad['segments'][0].update(reference='other.wav',pcm16_sha256=sha(changed.astype('<i2').tobytes()))
            with self.assertRaisesRegex(ValueError,'slice'):
                validated_inputs(inputs,bad)

    def test_report_identity_and_result_pcm_tampering_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            case,row,inputs,dest,pcm = self.fixture(Path(folder))
            bad=deepcopy(row);bad['file_bytes']+=1
            with self.assertRaisesRegex(ValueError,'metadata'):
                validate_saved(bad,case,4,{},'identity',dest,inputs)
            with self.assertRaisesRegex(ValueError,'metadata'):
                validate_saved(row,case,6,{},'identity',dest,inputs)
            changed=pcm.copy();changed[0]^=1
            sf.write(dest/'complete.wav',changed,8000,subtype='PCM_16')
            with self.assertRaisesRegex(ValueError,'reference changed'):
                validate_saved(row,case,4,{},'identity',dest,inputs)

    def test_pwm_metrics_apply_transfer_once_and_detect_lost_quiet_detail(self):
        reference=np.tile(np.asarray([-20,20],np.int16),400)
        actual=quality(reference,reference,False)
        self.assertEqual(actual['pcm16']['error_energy'],0)
        self.assertEqual(actual['pwm8']['error_energy'],actual['pcm16']['reference_energy'])
        self.assertTrue(actual['activity_preserved'])
        self.assertFalse(actual['pwm_activity_preserved'])


if __name__=='__main__':unittest.main()

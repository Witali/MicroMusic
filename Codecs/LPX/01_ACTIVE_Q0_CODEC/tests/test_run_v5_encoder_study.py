import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import soundfile as sf

from batch_decoder import ROOT
from benchmark_speech_flash import source_hashes
from measure_speech_firmware import REPOSITORY
from refine_speech_compact import quality
from run_v5_encoder_study import run
from select_speech_budget import quality_source_fingerprint
import speech_compact as compact


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def fixture(folder):
    blobs = [compact.pack(n, 6, [[4 + 6 * i for i in range(10)]] * ((n + 319) // 320),
        [(8, 55, 0)] * (2 * ((n + 319) // 320)), [(5, -3)] * (16 * ((n + 319) // 320)), pre=0)[0]
        for n in (81, 641)]
    pcm = np.concatenate([compact.decode_model(b) for b in blobs])
    reference = folder / 'reference.wav'; sf.write(reference, pcm, 8000, subtype='PCM_16')
    segments = []; position = 0
    for index, blob in enumerate(blobs):
        path = folder / f'seed-{index}.l4hy'; path.write_bytes(blob); n = compact.unpack(blob)[0]
        segments.append(dict(index=index, start=position, samples=n, path=str(path), stream_sha256=sha(blob), file_bytes=len(blob)))
        position += n
    size = sum(map(len, blobs))
    record = dict(id='speech-profile-001', profile=6, split='tuning', samples=len(pcm),
        reference=dict(path=str(reference), file_sha256=sha(reference.read_bytes()), pcm16_sha256=sha(pcm.astype('<i2').tobytes())),
        segments=segments, baseline_bytes=size, baseline_metrics=quality(pcm, pcm),
        budgets=[dict(percent=p, max_complete_stream_bytes=size * p // 100) for p in (100, 95, 90)])
    manifest = dict(schema='lpx-v5-encoder-quality-study-v1', source_sha256=source_hashes(ROOT / 'src'),
        quality_source_fingerprint=quality_source_fingerprint(), records=[record])
    path = folder / 'manifest-private.json'; path.write_text(json.dumps(manifest), encoding='utf-8')
    return path, manifest, blobs


class EncoderStudyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (REPOSITORY / 'build').mkdir(exist_ok=True)

    def test_real_multisegment_control_budgets_parity_and_immutable_outputs(self):
        with tempfile.TemporaryDirectory(dir=REPOSITORY / 'build') as temporary:
            folder = Path(temporary); path, _, blobs = fixture(folder)
            result = run(path, folder / 'experiment', variant='old-default')
            self.assertEqual(result['status'], 'complete')
            self.assertEqual(result['unique_streams_native_model_pwm_exact'], 2)
            budgets = result['records'][0]['budgets']
            self.assertEqual([b['percent'] for b in budgets], [100, 95, 90])
            self.assertEqual(budgets[0]['selected']['stream_bytes'], sum(map(len, blobs)))
            self.assertEqual([Path(s['path']).read_bytes() for s in budgets[0]['selected']['segments']], blobs)
            for budget in budgets[1:]:
                self.assertIsNone(budget['selected'])
                self.assertIsNone(budget['tradeoff'])
                self.assertEqual(budget['selection']['status'], 'no_pool_combination_fits')
            with self.assertRaisesRegex(ValueError, 'immutable'):
                run(path, folder / 'experiment', variant='old-default')

    def test_changed_input_or_budget_cannot_become_completed_evidence(self):
        with tempfile.TemporaryDirectory(dir=REPOSITORY / 'build') as temporary:
            folder = Path(temporary); path, manifest, _ = fixture(folder)
            manifest['records'][0]['budgets'][0]['max_complete_stream_bytes'] -= 1
            path.write_text(json.dumps(manifest), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'budget changed'):
                run(path, folder / 'wrong-budget', variant='old-default')
            partial = json.loads((folder / 'wrong-budget/results-private.json').read_text())
            self.assertEqual(partial['status'], 'running')
            ref = Path(manifest['records'][0]['reference']['path'])
            ref.write_bytes(ref.read_bytes() + b'changed')
            with self.assertRaisesRegex(ValueError, 'reference file changed'):
                run(path, folder / 'wrong-reference', variant='old-default')


if __name__ == '__main__':
    unittest.main()

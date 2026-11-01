import json
from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import soundfile as sf

import benchmark_nonspeech_trajectory as robustness
import audit_nonspeech_trajectory as independent_audit
from batch_decoder import BatchSession
import speech_compact as compact
from standard_metrics import pwm_duties
from test_refine_speech_trajectory import seed, altered


class NonSpeechRobustnessTests(unittest.TestCase):
    def test_centered_substitution_is_exact_without_rebuilding_long_arrays(self):
        ref = np.asarray([0, 100, -100, 32767], np.int16)
        baseline = np.asarray([10, 80, -90, 32760], np.int16)
        candidate = np.asarray([1, 99, -99, 32767], np.int16)
        huge = (1 << 60)+123
        objective = robustness.SubstitutionObjective(ref, baseline, huge)
        before = sum((int(a)-int(b))**2 for a, b in zip(ref, baseline))
        after = sum((int(a)-int(b))**2 for a, b in zip(ref, candidate))
        with patch.object(np, 'concatenate', side_effect=AssertionError('No full-record allocation')):
            self.assertEqual(objective(candidate), after-before)
            self.assertEqual(objective.whole_error(candidate), huge-before+after)
        self.assertEqual(float(objective(candidate)), after-before)
        with self.assertRaises(ValueError):
            robustness.SubstitutionObjective(ref, baseline, before-1)

    def test_chunked_exact_sse_and_segment_choice_use_integer_arithmetic(self):
        x = np.full(200000, -32768, np.int16)
        y = np.full(200000, 32767, np.int16)
        self.assertEqual(robustness.exact_sse(x, y), 200000*65535**2)
        self.assertEqual(robustness.select_segments([4, 8, 0], [4, 2, 3]), [1, 2])
        self.assertEqual(robustness.select_segments([4, 2], [4, 2]), [0, 1])
        self.assertEqual(robustness.select_segments([1, 8], [4, 2]), [1])
        self.assertEqual(robustness.select_segments([2**54+1, 2**54], [7, 7]), [0, 1])

    def test_numerical_metrics_have_no_stoi_and_descriptors_are_not_vad(self):
        ref = np.asarray([-32768, 32767, 0, 255, 256, -256], np.int16)
        with patch('pystoi.stoi', side_effect=AssertionError('STOI forbidden')):
            result = robustness.numerical_metrics(ref, ref)
        self.assertNotIn('stoi', result['pcm16'])
        self.assertNotIn('stoi', result['pwm8'])
        self.assertEqual(result['pcm16']['exact_error_energy'], 0)
        stats = robustness.descriptors(ref)
        self.assertEqual(stats['peak_abs_pcm16'], 32768)
        self.assertEqual(stats['full_scale_sample_fraction'], 2/6)
        self.assertEqual(stats['activity_abs_ge_256_fraction'], 4/6)
        self.assertEqual(stats['nonzero_fraction'], 5/6)
        self.assertTrue(robustness.numerical_floors(result, result))

    def test_smoke_depends_on_geometry_and_earliest_case_ties_only(self):
        records = [dict(private_case_id=case, profile=profile, samples=n)
                   for case, n in (('short', 10), ('middle', 30), ('long', 80))
                   for profile in (4, 6)]
        self.assertEqual(robustness.smoke_indices(records), [0, 1, 4, 5])
        for record in records:
            record['unrelated_quality'] = -record['samples']
        self.assertEqual(robustness.smoke_indices(records), [0, 1, 4, 5])

    def test_private_outputs_reject_aliases_and_escape(self):
        with tempfile.TemporaryDirectory(dir=robustness.REPOSITORY/'build') as directory:
            folder = Path(directory);source = folder/'source';source.write_bytes(b'preserve')
            target = folder/'target';os.link(source, target)
            with self.assertRaises(ValueError):robustness.guard_outputs([source], [target])
            self.assertEqual(source.read_bytes(), b'preserve')
        with self.assertRaises(ValueError):robustness.guard_outputs([], [robustness.REPOSITORY/'escape'])

    def test_complete_reset_chain_search_and_independent_final_reconstruction(self):
        with tempfile.TemporaryDirectory(dir=robustness.REPOSITORY/'build') as directory:
            folder = Path(directory);blobs = [seed(4, 321), seed(4, 137)]
            ref = np.concatenate([compact.decode_model(altered(blobs[0], [0])), compact.decode_model(blobs[1])])
            baseline = np.concatenate([compact.decode_model(blob) for blob in blobs])
            reference_path = folder/'reference.wav';sf.write(reference_path, ref, 8000, subtype='PCM_16')
            segments = [];offset = 0
            for index, blob in enumerate(blobs):
                path = folder/f'input-{index}.l4hy';path.write_bytes(blob);n = len(compact.decode_model(blob))
                segments.append(dict(index=index, start=offset, samples=n, profile=4, path=str(path),
                                     stream_sha256=robustness.sha(blob), file_bytes=len(blob)));offset += n
            record = dict(id='synthetic-group', private_case_id='synthetic-case', profile=4, samples=len(ref),
                baseline_bytes=sum(map(len, blobs)), segments=segments,
                reference=dict(path=str(reference_path), file_sha256=robustness.sha(reference_path.read_bytes()),
                               pcm16_sha256=robustness.sha(ref.astype('<i2').tobytes())),
                baseline_pcm16_sha256=robustness.sha(baseline.astype('<i2').tobytes()),
                baseline_pwm_sha256=robustness.sha(pwm_duties(baseline).tobytes()))
            settings = dict(robustness.SETTINGS, max_evaluations=4, spectral_candidates=1, excitation_candidates=0)
            with BatchSession('batch', speech=True, speech_compact=True) as common, BatchSession('batch', speech=True, speech_compact=True, compact_only=True) as narrow:
                with patch('refine_speech_trajectory.quality', side_effect=AssertionError('Speech metrics forbidden')):
                    result = robustness.run_group(record, 1, folder/'output', common, narrow, settings)
                    checked = independent_audit.audit_group(record, result, folder/'output', common, narrow)
                    self.assertTrue(checked['full_reference_metrics_caps_and_policy_exact'])
                    forged = deepcopy(result)
                    forged['outputs']['selected']['metrics']['pcm16']['exact_error_energy'] += 1
                    with self.assertRaises(AssertionError):
                        independent_audit.audit_group(record, forged, folder/'output', common, narrow)
            self.assertEqual(result['samples'], 458)
            self.assertEqual(result['selected_segments'], [0, 1])
            self.assertTrue(result['all_native_common_v5_model_pcm_pwm_exact'])
            self.assertFalse(result['stoi_computed'])
            self.assertTrue(result['outputs']['selected']['whole_numerical_floors_passed'])
            self.assertLessEqual(result['outputs']['selected']['stream_bytes'], record['baseline_bytes'])
            self.assertLessEqual(result['outputs']['raw']['stream_bytes'], record['baseline_bytes'])
            self.assertEqual(json.loads((folder/'output/result-private.json').read_text())['samples'], 458)


if __name__ == '__main__':
    unittest.main()

import unittest

import numpy as np

from speech_voice_objective import VoiceObjective, VoiceWeights, _period_profiles


def tone(frequency=200., amplitude=160., samples=8000, harmonics=(1., .4, .2)):
    time = np.arange(samples) / 8000
    wave = sum(weight * np.sin(2 * np.pi * frequency * (index + 1) * time)
               for index, weight in enumerate(harmonics))
    return np.rint(amplitude * wave).astype(np.int16)


def objective(reference, period=40.):
    count = max(0, (len(reference) - 640) // 160 + 1)
    return VoiceObjective(reference, np.full(count, period))


class VoiceObjectiveTests(unittest.TestCase):
    def test_quiet_correct_voice_beats_octaves_noise_and_disappearance(self):
        rng = np.random.default_rng(114)
        for amplitude in (2000, 32, 4):
            source = tone(amplitude=amplitude)
            score = objective(source)
            near = np.clip(source.astype(np.int32) + rng.integers(-1, 2, len(source)), -32768, 32767).astype(np.int16)
            self.assertEqual(score(source), 0.)
            for wrong in (tone(100, amplitude), tone(400, amplitude), np.zeros_like(source)):
                self.assertLess(score(near), score(wrong))
            self.assertGreater(score.components(np.zeros_like(source))['periodicity'], .1)

    def test_envelope_and_original_amplitude_both_count(self):
        source = tone(amplitude=200)
        score = objective(source)
        reshaped = tone(amplitude=200, harmonics=(.2, 1., .5))
        louder = source * 2
        self.assertGreater(score.components(reshaped)['spectrum'], .05)
        self.assertLess(score.components(louder)['spectrum'], 1e-20)
        self.assertGreater(score(louder), score(source))

    def test_analysis_is_approximately_gain_independent_above_pcm_quantization(self):
        source = tone(amplitude=200)
        candidate = tone(220, 200)
        first = objective(source).components(candidate)
        second = objective(source * 8).components(candidate * 8)
        for key in ('waveform', 'spectrum', 'periodicity'):
            self.assertAlmostEqual(first[key], second[key], places=12)

    def test_known_period_profile_and_constant_output_penalty(self):
        alternating = np.tile([1., -1.], 320)[None, :]
        profile = _period_profiles(alternating, np.array([2.]), np.array([640]))
        np.testing.assert_allclose(profile, [[2., 0., 2., 0.]])
        np.testing.assert_array_equal(_period_profiles(np.zeros_like(alternating), np.array([2.]), np.array([640])), np.ones((1, 4)))

    def test_unknown_source_pitch_silence_and_short_tails_are_explicit(self):
        for n in (1, 19, 159, 641, 803):
            source = np.zeros(n, np.int16)
            score = VoiceObjective(source)
            self.assertEqual(score(source), 0.)
            self.assertEqual(score.describe()['source_voiced_windows'], 0)
            self.assertEqual(score.components(np.ones(n, np.int16))['voiced_windows'], 0)
            self.assertGreater(score(np.ones(n, np.int16)), 0)

    def test_owned_inputs_and_consistent_range(self):
        source = tone()
        saved = source.copy()
        score = objective(source)
        source[:] = 0
        self.assertEqual(score(saved), 0.)
        self.assertEqual(score.score_range(saved, 0), score(saved))
        self.assertEqual(score.score_range(saved[160:1440], 160), 0.)
        with self.assertRaises(ValueError):
            score(saved[:100])
        with self.assertRaises(ValueError):
            score.periods[0] = 50

    def test_invalid_geometry_periods_and_values(self):
        source = tone()
        for weights in (dict(waveform=-1), dict(spectrum=np.inf), dict(periodicity=True),
                        dict(waveform=0, spectrum=0, periodicity=0)):
            with self.assertRaises(ValueError):
                VoiceWeights(**weights)
        for settings in (dict(frame_samples=True), dict(hop_samples=0), dict(bands=900),
                         dict(period_samples=[0]), dict(period_samples=[np.inf])):
            with self.assertRaises(ValueError):
                VoiceObjective(source, **settings)
        with self.assertRaises(ValueError):
            VoiceObjective(source.astype(float))


if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python3
"""Strongest-partial selection, identity continuity and tolerance contracts."""
import sys
import unittest
from copy import deepcopy
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
from harmonic_tracks import HarmonicTrackObjective, _associate


class HarmonicTracksTests(unittest.TestCase):
    sr = 7500
    samples = 12032

    def tone(self,hz,amplitude=.2):
        return amplitude*np.sin(2*np.pi*hz*np.arange(self.samples)/self.sr)

    def test_identity_scale_and_maximum_strongest_ten(self):
        audio = sum(self.tone(100+250*k,.01*(k+1)) for k in range(12))
        objective = HarmonicTrackObjective(audio)
        result = objective.evaluate(audio*3)
        self.assertLess(result['harmonic_track_loss'],1e-10)
        self.assertGreater(result['weighted_match_rate'],1-1e-10)
        tracks = objective.reference_tracks
        self.assertTrue(np.all(tracks['count'] <= 10))
        self.assertTrue(np.all(tracks['count'][5:-5] == 10))
        # The strongest ten include the highest tones, rather than the first
        # ten multiples of an estimated fundamental or frequency-order slots.
        selected = tracks['frequency_hz'][len(tracks['times'])//2]
        self.assertGreater(float(np.min(selected)),550)
        self.assertLess(float(np.max(abs(np.sort(selected)-(100+250*np.arange(2,12))))),1.)

    def test_detuning_absolute_errors_and_cached_tolerances(self):
        original = self.tone(500)
        candidate = self.tone(510)
        objective = HarmonicTrackObjective(original)
        first = objective.evaluate(candidate)
        loose = objective.with_tolerances(frequency_tolerance_cents=100,
                                         frequency_tolerance_hz=5,amplitude_tolerance_db=6)
        second = loose.evaluate(candidate)
        self.assertIs(objective.reference_tracks,loose.reference_tracks)
        self.assertAlmostEqual(first['frequency_error_hz'],10,delta=.5)
        self.assertGreater(first['frequency_error_cents'],30)
        self.assertLess(second['harmonic_track_loss'],first['harmonic_track_loss'])
        for key in ('frequency_error_cents','frequency_error_hz','level_error_db',
                    'frequency_error_p95_cents','frequency_error_p95_hz',
                    'level_error_p95_db','missing_reference_energy','extra_candidate_energy'):
            self.assertEqual(first[key],second[key],key)

    def test_missing_extra_level_and_octave_are_measured(self):
        first,second = self.tone(400),self.tone(1100)
        objective = HarmonicTrackObjective(first+second)
        missing = objective.evaluate(first)
        self.assertGreater(missing['missing_reference_energy'],.4)
        self.assertLess(missing['weighted_match_rate'],.6)
        levels = objective.evaluate(2*first+second)
        self.assertGreater(levels['level_error_db'],1.)
        extra = HarmonicTrackObjective(first).evaluate(first+self.tone(1800))
        self.assertGreater(extra['extra_candidate_energy'],.3)
        octave = HarmonicTrackObjective(first).evaluate(self.tone(800))
        self.assertGreater(octave['missing_reference_energy'],.9)
        self.assertGreater(octave['extra_candidate_energy'],.9)
        self.assertLess(octave['weighted_match_rate'],.1)

    def test_silence_and_noise_are_finite_without_scaling_extra_away(self):
        silence = np.zeros(self.samples)
        tone = self.tone(500)
        silent = HarmonicTrackObjective(silence)
        self.assertEqual(silent.evaluate(silence)['harmonic_track_loss'],0)
        extra = silent.evaluate(tone)
        self.assertAlmostEqual(extra['extra_candidate_energy'],1)
        missing = HarmonicTrackObjective(tone).evaluate(silence)
        self.assertAlmostEqual(missing['missing_reference_energy'],1)
        noise = np.random.default_rng(42).normal(0,.1,self.samples)
        result = HarmonicTrackObjective(tone).evaluate(noise)
        self.assertTrue(all(np.isfinite(value) for value in result.values()))
        self.assertGreater(result['extra_candidate_energy'],.1)
        self.assertGreater(result['missing_reference_energy'],.5)

    def test_ids_survive_amplitude_rank_swaps_and_short_gaps(self):
        t = np.arange(self.samples)/self.sr
        first = self.tone(440)*(.7+.6*np.sin(2*np.pi*t))
        first[(t>.65)&(t<.87)] = 0
        second = self.tone(1100)*(.7-.6*np.sin(2*np.pi*t))
        tracks = HarmonicTrackObjective(first+second).reference_tracks
        def identity(time,frequency):
            row = int(np.argmin(abs(tracks['times']-time)))
            col = int(np.nanargmin(abs(tracks['frequency_hz'][row]-frequency)))
            return tracks['track_id'][row,col]
        self.assertEqual(identity(.3,1100),identity(1.2,1100))
        self.assertEqual(identity(.4,440),identity(1.05,440))

    def test_crossing_prediction_and_trajectory_fragmentation_guard(self):
        # Perfect sub-bin trajectories isolate association from the physical
        # STFT limit at an unresolved crossing. A missing peak represents the
        # crossing's temporary inability to resolve both sources.
        count = 31
        a,b = np.linspace(400,700,count),np.linspace(700,400,count)
        frequency = np.c_[a,b]
        amplitude = np.c_[np.linspace(.3,.1,count),np.linspace(.1,.3,count)]
        frequency[14:17,1] = np.nan
        amplitude[14:17,1] = 0
        ids = _associate(frequency,amplitude,128/7500,7500/1024,8)
        self.assertEqual(ids[2,0],ids[-3,0])
        self.assertEqual(ids[2,1],ids[-3,1])
        # Actual smoothly chirping signals must produce time-varying tracks,
        # not a fixed global peak list.
        t = np.arange(self.samples)/self.sr
        chirp = .2*np.sin(2*np.pi*(350*t+110*t*t))
        objective = HarmonicTrackObjective(chirp)
        tracks = objective.reference_tracks
        dominant = tracks['frequency_hz'][:,0]
        self.assertGreater(float(dominant[-6]-dominant[6]),200)
        details = objective.details(chirp)
        self.assertLess(details['metrics']['continuity_break_rate'],1e-10)
        self.assertTrue(details['matches'])
        self.assertTrue(all(match['frame'] >= 0 and 'reference_id' in match for match in details['matches']))

    def test_invalid_inputs_and_tolerances(self):
        objective = HarmonicTrackObjective(self.tone(500))
        for kwargs in (dict(max_tracks=11),dict(n_fft=512),dict(frequency_tolerance_cents=0),
                       dict(amplitude_tolerance_db=0),dict(frequency_tolerance_hz=-1)):
            with self.assertRaises(ValueError):
                HarmonicTrackObjective(self.tone(500),**kwargs)
        with self.assertRaises(ValueError):
            objective.evaluate(self.tone(500)[:-1])

    def test_candidate_id_resets_cannot_erase_reference_motion_error(self):
        source = self.tone(2000)
        objective = HarmonicTrackObjective(source,max_tracks=1)
        candidate = deepcopy(objective.reference_tracks)
        candidate['frequency_hz'][:,0] += np.where(np.arange(len(candidate['times']))%2,90.,-90.)
        # Inject the same measured peak path with either continuous IDs or
        # fragmented IDs. Matching/trajectory scoring must measure the same
        # movement; fragmenting IDs additionally incurs a continuity penalty.
        objective.extract = lambda ignored:candidate
        continuous = objective.evaluate(source)
        candidate['track_id'][:,0] = np.arange(len(candidate['times']))+1000
        fragmented = objective.evaluate(source)
        self.assertGreater(continuous['frequency_trajectory_error'],1.)
        self.assertAlmostEqual(fragmented['frequency_trajectory_error'],continuous['frequency_trajectory_error'])
        self.assertGreater(fragmented['continuity_break_rate'],.9)
        self.assertGreater(fragmented['harmonic_track_loss'],continuous['harmonic_track_loss'])


if __name__ == '__main__':
    unittest.main()

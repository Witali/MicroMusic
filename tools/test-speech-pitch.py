"""Check voice-prior selection against short resonant attacks, without labels."""
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
from speech_pitch import track_speech_pitch
from period_wave import encode_model,decode_model,refine_frames
from auto_encoder import SpectralObjective


class SpeechPitchTest(unittest.TestCase):
    def test_persistent_voice_establishes_prior_despite_high_resonant_attacks(self):
        sr=7500;t=np.arange(sr*2)/sr
        voice=.13*np.sin(2*np.pi*125*t)+.08*np.sin(2*np.pi*250*t)
        voice*=.7+.3*np.sin(2*np.pi*3*t)**2
        for start in (.25,.8,1.4):
            local=t-start;active=(local>=0)&(local<.035)
            voice[active]+=.8*np.exp(-local[active]/.007)*np.sin(2*np.pi*780*local[active])
        _,f0,_,report=track_speech_pitch(voice)
        self.assertLess(abs(report['prior_hz']-125),2)
        self.assertLess(abs(np.median(f0[f0>0])-125),2)
        self.assertGreater(np.count_nonzero(f0),len(f0)*.7)

    def test_higher_voice_is_not_forced_into_a_fixed_male_pitch_range(self):
        t=np.arange(7500)/7500
        _,f0,_,report=track_speech_pitch(.2*np.sin(2*np.pi*310*t))
        self.assertLess(abs(report['prior_hz']-310),3)
        self.assertLess(abs(np.median(f0[f0>0])-310),3)

    def test_isolated_impulses_do_not_define_a_voice_prior(self):
        audio=np.zeros(7500);audio[::1500]=1
        _,f0,_,report=track_speech_pitch(audio)
        self.assertIsNone(report['prior_hz'])
        self.assertTrue(np.all(f0==0))

    def test_periodic_voice_onsets_are_protected_from_transient_rejection(self):
        sr=7500;t=np.arange(sr*2)/sr
        envelope=np.where((t % .4)<.2,.04,.25)
        audio=envelope*np.sin(2*np.pi*125*t)
        _,f0,_,report=track_speech_pitch(audio)
        self.assertGreater(np.count_nonzero(f0),len(f0)*.9)
        self.assertGreater(np.count_nonzero(report['protected_voiced_onsets']),0)

    def test_local_pitch_can_follow_a_smooth_voice_glide(self):
        sr=7500;t=np.arange(sr*2)/sr;frequency=125+12.5*t
        audio=.2*np.sin(2*np.pi*np.cumsum(frequency)/sr)
        centres,f0,_,report=track_speech_pitch(audio)
        accepted=f0>0
        target=125+12.5*centres/sr
        self.assertGreater(np.count_nonzero(accepted),len(f0)*.9)
        self.assertLess(np.median(abs(f0[accepted]-target[accepted])),2)
        self.assertTrue(all(run['duration_ms']>=80 for run in report['prior_runs'] if run['accepted']))

    def test_encoder_uses_the_voice_mask_for_phase_fitting_and_dictionary_training(self):
        sr=7500;t=np.arange(sr*2)/sr
        audio=.13*np.sin(2*np.pi*125*t)+.08*np.sin(2*np.pi*250*t)
        for start in (.25,.8,1.4):
            local=t-start;active=(local>=0)&(local<.035)
            audio[active]+=.8*np.exp(-local[active]/.007)*np.sin(2*np.pi*780*local[active])
        model,analysis=encode_model(audio,starts=2,pitch_mode='voice-priority')
        mask=analysis['pitch_analysis']
        self.assertEqual(len(decode_model(model)),len(audio))
        np.testing.assert_array_equal(np.asarray(model['frames'])[:,3],analysis['voice_mask'])
        self.assertFalse(np.any(analysis['book_mask']&np.asarray(mask['attack_frames'])))
        self.assertGreater(np.count_nonzero(analysis['book_mask']),len(model['frames'])*.65)
        self.assertLess(abs(np.median(analysis['f0'][analysis['voice_mask']])-125),2)
        refined,_=refine_frames(model,SpectralObjective(audio,sr),proposals=40,
                                 voiced_mask=analysis['voice_mask'])
        self.assertFalse(np.any((np.asarray(refined['frames'])[:,3]>0)&~analysis['voice_mask']))

    def test_pure_voice_keeps_its_trajectory_and_complete_duration(self):
        sr=7500;t=np.arange(sr)/sr;audio=.2*np.sin(2*np.pi*210*t)
        _,legacy=encode_model(audio,starts=2)
        model,robust=encode_model(audio,starts=2,pitch_mode='voice-priority')
        common=legacy['voice_mask']&robust['voice_mask']
        self.assertGreater(np.count_nonzero(common),len(model['frames'])*.9)
        np.testing.assert_allclose(legacy['f0'][common],robust['f0'][common],atol=1e-9)
        self.assertEqual(model['samples'],len(audio))


if __name__=='__main__':unittest.main()

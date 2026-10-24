"""Measure physical pulse-book compaction separately from lossy merges."""
import importlib.util
from pathlib import Path
import sys
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('mixed_prune_contracts',ROOT/'tools/prune-mixed-pulses.py')
probe=importlib.util.module_from_spec(spec);sys.modules[spec.name]=probe;spec.loader.exec_module(probe)


class MixedPruneTests(unittest.TestCase):
    def test_sparse_modes_compact_without_changing_voice_noise_phase_or_filter_states(self):
        path=ROOT/'ATtiny13A/Sound/research/q4-pulse-shapes/voice-search/model.json'
        for policy in ('literal','balance16'):
            state,bits,state_bits,mode,*_=probe.fit.load(path,tail_policy=policy)
            state.modes=np.where(state.modes%2,7,3).astype(np.int16);before=state.fields()
            result=probe.compact(state,bits,state_bits,mode)
            self.assertEqual(probe.active(result).tolist(),[0,1]);self.assertEqual(before,state.fields())
            old,counts=probe.fit.render(state,bits,state_bits,mode);new,new_counts=probe.fit.render(result,bits,state_bits,mode)
            np.testing.assert_array_equal(old,new);np.testing.assert_array_equal(counts,new_counts)
            probe.fit.validate(result,bits,state_bits,policy=='balance16')

    def test_literal_four_form_q1_capacity_and_q2_overflow_are_counted_separately(self):
        path=ROOT/'ATtiny13A/Sound/research/q4-pulse-shapes/wide32-zero/model.json'
        state,*_=probe.fit.load(path);state.modes%=4
        self.assertEqual(probe.storage(state),dict(forms=4,packed_waveform_bytes=64,area_descriptor_bytes=0,waveforms_fit_eeprom=True))
        state.wave_fraction_bits=2;state.waves_q1*=2
        self.assertFalse(probe.storage(state)['waveforms_fit_eeprom']);self.assertEqual(probe.storage(state)['packed_waveform_bytes'],80)


if __name__=='__main__':unittest.main()

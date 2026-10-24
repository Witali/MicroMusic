"""Quarter-period carry patterns, exact half controls and explicit wire format."""
import hashlib
import importlib.util
from pathlib import Path
import sys
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('q4_quarter_contracts',ROOT/'tools/refine-q4-quarter.py')
fit=importlib.util.module_from_spec(spec);sys.modules[spec.name]=fit;spec.loader.exec_module(fit)


class QuarterTests(unittest.TestCase):
    def test_even_quarters_reproduce_complete_selected_teacher_pcm(self):
        path=ROOT/'ATtiny13A/Sound/research/q4-lattice/followups/nearest/model.json'
        state,meta=fit.load(path);pcm,counts=fit.render(state,meta['state_bits'],meta['nearest'])
        self.assertFalse(np.any(counts))
        self.assertEqual(hashlib.sha256(pcm.tobytes()).hexdigest(),
            'e0cce5d036ea32253cceea7915fbba2b52de5317d3318f9f3ebec633651ad440')
        control=fit.base.load(path);expected,old_counts=fit.base.render(control,meta['state_bits'],meta['nearest'])
        np.testing.assert_array_equal(pcm,expected);np.testing.assert_array_equal(counts,old_counts)

    def test_fast_reload_patterns_cover_all_quarters_without_carry_drift(self):
        p=np.array([1],np.int16);g=np.array([1],np.int16);d=np.array([256],np.int16)
        modes=np.array([0],np.int16);waves=np.zeros((8,16),np.int16);waves[0,0]=1
        patterns={0:[1],1:[2,1,1,1],2:[2,1],3:[2,2,2,1]}
        for quarter,pattern in patterns.items():
            rows,excitation=fit.base.codec.legacy_excitation(p,g,d,modes,waves,np.array([quarter],np.int16),pitch_bits=2)
            peaks=np.flatnonzero(excitation[:250]);differences=np.diff(peaks)
            np.testing.assert_array_equal(differences,np.resize(pattern,len(differences)))

    def test_explicit_quarter_header_and_legacy_even_bytes_round_trip(self):
        p=np.array([40,63,64,126,0],np.int16);g=np.array([2,16,30,15,0],np.int16)
        d=np.array([64,128,192,256,64],np.int16);k=np.zeros((5,8),np.int16)
        m=np.array([0,3,4,7,0],np.int16);old=np.array([0,1,1,0,0],np.int16)
        old_data=fit.stream.pack(p,g,d,k,m,old)
        self.assertEqual(old_data,fit.stream.pack(p,g,d,k,m,old*2,pitch_bits=2))
        quarter=np.array([1,2,3,0,0],np.int16);values=(p,g,d,k,m,quarter)
        payload=fit.stream.pack(*values,pitch_bits=2)
        self.assertTrue(payload[0]&16)
        for expected,actual in zip(values,fit.stream.unpack(payload,pitch_bits=2)):
            np.testing.assert_array_equal(expected,actual)
        with self.assertRaises(ValueError):fit.stream.unpack(payload)
        bad=quarter.copy();bad[-1]=1
        with self.assertRaises(ValueError):fit.stream.pack(p,g,d,k,m,bad,pitch_bits=2)

    def test_mutations_use_quarter_units_and_do_not_reinterpret_invalid_flags(self):
        state,_=fit.load(ROOT/'ATtiny13A/Sound/research/q4-lattice/followups/nearest/model.json')
        state.pitches[0]=40;state.halves[0]=1
        changed=fit.apply(state,('pitch',0,0,1))
        self.assertEqual((int(changed.pitches[0]),int(changed.halves[0])),(40,2))
        self.assertEqual(int(state.halves[0]),1)
        for flags in (np.full(len(state.pitches),4),np.full(len(state.pitches),.5)):
            bad=state.copy();bad.halves=flags
            with self.assertRaises(ValueError):fit.validate(bad)

    def test_continuous_period_survives_frames_shorter_than_one_cycle(self):
        p=np.full(8,90,np.int16);g=np.ones(8,np.int16);d=np.full(8,64,np.int16)
        m=np.zeros(8,np.int16);h=np.zeros(8,np.int16);b=np.zeros((8,16),np.int16);b[0,0]=1
        _,reset=fit.base.codec.legacy_excitation(p,g,d,m,b,h,pitch_bits=2)
        self.assertFalse(np.any(reset))
        for mode,first in ((1,89),(2,0)):
            _,signal=fit.base.codec.legacy_excitation(p,g,d,m,b,h,pitch_bits=2,phase_mode=mode)
            peaks=np.flatnonzero(signal);self.assertEqual(int(peaks[0]),first)
            np.testing.assert_array_equal(np.diff(peaks),np.full(len(peaks)-1,90))
        p[:]=1;h[:]=1
        _,signal=fit.base.codec.legacy_excitation(p,g,d,m,b,h,pitch_bits=2,phase_mode=1)
        peaks=np.flatnonzero(signal)
        np.testing.assert_array_equal(np.diff(peaks),np.resize([2,1,1,1],len(peaks)-1))
        p=np.ones(2,np.int16);g=np.ones(2,np.int16);d=np.full(2,64,np.int16)
        m=np.zeros(2,np.int16);h=np.array([1,0],np.int16)
        rows,signal=fit.base.codec.legacy_excitation(p,g,d,m,b,h,phase_mode=1)
        peaks=np.flatnonzero((signal!=0)&(rows==1))
        np.testing.assert_array_equal(np.diff(peaks),np.ones(len(peaks)-1,np.int64))


if __name__=='__main__':unittest.main()

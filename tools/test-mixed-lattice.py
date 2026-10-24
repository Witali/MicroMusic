"""Precision promotion, order-neutral zero stages and bounded zero-area pulses."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest
import tempfile
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('mixed_lattice_contracts',ROOT/'tools/fit-mixed-lattice.py')
fit=importlib.util.module_from_spec(spec);sys.modules[spec.name]=fit;spec.loader.exec_module(fit)


class MixedLatticeTests(unittest.TestCase):
    def test_frame_phase_training_starts_exact_and_keeps_the_input_immutable(self):
        path=ROOT/'ATtiny13A/Sound/research/q4-pattern-precision/mixed/q8/best-intelligibility-model.json'
        state,bits,state_bits,mode,_,_,_=fit.load(path,pulse_length=32,fit_phase=True)
        self.assertFalse(np.any(state.phase_modes))
        pcm,counts=fit.render(state,bits,state_bits,mode)
        self.assertFalse(np.any(counts));self.assertEqual(hashlib.sha256(pcm.tobytes()).hexdigest(),
            '4cc6676f5a91995be4189f65ae08745b68cacd254732de7c5e4c4ee3e416058e')
        before=state.fields();changed=fit.apply(state,('phase',0,0,3),bits)
        self.assertEqual(state.fields(),before);self.assertEqual(int(changed.phase_modes[0]),3)
        fit.validate(changed,bits,state_bits)
        changed.phase_modes[0]=4
        with self.assertRaises(ValueError):fit.validate(changed,bits,state_bits)

    def test_zero_padding_a_full_pulse_teacher_preserves_all_pcm(self):
        path=ROOT/'ATtiny13A/Sound/research/q4-pattern-precision/mixed/q8/best-intelligibility-model.json'
        state,bits,state_bits,mode,_,_,_=fit.load(path,pulse_length=32)
        self.assertEqual(state.waves_q1.shape,(8,32));self.assertFalse(np.any(state.waves_q1[:,16:]))
        pcm,counts=fit.render(state,bits,state_bits,mode)
        self.assertFalse(np.any(counts))
        self.assertEqual(hashlib.sha256(pcm.tobytes()).hexdigest(),
            '4cc6676f5a91995be4189f65ae08745b68cacd254732de7c5e4c4ee3e416058e')

    def test_extended_taps_are_read_but_never_cross_a_short_pitch_cycle(self):
        p=np.full(4,64,np.int16);g=np.full(4,2,np.int16);d=np.full(4,128,np.int16)
        modes=np.zeros(4,np.int16);q=modes.copy();waves=np.zeros((8,32),np.int16);waves[0,31]=4
        _,old=fit.phase.legacy_excitation(p,g,d,modes,waves,q,pitch_bits=2)
        _,wide=fit.phase.legacy_excitation(p,g,d,modes,waves,q,pitch_bits=2,pulse_width=32)
        self.assertFalse(np.any(old));self.assertEqual(int(wide[94]),8)
        _,short=fit.phase.legacy_excitation(np.full(4,20,np.int16),g,d,modes,waves,q,pitch_bits=2,pulse_width=32)
        self.assertFalse(np.any(short))

    def test_long_pulse_schema_zero_area_and_truncation_are_explicit(self):
        path=ROOT/'ATtiny13A/Sound/research/q4-pattern-precision/mixed/q8/model.json'
        old=json.loads(path.read_text());state,bits,state_bits,_,_,_,_=fit.load(path,pulse_length=32)
        state.waves_q1=fit.zero_area(state.waves_q1)
        fit.validate(state,bits,state_bits,True);self.assertFalse(np.any(state.waves_q1.sum(axis=1)))
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
            target=Path(folder)/'model.json'
            meta=dict(old,schema=fit.codec.PULSE_SCHEMA,pulse_length=32,**state.fields())
            fit.base.save(target,meta);fit.load(target)
            state.waves_q1[0,31]=1
            fit.base.save(target,dict(meta,**state.fields()))
            with self.assertRaises(ValueError):fit.load(target,pulse_length=16)
            fit.base.save(target,dict(meta,schema=fit.codec.SCHEMA))
            with self.assertRaises(ValueError):fit.load(target)

    def test_promoting_q4_to_q7_preserves_every_boundary_product(self):
        values=[-32768,-32767,-4096,-129,-128,-127,-17,-16,-15,-1,0,1,15,16,17,127,128,4095,32767]
        for value in values:
            for coefficient in range(-15,16):
                for nearest in (False,True):
                    expected=fit.phase.state_multiply(value,coefficient,4,nearest)
                    self.assertEqual(fit.codec.multiply(value,coefficient*8,7,4,nearest),expected)

    def test_full_teacher_pcm_survives_head_promotion_and_extra_zero_stages(self):
        path=ROOT/'ATtiny13A/Sound/research/q4-lattice/followups/nearest/model.json'
        for order,profile in ((8,'head7'),(10,'all7')):
            state,bits,state_bits,mode,_,_,_=fit.load(path,order,profile,4)
            pcm,counts=fit.render(state,bits,state_bits,mode)
            self.assertFalse(np.any(counts))
            self.assertEqual(hashlib.sha256(pcm.tobytes()).hexdigest(),
                'e0cce5d036ea32253cceea7915fbba2b52de5317d3318f9f3ebec633651ad440')

    def test_zero_area_projection_and_paired_mutations_keep_the_pulse_constraint(self):
        original=np.random.default_rng(1027).integers(-7,8,(8,16),dtype=np.int16);snapshot=original.copy()
        projected=fit.zero_area(original)
        np.testing.assert_array_equal(original,snapshot);np.testing.assert_array_equal(projected.sum(axis=1),np.zeros(8))
        self.assertLessEqual(int(abs(projected).max()),7)
        state,bits,state_bits,_,_,_,_=fit.load(ROOT/'ATtiny13A/Sound/research/q4-lattice/followups/nearest/model.json',8,'head7',6)
        state.waves_q1[:]=0;changed=fit.apply(state,('wave',0,1,1,6),bits)
        self.assertIsNotNone(changed);fit.validate(changed,bits,state_bits,True)
        self.assertEqual((int(changed.waves_q1[0,1]),int(changed.waves_q1[0,6])),(1,-1))
        self.assertFalse(np.any(state.waves_q1))

    def test_unsigned_precision_arrays_do_not_overflow_the_stability_bound(self):
        k=np.zeros((1,6),np.int16);bits=np.full(6,7,np.uint8)
        fit.codec.validate(k,bits,6)
        for value in (-128,128):
            changed=k.copy();changed[0,0]=value
            with self.assertRaises(ValueError):fit.codec.validate(changed,bits,6)


if __name__=='__main__':unittest.main()

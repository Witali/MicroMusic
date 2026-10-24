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
    def test_balanced_tail_covers_every_possible_area_and_preserves_precision_promotion(self):
        for fraction_bits in (1,2):
            limit=7<<(fraction_bits-1)
            for area in range(-16*limit,16*limit+1):
                # Build each head independently, without relying on the tail generator.
                remaining=abs(area);head=np.zeros((8,16),np.int16)
                for i in range(16):
                    head[:,i]=(-1 if area<0 else 1)*min(limit,remaining);remaining-=abs(int(head[0,i]))
                result=fit.codec.balanced_pulses(head,fraction_bits)
                np.testing.assert_array_equal(result[:,:16],head)
                self.assertFalse(np.any(result.sum(axis=1)));self.assertLessEqual(int(abs(result).max()),limit)
                np.testing.assert_array_equal(fit.codec.balanced_pulses(-head,fraction_bits),-result)
                if fraction_bits==1:
                    np.testing.assert_array_equal(fit.codec.balanced_pulses(head*2,2),result*2)
        head=np.zeros((8,16),np.int16);head[:,0]=7
        expected=np.zeros((8,32),np.int16);expected[:,0]=7;expected[:,25:]=-1
        np.testing.assert_array_equal(fit.codec.balanced_pulses(head),expected)

    def test_balanced_head_storage_is_64_eeprom_bytes_and_rejects_corrupt_descriptors(self):
        head=np.random.default_rng(294).integers(-7,8,(8,16),dtype=np.int16)
        packed,areas=fit.codec.pack_balanced_heads(head)
        self.assertEqual((len(packed),len(areas)),(64,8))
        np.testing.assert_array_equal(fit.codec.unpack_balanced_heads(packed,areas),fit.codec.balanced_pulses(head))
        packed,areas=fit.codec.pack_balanced_heads(np.full((8,16),-7,np.int16))
        self.assertEqual(packed,bytes([0x99])*64);self.assertEqual(areas,bytes([112])*8)
        with self.assertRaises(ValueError):fit.codec.unpack_balanced_heads(packed,bytes(8))
        with self.assertRaises(ValueError):fit.codec.unpack_balanced_heads(bytes([0x88])*64,areas)

    def test_balanced_schema_and_mutations_keep_generated_tails_derived_from_heads(self):
        path=ROOT/'ATtiny13A/Sound/research/q4-pulse-shapes/wide32-zero/model.json'
        state,bits,state_bits,mode,_,zero,meta=fit.load(path,tail_policy='balance16')
        self.assertTrue(zero);fit.validate(state,bits,state_bits,True);before=state.fields()
        proposals=[a for a in fit.actions(state,bits,True) if a[0]=='wave']
        self.assertTrue(proposals);self.assertTrue(all(a[2]<16 and a[4]==-1 for a in proposals))
        for action in proposals:
            changed=fit.apply(state,action,bits)
            if changed is not None:fit.validate(changed,bits,state_bits,True)
        self.assertEqual(state.fields(),before)
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
            target=Path(folder)/'model.json';saved=dict(meta,schema=fit.codec.BALANCED_SCHEMA,pulse_length=32,**state.fields())
            saved.pop('waves_q1',None);fit.base.save(target,saved)
            restored=fit.load(target)[0];np.testing.assert_array_equal(restored.waves_q1,state.waves_q1)
            promoted=fit.load(target,wave_fraction_bits=2)[0]
            np.testing.assert_array_equal(promoted.waves_q1,state.waves_q1*2)
            np.testing.assert_array_equal(fit.render(state,bits,state_bits,mode)[0],fit.render(promoted,bits,state_bits,mode)[0])
            with self.assertRaises(ValueError):fit.load(target,pulse_length=16)
            fit.base.save(target,dict(saved,schema=fit.codec.PULSE_SCHEMA))
            with self.assertRaises(ValueError):fit.load(target)

    def test_reference_step_policy_derives_its_bound_from_the_original(self):
        import soundfile as sf
        x,sr=sf.read(ROOT/'web-player/audio/originals/vinni.wav')
        self.assertEqual(sr,7500);self.assertEqual(fit.step_bound(x,'legacy'),47)
        self.assertEqual(fit.step_bound(x,'reference'),73)
        self.assertEqual(fit.step_bound(np.array([-1.,1.]),'reference'),255)
        with self.assertRaises(ValueError):fit.step_bound(x,'unknown')

    def test_voice_proposals_can_fix_classification_and_octaves_without_mutating_the_seed(self):
        state=fit.State(np.array([0,40]),np.array([4,5]),np.array([128,128]),np.zeros((2,8),np.int16),
            np.array([0,1]),np.zeros((8,16),np.int16),np.zeros(2,np.int16),np.zeros(2,np.int16))
        bits=np.full(8,4,np.int16);before=state.fields()
        proposals=[a for a in fit.actions(state,bits,False,np.array([200,160])) if a[0]=='voice']
        self.assertTrue(any(a[1]==0 and a[2]>0 and a[5]==3 for a in proposals))
        self.assertTrue(any(a[1]==1 and a[2]==0 for a in proposals))
        self.assertTrue(any(a[1]==1 and a[2]==320 for a in proposals))
        for action in proposals:
            changed=fit.apply(state,action,bits);fit.validate(changed,bits,6)
        self.assertEqual(state.fields(),before)

    def test_wave_precision_promotion_preserves_voice_noise_and_complete_pcm(self):
        path=ROOT/'ATtiny13A/Sound/research/q4-pattern-precision/mixed/q8/best-intelligibility-model.json'
        for width in (16,32):
            state,bits,state_bits,mode,_,_,meta=fit.load(path,pulse_length=width,wave_fraction_bits=2)
            self.assertEqual(state.wave_fraction_bits,2)
            pcm,counts=fit.render(state,bits,state_bits,mode)
            self.assertFalse(np.any(counts));self.assertEqual(hashlib.sha256(pcm.tobytes()).hexdigest(),
                '4cc6676f5a91995be4189f65ae08745b68cacd254732de7c5e4c4ee3e416058e')
            with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
                target=Path(folder)/'model.json'
                saved={k:v for k,v in meta.items() if k!='waves_q1'}
                fit.base.save(target,dict(saved,schema=fit.codec.PULSE_SCHEMA,pulse_length=width,**state.fields()))
                restored=fit.load(target)[0];np.testing.assert_array_equal(restored.waves_q1,state.waves_q1)
                state.waves_q1[0,0]|=1
                fit.base.save(target,dict(saved,schema=fit.codec.PULSE_SCHEMA,pulse_length=width,**state.fields()))
                with self.assertRaises(ValueError):fit.load(target,wave_fraction_bits=1)

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

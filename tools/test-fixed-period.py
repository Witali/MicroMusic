"""Integer format contracts: quantization, bounds, clocks and PCM roundtrips."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from fixed_period import decode_fixed, pack_fixed, unpack_fixed, pack_avr_data, avr_features, validate


def model(samples=193):
    rng = np.random.default_rng(4728)
    return dict(schema='period-fixed-v1', sample_rate=7500, hop=64, samples=samples,
                phase_bits=4, initial_phase_u16=56231, noise_seed_u16=0xace1,
                codebook=rng.integers(-7, 8, (16,32)).tolist(),
                noise_filters=[[0,0,0,0,1,1,3,7], [0,0,0,0,0,-1,-1,7], [0,0,0,-1,0,1,3,7]],
                frames=[[126, 0x91, 3], [127, 0xe2, 18], [122, 0, 0], [255, 0xf3, 33]][:(samples+63)//64])


class FixedPeriodTest(unittest.TestCase):
    def test_portable_roundtrip_preserves_target_pcm_and_canonical_padding(self):
        for bits in (4,5,6):
            for dc in (0,5,6,7):
                source = model()
                source.update(phase_bits=bits, dc_block_shift=dc)
                before = deepcopy(source)
                packed = pack_fixed(source)
                recovered = unpack_fixed(packed)
                np.testing.assert_array_equal(decode_fixed(source), decode_fixed(recovered))
                self.assertEqual(packed, pack_fixed(recovered))
                self.assertEqual(source, before)

    def test_avr_bias_is_lossless_and_only_changes_wave_table_representation(self):
        source = model()
        payload = pack_avr_data(source)
        nibbles = np.column_stack((np.frombuffer(payload[:256], np.uint8)&15,
                                   np.frombuffer(payload[:256], np.uint8)>>4)).ravel()
        np.testing.assert_array_equal(nibbles.astype(int)-8, np.asarray(source['codebook']).ravel())
        self.assertEqual(len(payload), len(pack_fixed(source))-12+12)

    def test_fractional_fade_uses_frame_centers_and_pitch_uses_block_starts(self):
        source = model(128)
        source['codebook'] = [[-7]*32, [7]*32]+[[0]*32 for _ in range(14)]
        source['frames'] = [[80, 0xf0, 0], [160, 0xf1, 0]]
        pcm = decode_fixed(source).astype(int)-128
        self.assertTrue(np.all(pcm[:33] == -112))
        self.assertEqual(pcm[64], 0)
        self.assertTrue(np.all(pcm[96:] == 112))
        self.assertTrue(np.all(np.diff(pcm[32:97]) >= 0))

    def test_rejects_payload_damage_and_unsafe_fir_accumulator(self):
        packed = pack_fixed(model())
        for broken in (b'XX'+packed[2:], packed[:279], packed[:-2], packed+b'\x00',
                       packed[:11]+b'\x08'+packed[12:]):
            with self.assertRaises(ValueError):
                unpack_fixed(broken)
        source = model()
        source['noise_filters'][0] = [7]*8
        with self.assertRaises(ValueError):
            validate(source)

    def test_silence_is_exact_unsigned_midpoint_with_or_without_dc(self):
        source = model()
        source['frames'] = [[100,0,0] for _ in source['frames']]
        for dc in (0,5,6,7):
            source['dc_block_shift'] = dc
            self.assertTrue(np.all(decode_fixed(source) == 128))

    def test_compile_features_follow_active_modes_and_identical_filters(self):
        source = model()
        self.assertEqual(avr_features(source)['FIR_BYTES'], 24)
        source['noise_filters'] = [source['noise_filters'][0]]*3
        self.assertEqual(avr_features(source)['FIR_BYTES'], 8)
        unused = 256-avr_features(source)['WAVE_BYTES']
        self.assertEqual(len(pack_avr_data(source))-len(pack_avr_data(source,specialize=True)),16+unused)
        source['frames'] = [[p, h|128, r&15] for p,h,r in source['frames']]
        flags = avr_features(source)
        self.assertEqual((flags['ENABLE_UNVOICED'],flags['ENABLE_FIR'],flags['HISTORY_LENGTH']),(0,0,2))
        self.assertEqual(len(pack_avr_data(source))-len(pack_avr_data(source,specialize=True)),24+unused)


if __name__ == '__main__':
    unittest.main()

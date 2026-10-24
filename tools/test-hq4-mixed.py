"""Exact off-case and reproducible signed-eight-bit mixed excitation."""
from pathlib import Path
import sys
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
from hq4_mixed import decode,pack_mix,unpack_mix
from hq4_core import unpack_stream
from model import decode as baseline


class MixedHQ4Tests(unittest.TestCase):
    def test_all_zero_mix_is_bitexact_for_every_frozen_phrase(self):
        for name in ('chego','otvechaesh','vinni'):
            f,d=unpack_stream((ROOT/'ATtiny13A/Sound/codec/release'/name/'speech.hq').read_bytes())
            for keep_phase in (0,1):
                np.testing.assert_array_equal(decode(f,d,np.zeros(len(f),np.uint8),keep_phase=keep_phase),
                                              baseline(f,d,keep_phase))

    def test_disabled_mixing_and_zero_gain_preserve_state_exactly(self):
        f=np.asarray([[45,7,136,136,136,136],[0,9,136,136,136,136],
                      [50,0,136,136,136,136],[0,7,136,136,136,136]],np.uint8)
        d=np.full(4,256,np.uint16)
        np.testing.assert_array_equal(decode(f,d,np.full(4,3,np.uint8),enabled=False),baseline(f,d,0))
        # Only an unvoiced frame and a zero-gain voiced frame have mix flags.
        # Neither may advance the original LFSR beyond its baseline schedule.
        np.testing.assert_array_equal(decode(f,d,np.asarray([0,3,3,3],np.uint8)),baseline(f,d,0))

    def test_nonzero_mix_is_deterministic_and_keeps_duration(self):
        f=np.asarray([[45,7,136,136,136,136],[0,9,136,136,136,136]],np.uint8)
        d=np.full(2,256,np.uint16);m=np.asarray([2,0],np.uint8)
        a,b=decode(f,d,m),decode(f,d,m)
        np.testing.assert_array_equal(a,b)
        self.assertEqual(len(a),512)
        self.assertEqual(a.dtype,np.uint8)
        self.assertGreater(np.count_nonzero(a!=baseline(f,d,0)),100)

    def test_two_bit_map_roundtrip_and_padding(self):
        for count in range(1,20):
            codes=np.asarray([i%4 for i in range(count)],np.uint8)
            payload=pack_mix(codes)
            self.assertEqual(len(payload),(count+3)//4)
            np.testing.assert_array_equal(unpack_mix(payload,count),codes)
        with self.assertRaises(ValueError):unpack_mix(bytes([255]),1)
        with self.assertRaises(ValueError):pack_mix(np.asarray([4]))
        with self.assertRaises(ValueError):pack_mix(np.asarray([-1]))
        with self.assertRaises(ValueError):pack_mix(np.asarray([1.5]))

    def test_invalid_frame_and_map_are_rejected(self):
        f=np.asarray([[45,7,136,136,136,136]],np.uint8)
        d=np.asarray([256],np.uint16)
        for bad in ([],[0,0],[4],[-1],[1.2]):
            with self.assertRaises(ValueError):decode(f,d,np.asarray(bad))
        with self.assertRaises(ValueError):decode(f,np.asarray([255]),np.asarray([0]))


if __name__=='__main__':unittest.main()

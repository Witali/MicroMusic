"""EEPROM packing must preserve actual target output, not just parameters."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
from fixed_period import decode_fixed
from tiny_period import pack_tiny, unpack_tiny


def fixture(words=8):
    rng=np.random.default_rng(6095)
    pitches=[128,128,129,128,130,128,131,128,132,128,133,128,134,0,255,128]
    frames=[[p,128|((i%7+1)<<4)|(i%words),i%16] for i,p in enumerate(pitches)]
    frames[3][1]=0
    return dict(schema='period-fixed-v1',sample_rate=7500,samples=len(frames)*64,hop=64,
                phase_bits=4,dc_block_shift=7,initial_phase_u16=56231,noise_seed_u16=0xace1,
                frames=frames,codebook=rng.integers(-7,8,(16,32)).tolist(),noise_filters=[[0]*8]*3)


class TinyPeriodTest(unittest.TestCase):
    def test_all_pitch_prefixes_and_eeprom_splits_preserve_integer_pcm(self):
        for words in (1,2,4,5,8,10,12,16):
            source=fixture(words)
            packed=pack_tiny(source)
            restored=unpack_tiny(packed)
            np.testing.assert_array_equal(decode_fixed(source),decode_fixed(restored))
            self.assertEqual(packed,pack_tiny(restored))
            self.assertEqual(len(packed['eeprom']),64)
            self.assertEqual(packed['constants']['EEPROM_USED_BYTES'],min(64,words*16))

    def test_rejects_modes_that_tiny_assembly_cannot_play(self):
        for mutation in ('unvoiced','colored','precision','dc','duration'):
            source=fixture()
            if mutation=='unvoiced':source['frames'][0][1]&=127
            if mutation=='colored':source['frames'][1][2]=17
            if mutation=='precision':source['phase_bits']=5
            if mutation=='dc':source['dc_block_shift']=0
            if mutation=='duration':source['samples']-=1
            with self.assertRaises(ValueError):pack_tiny(source)

    def test_eeprom_constants_affect_the_decoded_voice(self):
        source=fixture()
        packed=pack_tiny(source)
        changed=deepcopy(packed)
        changed['eeprom']=b'\x88'*64
        self.assertFalse(np.array_equal(decode_fixed(source),decode_fixed(unpack_tiny(changed))))
        self.assertEqual(packed['flash_data'],changed['flash_data'])

    def test_rejects_truncation_extra_bits_and_inconsistent_layout(self):
        packed=pack_tiny(fixture())
        for kind in ('truncated','extra','layout','eeprom'):
            broken=deepcopy(packed)
            if kind=='truncated':broken['flash_data']=broken['flash_data'][:-2]
            if kind=='extra':broken['flash_data']+=b'\x00'
            if kind=='layout':broken['constants']['EEPROM_WAVE_SPLIT']+=1
            if kind=='eeprom':broken['eeprom']=broken['eeprom'][:-1]
            with self.assertRaises(ValueError):unpack_tiny(broken)


if __name__=='__main__':unittest.main()

#!/usr/bin/env python3
"""Container completeness, faithful original kernels and explicit LPX4 profiles."""
import struct
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
from lpc2_excitation import encode_excitation,decode_excitation,inspect_container,legacy,HEADER


class Lpc2ExcitationTests(unittest.TestCase):
    def setUp(self):
        self.sr,self.samples,self.pre = 7500,3073,.85
        # Synthetic zero-order predictor provider isolates the bitstream and
        # closed-loop contracts. Real LPC2 base/JS agreement is checked by the
        # actual probe, independently through the original Node decoder.
        base=bytearray(36)
        base[:4]=b'LPC2';base[4]=2;base[5]=10
        struct.pack_into('<H',base,6,self.sr)
        struct.pack_into('<I',base,16,self.samples)
        struct.pack_into('<f',base,24,self.pre)
        self.base=bytes(base)
        self.cache=(self.pre,self.sr,np.zeros((self.samples,10),dtype=float))
        self.reference=.2*np.sin(2*np.pi*330*np.arange(self.samples)/self.sr)
        self.requests=[]
        def provider(base):
            self.assertEqual(base,self.base)
            self.requests.append(base)
            return self.cache
        self.provider=provider

    def test_original_234_bitstreams_are_exactly_preserved(self):
        for bits in (2,3,4):
            data,audio,info=encode_excitation(self.reference,self.sr,self.base,bits,self.provider)
            original,expected,_=legacy.encode_lpx3(self.reference,self.sr,self.base,bits,
                block_size=75,cache=self.cache,auto_brightness=False)
            self.assertEqual(data,original)
            self.assertTrue(np.array_equal(audio,expected))
            self.assertEqual(info['format'],'LPX3')
            self.assertEqual(info['brightness'],0)

    def test_parameter_only_roundtrip_and_complete_byte_accounting(self):
        data,audio,info=encode_excitation(self.reference,self.sr,self.base,3,self.provider)
        decoded,meta=decode_excitation(data,self.provider)
        self.assertTrue(np.array_equal(audio,decoded))
        self.assertEqual(len(decoded),self.samples)
        self.assertEqual(len(data),meta['header_bytes']+meta['base_bytes']+meta['scale_bytes']+meta['excitation_bytes'])
        self.assertEqual(meta['header_bytes'],24)
        self.assertEqual(meta['block_samples'],75)
        self.assertTrue(self.requests)

    def test_truncation_extra_bytes_and_label_confusion_rejected(self):
        data,_,_=encode_excitation(self.reference,self.sr,self.base,4,self.provider)
        for invalid in (data[:-1],data+b'\0'):
            with self.assertRaises(ValueError):inspect_container(invalid)
        invalid=bytearray(data);invalid[5]=8
        with self.assertRaises(ValueError):inspect_container(bytes(invalid))
        invalid=bytearray(data);invalid[:4]=b'LPX4'
        with self.assertRaises(ValueError):inspect_container(bytes(invalid))
        invalid=bytearray(data);invalid[-1]|=0x80
        with self.assertRaises(ValueError):inspect_container(bytes(invalid))

    def test_extended_68_profiles_are_explicit_and_do_not_amplify_quiet_source(self):
        quiet=self.reference*.01
        for bits in (6,8):
            data,audio,info=encode_excitation(quiet,self.sr,self.base,bits,self.provider)
            decoded,meta=decode_excitation(data,self.provider)
            self.assertEqual(data[:4],b'LPX4')
            self.assertEqual(meta['bits_per_sample'],bits)
            self.assertTrue(np.array_equal(audio,decoded))
            self.assertEqual(len(decoded),len(quiet))
            ratio=np.sqrt(np.mean(decoded.astype(float)**2)/np.mean(quiet**2))
            self.assertGreater(ratio,.8);self.assertLess(ratio,1.2)
            self.assertEqual(int(np.sum(abs(decoded)>=1)),0)

    def test_descriptor_mismatch_and_nonfinite_source_rejected(self):
        with self.assertRaises(ValueError):
            encode_excitation(self.reference[:-1],self.sr,self.base,4,self.provider)
        source=self.reference.copy();source[2]=np.nan
        with self.assertRaises(ValueError):
            encode_excitation(source,self.sr,self.base,4,self.provider)
        data,_,_=encode_excitation(self.reference,self.sr,self.base,4,self.provider)
        invalid=bytearray(data);struct.pack_into('<I',invalid,24+16,self.samples+1)
        with self.assertRaises(ValueError):inspect_container(bytes(invalid))


if __name__ == '__main__':
    unittest.main()

"""Contract, physical EEPROM layout, provenance and spectrum checks for the bank."""
from pathlib import Path
import cmath
import copy
import importlib.util
import json
import math
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('instrument_bank', ROOT / 'tools/instrument-bank.py')
bank_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bank_module)


class InstrumentBankTests(unittest.TestCase):
    def setUp(self):
        self.bank = bank_module.load_bank()

    def test_firmware_build_needs_no_numpy_or_renderer(self):
        self.assertNotIn('numpy', sys.modules)
        self.assertEqual(len(bank_module.build_eeprom({'lead': 'flute'}, self.bank)), 64)
        self.assertNotIn('numpy', sys.modules)

    def test_physical_nibble_order_and_offset_binary(self):
        # A full signed ramp decodes as nibble values 0..15, low nibble first.
        self.assertEqual(bank_module.pack_wave(list(range(-8, 8))), bytes.fromhex('1032547698badcfe'))
        eeprom = bank_module.build_eeprom({'lead': 'flute', 'keys': 'violin', 'pluck': 'cello'}, self.bank)
        for index, name in enumerate(('flute', 'violin', 'cello')):
            for register_index, register in enumerate(('low', 'high')):
                offset = index * 16 + register_index * 8
                decoded = [((eeprom[offset + i // 2] >> (4 * (i % 2))) & 15) - 8 for i in range(16)]
                self.assertEqual(decoded, self.bank['instruments'][name]['waves'][register])
        self.assertEqual(eeprom[48:], b'\x88' * 16)

    def test_existing_three_profiles_remain_byte_identical(self):
        eeprom = bank_module.build_eeprom({'lead': 'violin', 'keys': 'acoustic-grand-piano',
                                          'pluck': 'acoustic-guitar-nylon'}, self.bank)
        self.assertEqual(eeprom[:48].hex(),
                         'a5dc8d6566b88c2386baebde48435476a8dc8b8899693464b9cbed9b78562352b8dcab9988873641dc8b87cb8a354385')

    def test_swapping_an_instrument_changes_only_its_physical_slot(self):
        a = bank_module.build_eeprom({'lead': 'violin', 'keys': 'clarinet', 'pluck': 'cello'}, self.bank)
        b = bank_module.build_eeprom({'lead': 'acoustic-grand-piano', 'keys': 'clarinet', 'pluck': 'cello'}, self.bank)
        self.assertNotEqual(a[:16], b[:16])
        self.assertEqual(a[16:], b[16:])

    def test_off_and_missing_parts_are_physical_silence(self):
        self.assertEqual(bank_module.build_eeprom({}, self.bank), b'\x88' * 64)
        self.assertEqual(bank_module.build_eeprom({'lead': 'off', 'percussion': 'off'}, self.bank), b'\x88' * 64)

    def test_noise_kit_has_measured_gm_notes_and_uses_no_eeprom(self):
        assignments = {'lead': 'violin', 'percussion': 'natural-kit'}
        self.assertEqual(bank_module.build_eeprom(assignments, self.bank),
                         bank_module.build_eeprom({'lead': 'violin'}, self.bank))
        kit = bank_module.describe_assignments(assignments, self.bank)['percussion']
        self.assertTrue(kit['enabled'])
        self.assertEqual(kit['eepromBytes'], 0)
        self.assertEqual([n['gmNote'] for n in kit['notes']], [35, 38, 42])
        self.assertFalse(bank_module.describe_assignments({'percussion': 'off'}, self.bank)['percussion']['enabled'])

    def test_levels_are_explicit_firmware_metadata(self):
        assignment = {'lead': {'instrument': 'flute', 'level': 5}, 'keys': 'off'}
        resolved = bank_module.describe_assignments(assignment, self.bank)
        self.assertEqual(resolved['lead']['level'], 5)
        self.assertEqual(resolved['lead']['gmProgram'], 73)
        self.assertEqual(resolved['lead']['envelope']['model'], 'sustain')
        self.assertEqual(resolved['keys']['level'], 0)
        self.assertEqual(bank_module.build_eeprom(assignment, self.bank),
                         bank_module.build_eeprom({'lead': 'flute'}, self.bank))
        resolved['lead']['envelope']['model'] = 'off'
        self.assertEqual(self.bank['instruments']['flute']['envelope']['model'], 'sustain')

    def test_invalid_assignments_fail_before_emitting_a_firmware(self):
        for assignment in ({'lead': 'pianoo'}, {'bass': 'cello'}, {'lead': {'instrument': []}},
                           {'lead': {'instrument': 'cello', 'level': 16}},
                           {'lead': {'instrument': 'cello', 'level': True}},
                           {'lead': {'instrument': 'off', 'level': 3}},
                           {'percussion': 'violin'}, {'keys': {'instrument': 'flute', 'gain': .5}}):
            with self.subTest(assignment=assignment), self.assertRaises(ValueError):
                bank_module.build_eeprom(assignment, self.bank)
        for wave in ([0] * 15, [8] * 16, [-9] * 16, [0.0] * 16):
            with self.subTest(wave=wave), self.assertRaises(ValueError):
                bank_module.pack_wave(wave)

    def test_measured_provenance_and_gm_programs(self):
        self.assertTrue(bank_module.verify_sources(self.bank))
        programs = {'acoustic-grand-piano': 0, 'acoustic-guitar-nylon': 24, 'fretless-bass': 35,
                    'violin': 40, 'cello': 42, 'clarinet': 71, 'flute': 73}
        self.assertEqual({n: p['gmProgram'] for n, p in self.bank['instruments'].items() if n != 'off'}, programs)
        changed = copy.deepcopy(self.bank)
        changed['instruments']['flute']['source']['measurementSha256'] = '0' * 64
        with self.assertRaises(ValueError):
            bank_module.verify_sources(changed)

    def test_new_integer_waves_match_the_measured_soft_targets(self):
        # Recompute Fourier amplitudes independently, without the NumPy fitter.
        for name in ('flute', 'cello', 'clarinet'):
            profile = self.bank['instruments'][name]
            for register in ('low', 'high'):
                with self.subTest(name=name, register=register):
                    wave = profile['waves'][register]
                    self.assertEqual(sum(wave), 0)
                    self.assertLessEqual(max(abs(v) for v in wave), 5)
                    harmonics = [abs(sum(v * cmath.exp(-2j * math.pi * h * i / 16)
                                         for i, v in enumerate(wave))) for h in range(1, 8)]
                    norm = math.sqrt(sum(x * x for x in harmonics))
                    normalized = [x / norm for x in harmonics]
                    measured = profile['fit']['registers'][register]
                    distance = math.sqrt(sum((a - b) ** 2 for a, b in zip(normalized, measured['softenedTargetAmplitudes'])))
                    self.assertLess(distance, .04)
                    self.assertAlmostEqual(distance, measured['normalizedSpectralDistance'], places=7)


if __name__ == '__main__':
    unittest.main(verbosity=2)

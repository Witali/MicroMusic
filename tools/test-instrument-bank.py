"""Contract, physical EEPROM layout, provenance and spectrum checks for the bank."""
from pathlib import Path
import cmath
import copy
import importlib.util
import hashlib
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

    def test_soft_piano_has_measured_origin_and_less_upper_harmonic_energy(self):
        import cmath
        import math
        base = self.bank['instruments']['acoustic-grand-piano']
        soft = self.bank['instruments']['acoustic-grand-piano-soft']
        self.assertEqual(soft['gmProgram'], 0)
        self.assertEqual(soft['envelope']['defaultLevel'], 14)
        for register in ('low', 'high'):
            def upper_energy(wave):
                coefficient = lambda h: sum(v * cmath.exp(-2j*math.pi*h*i/16) for i,v in enumerate(wave))
                return sum(abs(coefficient(h))**2 for h in range(4,8))/abs(coefficient(1))**2
            self.assertLess(upper_energy(soft['waves'][register]), upper_energy(base['waves'][register]))
            self.assertEqual(sum(soft['waves'][register]),0)
            self.assertLessEqual(max(abs(a-b) for a,b in zip(soft['waves'][register],soft['transient']['waves'][register])),1)

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

    def test_existing_violin_and_guitar_profiles_remain_byte_identical(self):
        eeprom = bank_module.build_eeprom({'lead': 'violin', 'keys': 'acoustic-grand-piano',
                                          'pluck': 'acoustic-guitar-nylon'}, self.bank)
        self.assertEqual(eeprom[:16].hex(), 'a5dc8d6566b88c2386baebde48435476')
        self.assertEqual(eeprom[32:48].hex(), 'b8dcab9988873641dc8b87cb8a354385')

    def test_swapping_to_piano_also_selects_the_shared_attack_pair(self):
        a = bank_module.build_eeprom({'lead': 'violin', 'keys': 'clarinet', 'pluck': 'cello'}, self.bank)
        b = bank_module.build_eeprom({'lead': 'acoustic-grand-piano', 'keys': 'clarinet', 'pluck': 'cello'}, self.bank)
        self.assertNotEqual(a[:16], b[:16])
        self.assertEqual(a[16:48], b[16:48])
        self.assertEqual(a[48:], b'\x88' * 16)
        self.assertNotEqual(a[48:], b[48:])

    def test_piano_attack_tables_are_shared_for_any_role(self):
        piano = self.bank['instruments']['acoustic-grand-piano']
        expected = b''.join(bank_module.pack_wave(piano['transient']['waves'][r]) for r in ('low', 'high'))
        saved = copy.deepcopy(self.bank)
        for role in ('lead', 'keys', 'pluck'):
            with self.subTest(role=role):
                assignment = {role: 'acoustic-grand-piano'}
                self.assertEqual(bank_module.build_eeprom(assignment, self.bank)[48:], expected)
                resolved = bank_module.describe_assignments(assignment, self.bank)[role]
                self.assertEqual(resolved['transient'], dict(kind='piano-attack', minEnvelopeLevel=14,
                    eepromOffsets={'low': 48, 'high': 56}, maximumSwitchSampleDelta=1))
                self.assertEqual(resolved['envelope']['releaseStep'], 2)
                self.assertEqual(resolved['envelope']['decayMaskByRegister'],
                    dict(thresholdMidi=75, thresholdDdsStep=2175, lowMask=3, highMask=0))
                resolved['transient']['minEnvelopeLevel'] = 0
                resolved['envelope']['decayMaskByRegister']['thresholdMidi'] = 0
        self.assertEqual(bank_module.build_eeprom(dict.fromkeys(('lead', 'keys', 'pluck'), 'acoustic-grand-piano'), self.bank)[48:], expected)
        self.assertEqual(self.bank, saved)

    def test_unsupported_attack_configurations_fail_closed(self):
        for field, value in (('kind', 'guitar'), ('minEnvelopeLevel', 13),
                             ('eepromOffsets', {'low': 40, 'high': 48}),
                             ('maximumSwitchSampleDelta', 2)):
            changed = copy.deepcopy(self.bank)
            changed['instruments']['acoustic-grand-piano']['transient'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                bank_module.build_eeprom({'lead': 'acoustic-grand-piano'}, changed)
        for wave in ([0] * 15, [8] * 16, [1] * 16, [-7, 7] * 8):
            changed = copy.deepcopy(self.bank)
            changed['instruments']['acoustic-grand-piano']['transient']['waves']['low'] = wave
            with self.subTest(wave=wave), self.assertRaises(ValueError):
                bank_module.build_eeprom({'lead': 'acoustic-grand-piano'}, changed)
        changed = copy.deepcopy(self.bank)
        changed['instruments']['acoustic-grand-piano']['gmProgram'] = 24
        with self.assertRaises(ValueError):
            bank_module.build_eeprom({'lead': 'acoustic-grand-piano'}, changed)

    def test_measured_piano_attack_and_sustain_quality_independent_dft(self):
        # These assertions validate the actual four-bit values, not a second
        # execution of the same fitter. No NumPy is needed by build or tests.
        profile = self.bank['instruments']['acoustic-grand-piano']
        report_path = ROOT / profile['fit']['report']
        self.assertEqual(hashlib.sha256(report_path.read_bytes()).hexdigest(), profile['fit']['reportSha256'])
        report = json.loads(report_path.read_text(encoding='utf-8'))
        self.assertEqual(report['measurementSha256'], profile['source']['measurementSha256'])
        for register in ('low', 'high'):
            measured = report['registers'][register]
            waves = [profile['transient']['waves'][register], profile['waves'][register]]
            self.assertEqual(waves, [measured['attackWave'], measured['sustainWave']])
            fundamental = []
            for stage, wave in zip(('attack', 'sustain'), waves):
                self.assertEqual(sum(wave), 0)
                self.assertLessEqual(max(abs(v) for v in wave), 7)
                coefficients = [sum(v * cmath.exp(-2j * math.pi * h * i / 16)
                                    for i, v in enumerate(wave)) for h in range(1, 8)]
                fundamental.append(coefficients[0])
                norm = math.sqrt(sum(abs(x) ** 2 for x in coefficients))
                distance = math.sqrt(sum((abs(x) / norm - target) ** 2 for x, target in zip(coefficients, measured[stage + 'Target'])))
                self.assertLess(distance, .05)
                self.assertAlmostEqual(distance, measured[stage + 'Distance'], places=12)
                self.assertLess(distance, measured['oldSustainDistances'][stage == 'sustain'])
            self.assertLess(abs(abs(fundamental[0] / fundamental[1]) - 1), .005)
            self.assertLess(abs(cmath.phase(fundamental[0] / fundamental[1])) * 180 / math.pi, 1)
            self.assertEqual(max(abs(a - b) for a, b in zip(*waves)), 1)

    def test_piano_capture_contains_fast_decaying_upper_register(self):
        profile = self.bank['instruments']['acoustic-grand-piano']
        data = json.loads((ROOT / profile['source']['measurement']).read_text(encoding='utf-8'))
        self.assertEqual([n['midi'] for n in data['notes']], list(range(49, 83)))
        self.assertEqual(data['program'], 0)
        self.assertEqual(data['velocity'], 100)
        self.assertFalse(data['effectsEnabled'])
        # Upper notes lose much more energy in 500ms than low notes. That is
        # why the synthesis envelope now has an explicit MIDI75 decay split.
        index = min(range(len(data['envelopeTimesSeconds'])), key=lambda i: abs(data['envelopeTimesSeconds'][i] - .5))
        def median(values):
            values = sorted(values)
            return (values[(len(values) - 1) // 2] + values[len(values) // 2]) / 2
        high = median([n['rms'][index] for n in data['notes'] if n['midi'] >= 75])
        low = median([n['rms'][index] for n in data['notes'] if n['midi'] < 62])
        self.assertLess(high, .12)
        self.assertGreater(low, .4)

    def test_selected_high_piano_decay_matches_measured_dynamics_better(self):
        profile = self.bank['instruments']['acoustic-grand-piano']
        report = json.loads((ROOT / profile['fit']['report']).read_text(encoding='utf-8'))
        high = report['envelopeComparison']['high']
        selected_error = sum((a - b) ** 2 for a, b in zip(high['measuredMedianNormalizedRms'], high['selectedEnvelopeMedian']))
        old_error = sum((a - b) ** 2 for a, b in zip(high['measuredMedianNormalizedRms'], high['oldMask3EnvelopeMedian']))
        self.assertLess(selected_error, old_error / 10)
        self.assertEqual(report['decayMaskByRegister'], profile['envelope']['decayMaskByRegister'])

    def test_fretless_has_finite_low_level_plucked_decay(self):
        resolved = bank_module.describe_assignments({'keys': 'fretless-bass'}, self.bank)['keys']
        self.assertEqual(resolved['level'], 6)
        self.assertEqual(resolved['envelope'], dict(model='pluck', defaultLevel=6, decayMask=3,
                                                  retrigger='peak', releaseStep=1))

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
        programs = {'acoustic-grand-piano': 0, 'acoustic-grand-piano-soft': 0,
                    'acoustic-guitar-nylon': 24, 'fretless-bass': 35,
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

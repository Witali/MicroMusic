"""Selection, integer synthesis, unchanged hi-hat and measured-kit regressions."""
from pathlib import Path
import copy
import hashlib
import importlib.util
import json
import math
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('percussion_bank', ROOT / 'tools/percussion-bank.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PercussionBankTests(unittest.TestCase):
    def setUp(self):
        self.bank = module.load_bank()

    def test_selection_and_render_need_no_numpy_soundfont_or_eeprom(self):
        self.assertNotIn('numpy', sys.modules)
        selected = module.select_kit(bank=self.bank)
        self.assertEqual([selected[k]['gmNote'] for k in ('kick', 'snare', 'hat')], [35, 38, 42])
        self.assertEqual(selected['hat']['id'], 'closed-hi-hat')
        self.assertEqual(selected['snare']['id'], 'acoustic-snare-soft-body')
        self.assertEqual(len(module.render_hit(selected['hat'])), 5625)
        self.assertNotIn('numpy', sys.modules)

    def test_retained_measurement_provenance(self):
        self.assertTrue(module.verify_source(self.bank))
        self.assertEqual(self.bank['source']['soundfont']['sha256'], '74594e8f4250680adf590507a306655a299935343583256f3b722c48a1bc1cb0')
        corrupted = copy.deepcopy(self.bank)
        corrupted['source']['measurementSha256'] = '0' * 64
        with self.assertRaises(ValueError):
            module.verify_source(corrupted)

    def test_selection_is_a_copy_and_unknown_gm_notes_are_not_silently_substituted(self):
        selected = module.select_gm_note(42, bank=self.bank)
        selected['generator']['noiseShift'] = 99
        self.assertEqual(module.select_gm_note(42, bank=self.bank)['generator']['noiseShift'], 2)
        for note in (36, 44, 49, -1, 128, True):
            with self.assertRaises(ValueError):
                module.select_gm_note(note, bank=self.bank)
        for name in ('missing', None, {}):
            with self.assertRaises(ValueError):
                module.select_hit(name, bank=self.bank)
            with self.assertRaises(ValueError):
                module.select_kit(name, bank=self.bank)
        for shift in (-1, 4, .5, True):
            with self.assertRaises(ValueError):
                module.select_kit(attenuation_shift=shift, bank=self.bank)

    def test_profiles_validate_before_selection(self):
        for key, value in [('feedbackXor', 0), ('nonzeroSeed', 0), ('period', 255)]:
            corrupted = copy.deepcopy(self.bank)
            corrupted['noise'][key] = value
            with patch.object(module.json, 'loads', return_value=corrupted):
                with self.assertRaises(ValueError):
                    module.load_bank()

    def test_existing_lfsr_has_all_65535_nonzero_states(self):
        state = 167
        visited = set()
        for _ in range(65535):
            self.assertNotEqual(state, 0)
            self.assertNotIn(state, visited)
            visited.add(state)
            state = module.lfsr_step(state)
        self.assertEqual(state, 167)
        self.assertEqual(len(visited), 65535)

    def test_hi_hat_integer_bits_and_decay_are_unchanged(self):
        hat = module.select_gm_note(42, bank=self.bank)
        self.assertEqual(hat['generator'], dict(kind='noise', noiseMode='difference', noiseShift=2))
        # Independent byte-by-byte rendition of LSL low / ADC high / XOR0x2D,
        # and the same LSR/ANDI/SUB/ASR/ASR sequence as the working AVR hat.
        for high_seed in (0, 113, 255):
            low, high = 167, high_seed
            actual = module.render_hit(hat, first_stage_ticks=2, initial_noise_high=high_seed)
            for position, value in enumerate(actual):
                time_ticks = position * 9600000 / (18750 * 131072)
                stage = math.floor(time_ticks / 2)
                if stage >= 4:
                    self.assertEqual(value, 0)
                    continue
                carry = low >> 7
                low = (low * 2) & 255
                overflow = high >> 7
                high = ((high * 2) + carry) & 255
                if overflow:
                    low ^= 45
                first, second = (low // 2) & 63, low & 63
                expected = ((first - second) // 2 // 2) // (2 ** stage.bit_count())
                self.assertEqual(value, expected)

    def test_selected_snare_keeps_noise_and_uses_existing_counter_body(self):
        hit = module.select_gm_note(38, bank=self.bank)
        generator = hit['generator']
        self.assertEqual(generator['noiseShift'], 2)
        self.assertEqual(generator['phaseSource'], 'existing PWM counter R15')
        self.assertEqual(generator['phaseStep'], 2)
        self.assertEqual(generator['phaseOffset'], -64)
        self.assertEqual(module.triangle(1 - 64), 0, 'body starts nearzero')
        self.assertEqual(18750 * generator['phaseStep'] / 256, 146.484375)
        self.assertEqual(hit['signedDutyRange'], [-24, 23])

    def test_four_stage_decay_has_a_finite_silent_tail_and_safe_mix_bounds(self):
        for hit in module.select_kit(bank=self.bank).values():
            for first in (1, 2):
                actual = module.render_hit(hit, first_stage_ticks=first)
                boundary = math.ceil((first + 6) * 131072 / 9600000 * 18750)
                self.assertTrue(all(value == 0 for value in actual[boundary:]))
                self.assertTrue(any(value != 0 for value in actual[:boundary]))
                self.assertGreaterEqual(min(actual), hit['signedDutyRange'][0])
                self.assertLessEqual(max(actual), hit['signedDutyRange'][1])
                # Even three maximum-level signed4-bit tonal waves fit in PWM.
                self.assertGreaterEqual(3 * (-8 * 15 // 4) + hit['signedDutyRange'][0], -128)
                self.assertLessEqual(3 * (7 * 15 // 4) + hit['signedDutyRange'][1], 127)
            quieter = module.select_hit(hit['id'], attenuation_shift=1, bank=self.bank)
            self.assertEqual(module.render_hit(quieter), [v >> 1 for v in module.render_hit(hit)])

    def test_midpoint_rounding_and_level_validation(self):
        self.assertEqual(module.interpolate([-3, 2, -2]), [-3, -1, 2, 0, -2, -1])
        hit = module.select_gm_note(42, bank=self.bank)
        for first in (0, 3, 1.0, True):
            with self.assertRaises(ValueError):
                module.render_hit(hit, first_stage_ticks=first)
        for seconds in (0, -1, math.inf, True):
            with self.assertRaises(ValueError):
                module.render_hit(hit, seconds=seconds)

    def test_retained_measured_snare_improves_spectrum_without_changing_hat(self):
        report = json.loads((ROOT / 'ATtiny13A/Music/instruments/percussion-verification.json').read_text(encoding='utf-8'))
        self.assertEqual(report['sourceMeasurementSha256'], self.bank['source']['measurementSha256'])
        self.assertEqual(report['profileBankSha256'], hashlib.sha256(json.dumps(self.bank, sort_keys=True, separators=(',', ':')).encode()).hexdigest())
        results = report['profiles']
        for old, selected in zip(results['noise-snare-legacy']['candidates'], results['acoustic-snare-soft-body']['candidates']):
            self.assertEqual((old['firstStageTicks'], old['initialNoiseHigh']), (selected['firstStageTicks'], selected['initialNoiseHigh']))
            self.assertLess(selected['spectralDistance'], old['spectralDistance'] * .45)
            self.assertLess(selected['spectralDistance'], .32)
        for entry in results['closed-hi-hat']['candidates']:
            self.assertLess(entry['spectralDistance'], .25)
            self.assertGreater(sum(entry['bandPower'][5:]), .8)
        for entry in results['acoustic-bass-drum']['candidates']:
            self.assertLess(entry['spectralDistance'], .23)
            self.assertGreater(sum(entry['bandPower'][:2]), .9)

    def compiled_kits(self):
        template = (ROOT / 'tools/avr-synth-template.S').read_text(encoding='utf-8')
        assembler_spec = importlib.util.spec_from_file_location('percussion_assembler', ROOT / 'tools/assemble-avr.py')
        assembler = importlib.util.module_from_spec(assembler_spec)
        assembler_spec.loader.exec_module(assembler)
        results = {}
        for kit in ('natural-kit', 'legacy-kit', 'full-body-comparison'):
            source = module.compile_source(template, kit, bank=self.bank)
            region = source.split('render_drum:\n', 1)[1].split('write_pwm:\n', 1)[0]
            standalone = 'render_drum:\n' + region + 'write_pwm:\n  nop\n'
            with patch.object(Path, 'read_text', return_value=standalone):
                rom, labels = assembler.assemble(ROOT / 'build/virtual-percussion.S')
            results[kit] = dict(source=source, rom=list(rom), labels=labels)
        return template, results

    def test_compile_three_kits_preserves_hat_opcode_bytes_and_takes_no_extra_data(self):
        template, results = self.compiled_kits()
        self.assertEqual(module._instructions(results['natural-kit']['source']), module._instructions(template))
        legacy = results['legacy-kit']
        legacy_noise_size = legacy['labels']['.L2ae'] - legacy['labels']['.L298']
        golden_noise = legacy['rom'][legacy['labels']['.L298']:legacy['labels']['.L2ae']]
        for kit, compiled in results.items():
            start = compiled['labels']['.L298']
            self.assertEqual(compiled['rom'][start:start + legacy_noise_size], golden_noise, kit)
            self.assertEqual(module.compile_source(compiled['source'], kit, bank=self.bank), compiled['source'])
        self.assertEqual(len(results['natural-kit']['rom']) - len(legacy['rom']), 22)
        self.assertEqual(len(results['full-body-comparison']['rom']) - len(legacy['rom']), 20)

    def test_compile_fails_closed_on_unknown_source_and_incompatible_profiles(self):
        source = (ROOT / 'tools/avr-synth-template.S').read_text(encoding='utf-8')
        for bad in ('', source.replace('render_drum:', 'unknown:'), source.replace('eor r14, r17', 'nop')):
            with self.assertRaises(ValueError):
                module.compile_source(bad, bank=self.bank)
        for profile, key, value in [('closed-hi-hat', 'noiseShift', 1),
                                    ('acoustic-bass-drum', 'phaseStep', 2),
                                    ('acoustic-snare-soft-body', 'phaseStep', 3)]:
            altered = copy.deepcopy(self.bank)
            altered['profiles'][profile]['generator'][key] = value
            with self.assertRaises(ValueError):
                module.compile_source(source, bank=altered)
        altered = copy.deepcopy(self.bank)
        altered['noise']['feedbackXor'] = 43
        with self.assertRaises(ValueError):
            module.compile_source(source, bank=altered)

    def test_compiled_avr_hit_samples_equal_integer_profiles_for_all_three_kits(self):
        _, compiled = self.compiled_kits()
        # Execute the assembled instructions in the independently audited AVR
        # interpreter. No mocked generator or second JavaScript drum model.
        cases = []
        for kit, result in compiled.items():
            for kind, role in ((0, 'kick'), (2, 'hat'), (4, 'snare')):
                hit = module.select_kit(kit, bank=self.bank)[role]
                for first in (1, 2):
                    cases.append(dict(kit=kit, kind=kind, first=first, rom=result['rom'], labels=result['labels'],
                                      expected=module.render_hit(hit, first_stage_ticks=first, seconds=2304 / 18750)))
        core_url = (ROOT / 'web-player/lib/avr-core.js').as_uri()
        program = f'''import {{AVRCore}} from {json.dumps(core_url)};
import fs from 'node:fs';
const cases=JSON.parse(fs.readFileSync(0,'utf8'));
for(const item of cases){{
  const c=new AVRCore(Uint8Array.from(item.rom)),actual=[];
  c.r[14]=167;c.sram[0]=0;c.r[29]=item.kind;
  for(let index=0;index<item.expected.length;index++){{
    const ticks=index*9600000/(18750*131072);
    c.r[15]=(2*index+1)&255;c.r[21]=ticks<item.first?0:1+Math.floor((ticks-item.first)/2);
    c.r[26]=0;c.pc=0;
    let steps=0;
    while(c.pc!==item.labels.write_pwm/2){{c.step();if(++steps>100)throw Error('Drum did not return');}}
    const value=c.r[26]<128?c.r[26]:c.r[26]-256;
    if(value!==item.expected[index])throw Error(`${{item.kit}} kind${{item.kind}} sample${{index}}: ${{value}} != ${{item.expected[index]}}`);
  }}
}}
console.log('Exact AVR/profile match: '+cases.length+' hit variants, 2304 samples each');'''
        result = subprocess.run(['node', '--input-type=module', '-e', program], input=json.dumps(cases),
                                text=True, capture_output=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Exact AVR/profile match: 18 hit variants', result.stdout)


if __name__ == '__main__':
    unittest.main(verbosity=2)

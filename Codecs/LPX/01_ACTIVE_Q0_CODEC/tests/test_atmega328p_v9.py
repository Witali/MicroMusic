"""Cheap source/fixture binding for the separately run live-IRQ benchmark."""
import json
import unittest
from verify_atmega328p_v9 import ACTIVE, REPO, RECEIPT, CASES, sha, text_sha
from verify_atmega328p_v9 import adapt_player, adapt_observer, adapt_builder, adapt_verifier


class Atmega328pV9Tests(unittest.TestCase):
    def setUp(self):
        self.receipt = json.loads((ACTIVE/'examples/ATTINY88_V5_PLAYER/atmega328p-v9-measurements.json').read_text())

    def test_measurement_binds_sources_and_private_port(self):
        r = self.receipt
        for name, digest in r['production_source_sha256'].items():
            self.assertEqual(text_sha((REPO/name).read_bytes()), digest, name)
        self.assertEqual(text_sha(RECEIPT.read_bytes()), r['frozen_tiny_receipt_sha256'])
        base = 'Codecs/LPX/'
        for source, transform, generated in (
            (ACTIVE/'examples/ATTINY88_V5_PLAYER/player.cpp', adapt_player,
             base+'01_ACTIVE_Q0_CODEC/examples/ATTINY88_V5_PLAYER/player.cpp'),
            (ACTIVE.parent/'validation/attiny88/sim_player.c', adapt_observer,
             base+'validation/attiny88/sim_player.c')):
            self.assertEqual(text_sha(transform(source.read_text()).encode()), r['generated_source_sha256'][generated])
        for source, transform, generated in (
            ('build_attiny88_player', adapt_builder, 'build_mega_player.py'),
            ('verify_attiny88_player', adapt_verifier, 'verify_mega_player.py')):
            self.assertEqual(text_sha(transform((ACTIVE/'tools'/(source+'.py')).read_text()).encode()),
                             r['generated_tool_sha256'][generated])

    def test_public_fixture_streams_match_frozen_oracles(self):
        import sys
        sys.path.insert(0, str(ACTIVE/'tools'))
        from speech_v9 import repack
        from test_speech_v9 import sparse_fixture
        paths = [ACTIVE/'tests/fixtures/chego-2k-v8.lpx',
                 REPO/'web-player/audio/lpx-speech/chego/compact.lpx',
                 REPO/'web-player/audio/lpx-speech/chego/quality.lpx']
        blobs = [repack(p.read_bytes())[0] for p in paths]
        blobs.append(repack(sparse_fixture(12800, 'changing', 16383, 11468, 18)[0])[0])
        frozen = json.loads(RECEIPT.read_text())
        for name, blob in zip(CASES, blobs):
            old = next(row for row in frozen['cases'] if row['case']==name)
            self.assertEqual(sha(blob), old['data_sha256'])
            for row in self.receipt['cases']:
                if row['case']==name:
                    self.assertEqual(row['input_sha256'], old['data_sha256'])
                    self.assertEqual(row['pwm_sha256'], old['pwm_sha256'])

    def test_real_backend_flags_and_strict_playback_outcomes(self):
        rows = self.receipt['cases']
        self.assertEqual([r['case'] for r in rows if r['backend']=='asm'], list(CASES))
        self.assertEqual(sum(r['backend']=='c' for r in rows), 1)
        for row in rows:
            options = row['compiler_options']
            self.assertIn('-mmcu=atmega328p', options)
            self.assertIn('-finline-small-functions', options)
            self.assertFalse(any(o.startswith(('-ffixed-r', '-D__AVR', '-DLPX4_ARCH=')) for o in options))
            self.assertEqual(row['backend_macro'], int(row['backend']=='asm'))
            self.assertTrue(row['dequeued_pwm_exact'] and row['irq_registers_preserved'])
            if row['backend']=='asm':
                self.assertTrue(row['accepted_real_time'] and row['pwm_exact'])
                self.assertEqual(row['underruns'], 0)
            else:
                self.assertFalse(row['accepted_real_time'])
                self.assertGreater(row['total_active_cycles_per_sample'], 2000)
                self.assertEqual(row['output_samples'], row['samples']+row['underruns'])
        with self.assertRaises(ValueError):
            adapt_player('unrelated or changed source')


if __name__ == '__main__':
    unittest.main()

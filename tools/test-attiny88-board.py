"""Check retained MH-ET LIVE Flash artifacts and the bare-chip build contract.

Run --rebuild-default to additionally compile every unchanged 8 MHz ISP image
into build/ and compare BIN bytes and HEX records with the originals (checkout
line endings are deliberately excluded from the Intel HEX record comparison).
"""
import importlib.util
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('attiny88_builder', HERE/'build-attiny88-music.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
REBUILD_DEFAULT = '--rebuild-default' in sys.argv
if REBUILD_DEFAULT:
    sys.argv.remove('--rebuild-default')


class BoardImages(unittest.TestCase):
    def test_three_fifths_clock_has_no_false_tick_for_zero_advance(self):
        fraction, phase, ticks, samples = 4, 0, 0, 0
        for _ in range(256*5):
            result = fraction-3
            advance = int(result < 0)
            fraction = result+5 if advance else result
            before = phase
            phase = (phase+advance)&255
            ticks += int(before+advance > 255)
            samples += advance
            self.assertIn(fraction, range(5))
        self.assertEqual((samples,ticks,phase,fraction), (768,3,0,4))
        self.assertEqual(31_250*3/5,18_750)

    def test_all_nine_flash_images_preserve_bank_and_bootloader_space(self):
        for name in builder.VARIANTS:
            with self.subTest(variant=name):
                folder = builder.MICRONUCLEUS_OUTPUT/name
                meta = json.loads((folder/'build-report.json').read_text(encoding='utf-8'))
                raw = (folder/'synth.bin').read_bytes()
                bank = (folder/'wave-bank.bin').read_bytes()
                storage = meta['wavetableStorage']
                self.assertEqual((meta['cpuHz'],meta['pwmHz'],meta['synthesisHz']),
                                 (16_000_000,62_500,31_250))
                self.assertEqual(meta['controlClock']['virtualSamples'],3)
                self.assertEqual(meta['controlClock']['physicalSamples'],5)
                self.assertEqual(meta['wavetableHighStepThreshold'],614)
                self.assertEqual((meta['eepromBytes'],meta['eepromSha256']), (0,None))
                self.assertIsNone(meta['requiredFuses'])
                self.assertEqual(meta['applicationFlashLimit'],6012)
                self.assertLessEqual(len(raw),6012)
                self.assertEqual(len(bank),64)
                self.assertEqual(storage['address']%256,0)
                self.assertEqual(raw[storage['address']:storage['address']+64],bank)
                self.assertEqual(storage['sha256'],builder.sha(bank))
                self.assertEqual(meta['flashSha256'],builder.sha(raw))
                self.assertEqual((folder/'synth.hex').read_text(),builder.ihex(raw))
                self.assertFalse((folder/'eeprom.hex').exists())
                self.assertFalse((folder/'eeprom.bin').exists())
                # Micronucleus relies on the reset vector being an RJMP;
                # uploader patching is handled by the board's own bootloader.
                self.assertEqual(int.from_bytes(raw[:2],'little')&0xf000,0xc000)
                self.assertEqual(len(meta['flashBankReads']),3 if name.endswith('-sparse') else 1)
                for read in meta['flashBankReads']:
                    op = int.from_bytes(raw[read['address']:read['address']+2],'little')
                    self.assertEqual(op,0x9004|(read['outputRegister']<<4))
                    self.assertTrue(read['preservesSreg'])
                source = (folder/'synth.S').read_text()
                self.assertNotIn('  sbi 31, 0\n',source)
                self.assertNotIn('  out 33,',source)
                self.assertIn('_SFR_IO_ADDR(EIMSK)',source)
                for file,digest in meta['sourceInputs'].items():
                    self.assertEqual(builder.sha((builder.ROOT/file).read_bytes()),digest,file)
                self.assertEqual(meta['generator']['sha256'],builder.sha(Path(builder.__file__).read_text(encoding='utf-8').encode('utf-8')))

    @unittest.skipUnless(REBUILD_DEFAULT,'pass --rebuild-default to run GNU AVR')
    def test_default_isp_firmware_bytes_are_unchanged(self):
        compiler = builder.toolchain(None)
        retained = builder.OUTPUT
        builder.OUTPUT = builder.ROOT/'build/attiny88-board-default-rebuild'
        try:
            for name in builder.VARIANTS:
                with self.subTest(variant=name):
                    builder.build(name,compiler)
                    for file in ('synth.bin','synth.hex','eeprom.bin','eeprom.hex'):
                        generated,original = builder.OUTPUT/name/file,retained/name/file
                        self.assertEqual(generated.read_text() if file.endswith('.hex') else generated.read_bytes(),
                                         original.read_text() if file.endswith('.hex') else original.read_bytes(),file)
        finally:
            builder.OUTPUT = retained


if __name__ == '__main__':
    unittest.main()

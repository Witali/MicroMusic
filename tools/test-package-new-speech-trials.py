"""Packaging refuses stale/unqualified firmware, wrong HEX and repeated tails."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('package_speech', ROOT/'tools/package-new-speech-trials.py')
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


def ihex(data):
    result = []
    for address in range(0, len(data), 16):
        chunk = data[address:address+16]
        row = bytes([len(chunk), address >> 8, address & 255, 0])+chunk
        result.append(':'+row.hex().upper()+f'{-sum(row)&255:02X}')
    return '\n'.join(result+[':00000001FF'])+'\n'


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.base = (ROOT/'build/package-tests').resolve()
        self.base.mkdir(exist_ok=True, parents=True)
        self.path = Path(tempfile.mkdtemp(dir=self.base)).resolve()
        self.assertTrue(self.path.is_relative_to(self.base))
        self.addCleanup(self.clean)
        self.pcm = bytes(range(64))+bytes([128])*128
        image = bytes([0, 1, 2, 3])
        v = dict(schema='test', **{'pass': True}, playbackMode='once',
                 engines=['reference', 'wasm', 'wasm-unoptimized'], verifiedSamples=192,
                 phraseSamples=64, verifiedLoops=1, silenceSamplesVerified=128,
                 mismatches=0, lostOverflows=0, missedSamples=0,
                 imageSha256=package.sha(image), actualPcmSha256=package.sha(self.pcm),
                 expectedPcmSha256=package.sha(self.pcm))
        self.report = dict(status='verified', playbackMode='once', phraseSamples=64,
                           flashBytes=4, eepromBytes=0, eepromUsedBytes=0,
                           imageSha256=package.sha(image), expectedPcmSha256=package.sha(self.pcm),
                           verification=v)
        (self.path/'firmware.bin').write_bytes(image)
        (self.path/'firmware.hex').write_text(ihex(image))
        (self.path/'actual.raw').write_bytes(self.pcm)
        (self.path/'expected.raw').write_bytes(self.pcm)
        self.save()

    def clean(self):
        if not self.path.is_relative_to(self.base):
            raise RuntimeError('Temporary cleanup escaped its verified test directory')
        shutil.rmtree(self.path)

    def save(self):
        (self.path/'build.json').write_text(json.dumps(self.report))

    def test_three_engine_one_shot_pair_is_accepted(self):
        report, pcm = package.verified_bundle(self.path, 64)
        self.assertEqual(pcm.tobytes(), bytes(range(64)))
        self.assertEqual(report['flashBytes'], 4)

    def test_invalid_hex_checksum_cannot_be_distributed(self):
        (self.path/'firmware.hex').write_text(':0400000000010203F5\n:00000001FF\n')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            package.verified_bundle(self.path, 64)

    def test_stale_actual_pcm_hash_is_rejected(self):
        (self.path/'actual.raw').write_bytes(bytes([250])+self.pcm[1:])
        with self.assertRaisesRegex(ValueError, 'PCM SHA'):
            package.verified_bundle(self.path, 64)

    def test_repeat_is_rejected_even_with_consistent_pcm_hashes(self):
        repeated = bytes(range(64))*3
        for name in ('actual.raw', 'expected.raw'):
            (self.path/name).write_bytes(repeated)
        for key in ('expectedPcmSha256',):
            self.report[key] = package.sha(repeated)
        for key in ('expectedPcmSha256', 'actualPcmSha256'):
            self.report['verification'][key] = package.sha(repeated)
        self.save()
        with self.assertRaisesRegex(ValueError, 'phrase/silence'):
            package.verified_bundle(self.path, 64)

    def test_partial_engine_or_pending_qualification_cannot_win_selection(self):
        self.report['verification']['engines'] = ['reference', 'wasm']
        self.save()
        with self.assertRaisesRegex(ValueError, 'three-engine'):
            package.verified_bundle(self.path, 64)
        self.report['verification']['engines'].append('wasm-unoptimized')
        self.report['status'] = 'pending'
        self.save()
        with self.assertRaisesRegex(ValueError, 'three-engine'):
            package.verified_bundle(self.path, 64)

    def test_eeprom_hex_must_match_the_verified_eeprom(self):
        eeprom = bytes(range(64))
        self.report.update(eepromBytes=64, eepromUsedBytes=64, eepromSha256=package.sha(eeprom))
        self.report['verification']['eepromSha256'] = package.sha(eeprom)
        (self.path/'eeprom.bin').write_bytes(eeprom)
        (self.path/'eeprom.hex').write_text(ihex(eeprom))
        self.save()
        package.verified_bundle(self.path, 64)
        (self.path/'eeprom.hex').write_text(ihex(bytes([0])*64))
        with self.assertRaisesRegex(ValueError, 'EEPROM'):
            package.verified_bundle(self.path, 64)

    def test_later_excerpt_manifest_replaces_full_recording(self):
        paths = []
        for index, value in enumerate((dict(id='clip', reference_file='reference.wav'),
                                       dict(id='clip', reference_file='reference.wav', selection_start_seconds=14.24))):
            path = self.path/f'manifest-{index}.json'
            path.write_text(json.dumps(dict(clips=[value])))
            paths.append(path)
        result = package.load_entries(paths)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['id'], 'clip-final')
        self.assertEqual(result[0]['_reference'], self.path/'clip/reference.wav')
        self.assertEqual(result[0]['selection_start_seconds'], 14.24)
        paths[0].write_text(json.dumps(dict(clips=[dict(id='../escape', reference_file='reference.wav')])))
        with self.assertRaisesRegex(ValueError, 'safe lowercase'):
            package.load_entries(paths)


if __name__ == '__main__':
    unittest.main()

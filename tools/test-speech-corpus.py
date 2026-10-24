"""Local corpus provenance, unchanged levels and deterministic preparation."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from scipy.signal import resample_poly
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('prepare_speech_corpus', ROOT/'tools/prepare-speech-corpus.py')
prep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prep)


class SpeechCorpusTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'build').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='test-speech-corpus-', dir=ROOT/'build')
        self.root = Path(self.temp.name)
        self.source = self.root/'source'
        (self.source/'originals').mkdir(parents=True)
        self.sources = []
        self.clips = []
        for identifier, voice in [('ru_square', 'female'), ('ru_russia', 'male')]:
            ogg = self.source/'originals'/f'{identifier}.ogg'
            ogg.write_bytes(b'local hash-verification fixture '+identifier.encode())
            source = dict(id=identifier, language='ru', voice=voice, speaker=identifier,
                file=identifier+'.ogg', title='Fixture only', license='Fixture',
                page='https://example.invalid/source', url='https://example.invalid/audio',
                sha256=prep.digest(ogg))
            self.sources.append(source)
            t = np.arange(144123)/48000
            audio = .2*np.sin(2*np.pi*220*t)+.025
            self.add_clip(source, identifier+'_a', audio, 48000, 'natural', 16)
        # Preserve the modified 8-kHz original, including the original PCM16
        # quantization, rather than attenuating a fresh 48-kHz reference.
        base, rate = sf.read(self.source/'clips/ru_square_a/input.wav', dtype='float64')
        self.add_clip(self.sources[0], 'ru_square_a_quiet_minus24dB',
            np.round(base*10**(-24/20)*32768)/32768, rate, 'quiet_minus24dB', 16)
        self.manifest = self.source/'corpus.json'
        self.write_manifest()

    def tearDown(self):
        self.temp.cleanup()

    def add_clip(self, source, identifier, values, rate, condition, start):
        folder = self.source/'clips'/identifier
        folder.mkdir(parents=True)
        sf.write(folder/'original.wav', values, rate, subtype='FLOAT' if rate == 48000 else 'PCM_16')
        converted = resample_poly(values, 1, 6) if rate == 48000 else values
        sf.write(folder/'input.wav', converted, 8000, subtype='PCM_16')
        self.clips.append(dict(id=identifier, source=source['id'], language=source['language'],
            voice=source['voice'], speaker=source['speaker'], condition=condition,
            start_seconds=start, input_sha256=prep.digest(folder/'input.wav')))

    def write_manifest(self):
        self.manifest.write_text(json.dumps(dict(sources=self.sources, clips=self.clips)), encoding='utf-8')

    def prepare(self, destination='output'):
        return prep.prepare(self.source, self.root/destination)

    def read(self, manifest, source_clip_id, variant='full', output='output'):
        row = next(c for c in manifest['clips'] if c['source_clip_id'] == source_clip_id and c['variant'] == variant)
        values, rate = sf.read(self.root/output/row['reference'], dtype='float64')
        self.assertEqual(rate, 7500)
        return row, values

    def test_original_ogg_hash_mismatch_fails_before_output(self):
        (self.source/'originals/ru_square.ogg').write_bytes(b'changed source')
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            self.prepare()
        self.assertFalse((self.root/'output').exists())

    def test_encoder_input_hash_mismatch_fails_before_output(self):
        path = self.source/'clips/ru_russia_a/input.wav'
        path.write_bytes(path.read_bytes()+b'changed input')
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            self.prepare()
        self.assertFalse((self.root/'output').exists())

    def test_quiet_level_and_dc_are_preserved_without_normalization(self):
        manifest = self.prepare()
        _, base = self.read(manifest, 'ru_square_a')
        quiet_row, quiet = self.read(manifest, 'ru_square_a_quiet_minus24dB')
        ratio_db = 20*np.log10(np.sqrt(np.mean(quiet**2)/np.mean(base**2)))
        self.assertAlmostEqual(float(ratio_db), -24, delta=.02)
        self.assertGreater(float(base.mean()), .02)
        self.assertGreater(float(quiet.mean()), .001)
        self.assertEqual(quiet_row['chosen_original_sha256'], quiet_row['input_8000_sha256'])
        self.assertEqual(quiet_row['split'], 'tuning')
        self.assertFalse(manifest['gain_normalization'])

    def test_wav_and_manifest_reproducible_in_different_output_directories(self):
        one, two = self.prepare('one'), self.prepare('two')
        self.assertEqual(one, two)
        self.assertEqual((self.root/'one/manifest.json').read_bytes(), (self.root/'two/manifest.json').read_bytes())
        for row in one['clips']:
            a, b = self.root/'one'/row['reference'], self.root/'two'/row['reference']
            self.assertEqual(a.read_bytes(), b.read_bytes())
            self.assertEqual(prep.digest(a), row['reference_sha256'])
        self.assertNotIn(str(self.root), json.dumps(one))

    def test_speaker_split_center_crop_offsets_and_only_zero_padding(self):
        manifest = self.prepare()
        tuning = {c['source_id'] for c in manifest['clips'] if c['split'] == 'tuning'}
        evaluation = {c['source_id'] for c in manifest['clips'] if c['split'] == 'evaluation'}
        self.assertFalse(tuning & evaluation)
        full, whole = self.read(manifest, 'ru_square_a')
        short, center = self.read(manifest, 'ru_square_a', 'center2048')
        self.assertNotEqual(full['unpadded_samples'] % 64, 0)
        self.assertEqual(full['samples'] % 64, 0)
        self.assertTrue(np.all(whole[full['unpadded_samples']:] == 0))
        start = (full['unpadded_samples']-15360)//2
        np.testing.assert_array_equal(center, whole[start:start+15360])
        self.assertEqual(short['source_start_seconds'], 16+start/7500)
        self.assertEqual(short['samples'], 15360)
        self.assertTrue(short['cropped'])
        self.assertFalse(short['whole_phrase_guaranteed'])

    def test_float_overshoot_is_reported_and_not_clipped(self):
        path = self.source/'clips/ru_russia_a/original.wav'
        values, rate = sf.read(path, dtype='float64')
        sf.write(path, values*6, rate, subtype='FLOAT')
        manifest = self.prepare()
        row, output = self.read(manifest, 'ru_russia_a')
        self.assertGreater(float(abs(output).max()), 1)
        self.assertTrue(row['input_pcm_range_exceeded'])
        self.assertEqual(row['input_pcm_range_exceeded_samples'], int(np.count_nonzero(abs(output) > 1)))
        self.assertFalse(manifest['clipping'])


if __name__ == '__main__':
    unittest.main()

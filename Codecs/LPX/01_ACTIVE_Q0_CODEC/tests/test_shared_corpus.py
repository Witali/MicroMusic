"""Shared corpus hash domains, unchanged levels, coverage and anonymous manifests."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import soundfile as sf

from shared_corpus import balanced_segments, prepare

REPOSITORY = Path(__file__).resolve().parents[4]


def sha(data):
    return hashlib.sha256(data).hexdigest()


class SharedCorpusTests(unittest.TestCase):
    def setUp(self):
        directory = REPOSITORY / 'build' / 'shared-corpus-tests'
        directory.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=directory)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.collection = self.base / 'collection'
        self.collection.mkdir()
        self.output = self.base / 'output'

    def write_json(self, relative, data):
        path = self.collection / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data) + '\n', encoding='utf-8', newline='\n')

    def audio(self, relative, values, rate=8000, subtype='PCM_16'):
        path = self.collection / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(path, values, rate, subtype=subtype)
        return sha(path.read_bytes())

    def index(self):
        records = []
        for path in sorted(self.collection.rglob('*')):
            if path.is_file() and path.name != 'INDEX.json':
                records.append(dict(file=path.relative_to(self.collection).as_posix(),
                    sha256=sha(path.read_bytes()), bytes=path.stat().st_size,
                    audio=path.suffix.lower() == '.wav'))
        self.write_json('INDEX.json', dict(schema='micromusic-local-audio-collection-v1', files=records))

    def speech(self, values, identifier='private_clip', source='ru_square', rate=8000):
        digest = self.audio(f'speech-ru-en-originals/clips/{identifier}/input.wav', values, rate)
        self.write_json('speech-ru-en-originals/corpus.json', {'clips': [dict(id=identifier,
            source=source, language='ru', condition='quiet_minus24dB', input_sha256=digest,
            frames=402)]})  # Upstream frames are codec packets, not samples.

    def read_reference(self, case):
        pcm, rate = sf.read(self.output / case['reference'], dtype='int16')
        self.assertEqual(rate, 8000)
        self.assertEqual(sha(pcm.astype('<i2').tobytes()), case['reference_pcm16_sha256'])
        return pcm

    def test_primary_quiet_dc_and_one_sample_tail_are_retained_without_normalization(self):
        values = np.r_[np.full(64000, 17, np.int16), np.array([-23], np.int16)]
        self.speech(values)
        # Nested alternate-rate renditions must not become additional inputs.
        self.audio('speech-ru-en-originals/clips/private_clip/16000/input.wav', values, 16000)
        self.index()
        manifest = prepare(self.collection, self.output, ['speech'])
        self.assertEqual(len(manifest['cases']), 1)
        case = manifest['cases'][0]
        np.testing.assert_array_equal(self.read_reference(case), values)
        self.assertEqual(case['split'], 'tuning')
        self.assertEqual(case['condition'], 'quiet_minus24dB')
        self.assertEqual([s['samples'] for s in case['segments']], [32001, 32000])
        chunks = [sf.read(self.output / s['reference'], dtype='int16')[0] for s in case['segments']]
        np.testing.assert_array_equal(np.concatenate(chunks), values)
        public = json.dumps(manifest)
        self.assertNotIn('private_clip', public)
        self.assertNotIn('ru_square', public)
        self.assertNotIn(str(self.collection), public)
        private = json.loads((self.output / 'private-manifest.json').read_text())
        self.assertIn('private_clip', private['inputs'][0]['source_relative'])

    def test_regression_hash_is_pcm16_not_wav_file_and_change_is_rejected(self):
        pcm = np.array([-32768, -7, 0, 123, 32767], np.int16)
        file_hash = self.audio('speech-music-tests-8000/silence/reference.wav', pcm)
        row = dict(id='silence', kind='music', group='synthetic', samples=len(pcm),
                   reference_sha256=sha(pcm.astype('<i2').tobytes()))
        self.assertNotEqual(row['reference_sha256'], file_hash)
        self.write_json('speech-music-tests-8000/corpus.json', {'cases': [row]})
        self.index()
        case = prepare(self.collection, self.output, ['regression'])['cases'][0]
        np.testing.assert_array_equal(self.read_reference(case), pcm)
        row['reference_sha256'] = file_hash
        self.write_json('speech-music-tests-8000/corpus.json', {'cases': [row]})
        self.index()
        with self.assertRaisesRegex(ValueError, 'PCM16 sample hash'):
            prepare(self.collection, self.base / 'bad-output', ['regression'])
        self.assertFalse((self.base / 'bad-output').exists())

    def test_input_file_and_manifest_index_hashes_reject_stale_sources(self):
        self.speech(np.arange(20, dtype=np.int16))
        self.index()
        path = self.collection / 'speech-ru-en-originals/clips/private_clip/input.wav'
        path.write_bytes(path.read_bytes() + b'extra')
        with self.assertRaisesRegex(ValueError, 'Indexed input file'):
            prepare(self.collection, self.output, ['speech'])
        self.assertFalse(self.output.exists())
        self.index()
        manifest_path = self.collection / 'speech-ru-en-originals/corpus.json'
        manifest_path.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Indexed cohort manifest'):
            prepare(self.collection, self.output, ['speech'])

    def test_exact_pcm_duplicates_removed_and_decoder_oracle_is_not_an_input(self):
        pcm = np.array([100, -200, 300, -400], np.int16)
        self.audio('instrument-samples/grid/piano/a.wav', pcm)
        self.audio('instrument-samples/fluidr3-context/duplicate.wav', pcm)
        self.audio('speex-decoder-corpora/oracle.wav', np.zeros(800, np.int16))
        self.index()
        result = prepare(self.collection, self.output, ['instruments'])
        self.assertEqual(result['source_inputs'], 2)
        self.assertEqual(result['duplicates_removed'], 1)
        self.assertEqual(len(result['cases']), 1)
        np.testing.assert_array_equal(self.read_reference(result['cases'][0]), pcm)

    def test_original_manifest_resolves_hash_when_upstream_filename_is_absent(self):
        pcm = np.array([1000, -2000, 3000], np.int16)
        digest = self.audio('music-originals/local-copy.wav', pcm)
        self.write_json('music-originals/sources.json', [dict(id='piano', file='absent-upstream.ogg',
            sha256=digest, local='must-not-be-copied-into-public-manifest')])
        self.index()
        result = prepare(self.collection, self.output, ['music'])
        np.testing.assert_array_equal(self.read_reference(result['cases'][0]), pcm)
        self.assertNotIn('local-copy', json.dumps(result))
        self.assertNotIn('absent-upstream', json.dumps(result))

    def test_stereo_average_rounds_once_and_reports_pcm16_clipping(self):
        values = np.array([[1.25, 1.25], [-1.25, -1.25], [1/32768, 2/32768],
                           [-2/32768, -3/32768], [.25, -.25]], dtype=np.float64)
        self.audio('instrument-samples/stereo.wav', values, subtype='FLOAT')
        self.index()
        case = prepare(self.collection, self.output, ['instruments'])['cases'][0]
        np.testing.assert_array_equal(self.read_reference(case), [32767, -32768, 2, -2, 0])
        self.assertEqual(case['conversion']['clipped_samples'], 2)
        self.assertTrue(case['conversion']['channel_average'])
        self.assertFalse(case['conversion']['resampled'])

    def test_rational_resample_retains_full_duration_and_deterministic_bytes(self):
        # A quiet DC plateau detects accidental normalization/high-pass filtering.
        values = np.full(7500, .01, dtype=np.float64)
        self.audio('instrument-samples/quiet.wav', values, 7500, 'FLOAT')
        self.index()
        before = prepare(self.collection, self.output, ['instruments'])
        case = before['cases'][0]
        pcm = self.read_reference(case)
        self.assertEqual(len(pcm), 8000)
        self.assertLess(abs(float(pcm[100:-100].mean()) - 327.68), 1.)
        wav_bytes = (self.output / case['reference']).read_bytes()
        self.assertEqual(prepare(self.collection, self.output, ['instruments']), before)
        self.assertEqual((self.output / case['reference']).read_bytes(), wav_bytes)

    def test_only_declared_prepared_phrases_are_selected(self):
        pcm = np.arange(320, dtype=np.int16)
        digest = self.audio('new-phrases-7500/phrase/reference.wav', pcm)
        self.audio('new-phrases-7500/phrase/ffmpeg-independent.wav', pcm + 1)
        self.write_json('new-phrases-7500/manifest.json', {'clips': [dict(id='phrase',
            reference_file='reference.wav', reference_sha256=digest,
            source_mono_dc_removed=.001, normalization_gain=2.)]})
        self.index()
        result = prepare(self.collection, self.output, ['phrases'])
        self.assertEqual(result['source_inputs'], 1)
        self.assertEqual(result['cases'][0]['condition'], 'prepared')
        np.testing.assert_array_equal(self.read_reference(result['cases'][0]), pcm)

    def test_reject_nonfinite_and_primary_rate_changes_before_writing(self):
        self.audio('instrument-samples/nonfinite.wav', np.array([0., np.nan]), subtype='FLOAT')
        self.index()
        with self.assertRaisesRegex(ValueError, 'finite'):
            prepare(self.collection, self.output, ['instruments'])
        self.speech(np.arange(16, dtype=np.int16), rate=16000)
        self.index()
        with self.assertRaisesRegex(ValueError, 'mono 8 kHz'):
            prepare(self.collection, self.output, ['speech'])
        self.assertFalse(self.output.exists())

    def test_reject_path_escape_and_nonignored_output(self):
        self.speech(np.arange(16, dtype=np.int16))
        self.index()
        index = json.loads((self.collection / 'INDEX.json').read_text())
        index['files'].append(dict(file='../outside.wav', sha256='0'*64))
        self.write_json('INDEX.json', index)
        with self.assertRaisesRegex(ValueError, 'escapes'):
            prepare(self.collection, self.output, ['speech'])
        with self.assertRaisesRegex(ValueError, 'ignored Git'):
            prepare(self.collection, REPOSITORY / 'Codecs/LPX/nonignored-corpus-output', ['speech'])

    def test_balanced_coverage_limit_and_small_inputs(self):
        for count in [1, 63999, 64000, 64001, 128001, 1000000]:
            spans = balanced_segments(count)
            self.assertEqual(sum(s['samples'] for s in spans), count)
            self.assertTrue(all(0 < s['samples'] <= 64000 for s in spans))
            self.assertLessEqual(max(s['samples'] for s in spans) - min(s['samples'] for s in spans), 1)
            self.assertEqual([s['start'] for s in spans], list(np.cumsum([0] + [s['samples'] for s in spans[:-1]])))
        for count, limit in [(0, 64000), (2, 0), (100000, 64001)]:
            with self.assertRaises(ValueError):
                balanced_segments(count, limit)


if __name__ == '__main__':
    unittest.main()

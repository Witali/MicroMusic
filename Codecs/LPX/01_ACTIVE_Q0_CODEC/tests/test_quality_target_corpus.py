"""Public CLI target regression against the retained complete-file LPX corpus.

Run with Python in Linux/WSL. Uses only repository audio and standard-library
preparation; generated executables/media/receipts stay in ignored build/.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import re
import struct
import subprocess
import unittest
import wave

REPO = Path(__file__).resolve().parents[4]
ACTIVE = REPO / 'Codecs/LPX/01_ACTIVE_Q0_CODEC'
OUTPUT = REPO / 'build/pcm-quality-corpus'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class QualityTargetCorpus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        OUTPUT.mkdir(parents=True, exist_ok=True)
        config = (REPO / 'web-player/scripts/lib/lpx-build.mjs').read_text()
        names = re.findall(r"'([^']+\.cpp)'", config.split('export const hostSources=host([')[1].split(']);')[0])
        sources = [ACTIVE / 'src/Lpx4HybridCore.cpp', ACTIVE / 'host/LpxEncoder.cpp',
                   *(ACTIVE / 'host' / name for name in names), ACTIVE / 'host/encode_lpx.cpp']
        inputs = [*sources, *(ACTIVE / 'host').glob('*.h'), *(ACTIVE / 'src').glob('*.h')]
        before = {p.relative_to(REPO).as_posix(): sha(p) for p in inputs}
        cls.encoder = OUTPUT / 'lpx-encode'
        command = ['g++', '-O3', '-std=c++17', '-ffp-contract=off', '-DNDEBUG',
                   '-DLPX4_ENABLE_ASM=0', '-DLPX4_FLOAT_SYNTHESIS=0', '-DLPX4_ENABLE_SPEECH=1',
                   '-DLPX4_ENABLE_SPEECH_COMPACT=1', '-DLPX4_COMPACT_ONLY=1', '-DLPX4_COMPACT_VERSION=9',
                   '-DLPX4_SAMPLE_RATE=0', '-DLPX4_EXTENDED_SAMPLE_RATES=1', '-DLPX4_ENABLE_WIDE_V9=1',
                   '-include', str(ACTIVE / 'host/LpxHostWorkspace.h'),
                   '-I' + str(ACTIVE / 'src'), '-I' + str(ACTIVE / 'host'),
                   *(str(p) for p in sources), '-o', str(cls.encoder)]
        subprocess.run(command, cwd=REPO, check=True)
        if before != {p.relative_to(REPO).as_posix(): sha(p) for p in inputs}:
            raise RuntimeError('Inputs changed during the native build')
        cls.receipt = dict(command=command, sources=before, executable_sha256=sha(cls.encoder), rows=[])
        retained = json.loads((REPO / 'Codecs/LPX/research/lbg1-2026-11-26/results.json').read_text())
        cls.expected = retained['cases']
        helper = REPO / 'Codecs/LPX/research/lbg1-2026-11-26/prepare_sources.py'
        spec = importlib.util.spec_from_file_location('target_resample', helper)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.pcm = {}
        for source in retained['inputs']['sources']:
            path = REPO / source['source']
            if sha(path) != source['source_sha256']:
                raise RuntimeError('Public source changed')
            with wave.open(str(path), 'rb') as f:
                if f.getnchannels() != 1 or f.getsampwidth() != 2:
                    raise RuntimeError('Expected mono PCM16')
                data, rate = f.readframes(f.getnframes()), f.getframerate()
            if rate == 7500:
                samples = struct.unpack('<' + 'h' * (len(data) // 2), data)
                samples = module.resample16_15(samples)
                data = struct.pack('<' + 'h' * len(samples), *samples)
            elif rate != 8000:
                raise RuntimeError('Unexpected source rate')
            if hashlib.sha256(data).hexdigest() != source['pcm_sha256']:
                raise RuntimeError('Prepared PCM differs from the pinned corpus')
            cls.pcm[source['clip']] = data

    @classmethod
    def tearDownClass(cls):
        (OUTPUT / 'receipt.json').write_text(json.dumps(cls.receipt, indent=2) + '\n', encoding='utf-8', newline='\n')

    def encode(self, data, *args):
        result = subprocess.run([str(self.encoder), *args], input=data, capture_output=True, check=True)
        report = json.loads(result.stderr)
        self.assertEqual(report['bytes'], len(result.stdout))
        self.assertEqual(result.stdout[:2], b'L9')
        return result.stdout, report

    def test_default_matches_all_eight_prior_complete_files(self):
        for case in self.expected:
            clip, profile = case['name'].rsplit('-p', 1)
            with self.subTest(case=case['name']):
                data, report = self.encode(self.pcm[clip], '--accuracy', profile, '--calls', '4')
                self.assertEqual(hashlib.sha256(data).hexdigest(), case['baseline']['sha256'])
                self.assertEqual(report['qualityTarget'], 'pwm')
                self.receipt['rows'].append(dict(case=case['name'], target='default-pwm', bytes=len(data),
                    baseline_byte_exact=True, sha256=hashlib.sha256(data).hexdigest()))

    def test_explicit_pwm_matches_implicit_default(self):
        args = ('--accuracy', '4', '--calls', '1')
        implicit, _ = self.encode(self.pcm['chego'], *args)
        explicit, report = self.encode(self.pcm['chego'], *args, '--quality-target', 'pwm')
        self.assertEqual(explicit, implicit)
        self.assertEqual(report['qualityTarget'], 'pwm')

    def test_pcm_accuracy_output_uses_requested_target_at_each_rate(self):
        data = self.pcm['chego'][:1282]
        for rate in (8000, 12000, 16000):
            for profile in (4, 6):
                with self.subTest(rate=rate, profile=profile):
                    output, report = self.encode(data, '--accuracy', str(profile), '--rate', str(rate),
                        '--calls', '1', '--quality-target', 'pcm')
                    self.assertEqual(report['qualityTarget'], 'pcm')
                    self.assertEqual(struct.unpack_from('<HH', output, 3), (rate, len(data) // 2))

    def test_invalid_target_emits_no_stream(self):
        for value in ('', 'PCM', 'dac', '2'):
            result = subprocess.run([str(self.encoder), '--quality-target', value], input=b'', capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, b'')
            self.assertIn('Quality target', json.loads(result.stderr)['error'])


if __name__ == '__main__':
    unittest.main(verbosity=2)

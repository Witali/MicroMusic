"""Independent native contracts for per-encode PCM/PWM quality targets.

Standard-library only. On Windows set LPX_TEST_WSL=Ubuntu; Linux uses g++.
Build composition/portable defines come from the production native/WASM config.
No production source, decoder or media file is modified.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import unittest

ACTIVE = Path(__file__).resolve().parents[1]
REPO = ACTIVE.parents[2]
OUTPUT = REPO / 'build/pcm-quality-policy-audit'


def native(path):
    path = Path(path).resolve()
    if os.name == 'nt' and os.environ.get('LPX_TEST_WSL'):
        return '/mnt/' + path.drive[0].lower() + '/' + '/'.join(path.parts[1:])
    return str(path)


class QualityTargetPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prefix = ['wsl', '-d', os.environ['LPX_TEST_WSL'], '--'] if os.name == 'nt' and os.environ.get('LPX_TEST_WSL') else []
        OUTPUT.mkdir(parents=True, exist_ok=True)
        config = (REPO / 'web-player/scripts/lib/lpx-build.mjs').read_text()
        names = re.findall(r"'([^']+\.cpp)'", config.split('export const hostSources=host([')[1].split(']);')[0])
        defines = re.findall(r"'([^']+)'", config.split('export const portableDefines=[')[1].split('];')[0])
        sources = [ACTIVE / 'src/Lpx4HybridCore.cpp', ACTIVE / 'host/LpxEncoder.cpp',
                   *(ACTIVE / 'host' / name for name in names), ACTIVE / 'host/LpxAdaptiveApi.cpp',
                   ACTIVE / 'host/LpxStreamingApi.cpp', ACTIVE / 'tests/quality_target_policy.cpp']
        command = ['g++', '-O2', '-std=c++11', '-ffp-contract=off', '-pthread',
                   *('-D' + define for define in defines),
                   '-include', native(ACTIVE / 'host/LpxHostWorkspace.h'),
                   '-I' + native(ACTIVE / 'src'), '-I' + native(ACTIVE / 'host'),
                   *(native(path) for path in sources), '-o', native(OUTPUT / 'policy-audit')]
        done = subprocess.run(cls.prefix + command, capture_output=True, text=True)
        if done.returncode:
            raise AssertionError(done.stdout + done.stderr)
        compiler = subprocess.check_output(cls.prefix + ['g++', '--version'], text=True).splitlines()[0]
        manifest = dict(compiler=compiler, command=command,
                        sources={path.relative_to(REPO).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources})
        (OUTPUT / 'build.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')

    def check_native(self, mode):
        done = subprocess.run(self.prefix + [native(OUTPUT / 'policy-audit'), mode], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn('PASS', done.stdout)

    def test_boundary_metrics_and_independent_parallel_contexts(self):
        self.check_native('metrics')

    def test_candidate_cache_policy_ownership_and_continuation_state(self):
        self.check_native('cache')

    def test_c_api_invalid_options_and_legacy_pwm_compatibility(self):
        self.check_native('api')

    def test_interleaved_stream_sessions_and_final_policy_admission(self):
        self.check_native('stream')


if __name__ == '__main__':
    unittest.main()

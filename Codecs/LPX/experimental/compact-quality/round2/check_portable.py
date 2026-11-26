"""Compile the changed accuracy TU without exceptions or RTTI.

Probe freestanding standard-library support separately; never fake hosted
macros. This is native object-only evidence, not a WASM build or MCU test.
Run with Linux/WSL Python and the existing g++; no SDK download is performed.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
ACTIVE = REPO / 'Codecs/LPX/01_ACTIVE_Q0_CODEC'
OUTPUT = REPO / 'build/compact-quality/round2-portable'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    config = REPO / 'web-player/scripts/lib/lpx-build.mjs'
    defines = re.findall(r"'([^']+)'", config.read_text().split('export const portableDefines=[')[1].split('];')[0])
    source = ACTIVE / 'host/LpxAccuracy.cpp'
    inputs = [source, config, Path(__file__).resolve()]
    for directory in (ACTIVE / 'host', ACTIVE / 'src'):
        inputs.extend(directory.glob('*.h'))
        inputs.extend(directory.glob('*.inc'))
    hashes = {p.relative_to(REPO).as_posix(): sha(p) for p in inputs}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    probe_command = ['g++', '-std=c++11', '-ffreestanding', '-x', 'c++', '-c',
                     '-o', str(OUTPUT / 'stdlib-probe.o'), '-']
    probe = subprocess.run(probe_command, input='#include <vector>\n',
                           capture_output=True, text=True)
    freestanding = probe.returncode == 0
    (OUTPUT / 'stdlib-probe.log').write_text(probe.stderr, encoding='utf-8')
    flags = ['-std=c++11', '-O2', '-fno-exceptions', '-fno-rtti',
             '-ffp-contract=off', *('-D' + d for d in defines),
             '-include', 'Codecs/LPX/01_ACTIVE_Q0_CODEC/host/LpxHostWorkspace.h',
             '-ICodecs/LPX/01_ACTIVE_Q0_CODEC/host',
             '-ICodecs/LPX/01_ACTIVE_Q0_CODEC/src']
    if freestanding:
        flags.append('-ffreestanding')
    rows = []
    for value in (0, 1):
        output = OUTPUT / ('accuracy-' + str(value) + '.o')
        command = ['g++', *flags, '-DLPX_ENCODER_COMPACT_ENSEMBLE=' + str(value),
                   '-c', source.relative_to(REPO).as_posix(), '-o', output.relative_to(REPO).as_posix()]
        start = time.perf_counter()
        result = subprocess.run(command, cwd=REPO, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stderr)
        rows.append(dict(enabled=value, command=command, wall_seconds=time.perf_counter() - start,
                         object_bytes=output.stat().st_size, object_sha256=sha(output)))
    if hashes != {name: sha(REPO / name) for name in hashes}:
        raise RuntimeError('Source changed during portability compilation')
    report = dict(status='PASS_NATIVE_OBJECTS', compiler=subprocess.check_output(['g++', '--version'], text=True).splitlines()[0],
                  sources=hashes, variants=rows, freestanding_stdlib_available=freestanding,
                  freestanding_probe_status='PASS' if freestanding else 'UNAVAILABLE_WITH_HOST_STDLIB',
                  scope='Native object compilation only. No WASM link/execution, AVR timing, code-size or hardware claim.')
    (OUTPUT / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('PASS: two native no-exception/no-RTTI objects; freestanding stdlib:',
          'available' if freestanding else 'unavailable', '; no WASM runtime claim')


if __name__ == '__main__':
    main()

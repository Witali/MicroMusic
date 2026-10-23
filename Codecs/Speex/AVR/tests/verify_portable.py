"""Export, archive and consume the C library using only its public API/package.

Compare every retained fixture and prepared human-speech stream to the pinned
upstream host oracle. No source include or object from the checkout may leak
into the exported library build. This is a host portability test, not an MCU
timing claim. Scratch tracking is off, as in a freestanding integration.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build


def run(command):
    subprocess.run([str(v) for v in command], check=True, capture_output=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc', required=True)
    parser.add_argument('--ar', required=True)
    parser.add_argument('--cmake', help='Also build and test the exported CMake target')
    parser.add_argument('--ninja', help='Ninja executable for the optional CMake build')
    parser.add_argument('--package', type=Path, help='Verify an existing exported package')
    args = parser.parse_args()
    output = Path(tempfile.mkdtemp(prefix='portable-check-', dir=ROOT / 'build'))
    package = args.package.resolve() if args.package else build.export_c(output / 'package')
    assert not list(package.rglob('*.S'))
    for name, digest in json.loads((package / 'SHA256.json').read_text()).items():
        assert hashlib.sha256((package / name).read_bytes()).hexdigest() == digest
    manifest = json.loads((package / 'sources.json').read_text())
    assert manifest['backend'] == 'c'
    flags = ['-std=c11', '-O2', *manifest['gccClangFlags'],
             *['-D' + d for d in manifest['definitions']],
             *['-I' + str(package / d) for d in manifest['includeDirectories']]]
    objects = []
    for name in manifest['sources']:
        obj = output / (Path(name).stem + '.o')
        run([args.cc, *flags, '-c', package / name, '-o', obj])
        objects.append(obj)
    library = output / 'libspeex_nb3.a'
    run([args.ar, 'rcs', library, *objects])
    libraries = [library]
    if args.cmake:
        if not args.ninja:
            parser.error('--cmake requires --ninja')
        cmake_output = output / 'cmake-generic'
        run([args.cmake, '-S', package, '-B', cmake_output, '-G', 'Ninja',
             '-DCMAKE_C_COMPILER=' + args.cc, '-DCMAKE_AR=' + args.ar,
             '-DCMAKE_MAKE_PROGRAM=' + args.ninja, '-DCMAKE_SYSTEM_NAME=Generic',
             '-DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY', '-DCMAKE_BUILD_TYPE=Release'])
        run([args.cmake, '--build', cmake_output])
        libraries.append(cmake_output / 'libspeex_nb3.a')
    consumer = output / ('decode.exe' if os.name == 'nt' else 'decode')
    reference = ROOT / 'build/reference' / ('decode.exe' if os.name == 'nt' else 'decode')
    streams = sorted((ROOT / 'reference/R4/data').glob('*.spxraw'))
    streams += sorted((ROOT / 'build/real-speech/streams').glob('*.spxraw'))
    rows = []
    for archive in libraries:
        # Only public exported includes, not private src/, are visible here.
        run([args.cc, '-std=c11', '-O2', '-DSPEEX_AVR_PROFILE',
             '-I' + str(package / 'include'), ROOT / 'tests/decode.c', archive,
             '-o', consumer, *([] if os.name == 'nt' else ['-lm'])])
        actual_rows = []
        for stream in streams:
            actual, oracle = output / 'actual.pcm', output / 'oracle.pcm'
            run([consumer, stream, actual])
            run([reference, stream, oracle])
            pcm = actual.read_bytes()
            assert pcm == oracle.read_bytes(), stream.name
            assert len(pcm) == len(stream.read_bytes()) // 20 * 320
            actual_rows.append({'stream': stream.name, 'frames': len(pcm) // 320,
                                'pcmSha256': hashlib.sha256(pcm).hexdigest()})
        if rows:
            assert actual_rows == rows, 'CMake and manifest archives must agree'
        rows = actual_rows
    report = {'backend': 'c', 'hostArchitecture': platform.machine(),
              'compiler': args.cc, 'archiver': args.ar,
              'sourceFiles': len(objects), 'staticArchiveBuilt': True,
              'cmakeGenericStaticArchiveBuiltAndExecuted': bool(args.cmake),
              'testedStaticArchives': len(libraries),
              'consumerUsesPublicIncludesOnly': True,
              'scratchInstrumentation': False,
              'exactS16AgainstUpstream': True, 'invalidCallsVerified': True,
              'frames': sum(r['frames'] for r in rows), 'streams': rows,
              'scope': 'Native host static-library execution; other MCU hardware/timing untested.'}
    (ROOT / 'build/portable-library.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'streams'}, indent=2))

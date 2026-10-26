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
    result=subprocess.run([str(v) for v in command],capture_output=True)
    if result.returncode:
        sys.stderr.write(result.stderr.decode(errors='replace'))
        result.check_returncode()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc', required=True)
    parser.add_argument('--ar', required=True)
    parser.add_argument('--cmake', help='Also build and test the exported CMake target')
    parser.add_argument('--ninja', help='Ninja executable for the optional CMake build')
    parser.add_argument('--package', type=Path, help='Verify an existing exported package')
    parser.add_argument('--wb', action='store_true', help='Also verify compact WB from the exported package')
    parser.add_argument('--enable-nb4', action='store_true', help='Export and verify NB11/WB12.8 as well as legacy profiles')
    args = parser.parse_args()
    output = Path(tempfile.mkdtemp(prefix='portable-check-', dir=ROOT / 'build'))
    if args.wb and not args.package:
        import build_wb
        package=output/'package'
        build_wb.export_c(package,args.enable_nb4)
    else:
        package = args.package.resolve() if args.package else build.export_c(output / 'package',args.enable_nb4)
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
    if args.wb:
        wb_rows=[]
        wb_streams=sorted((ROOT/'build/wb-corpus/streams').glob('*.spxraw'))
        assert wb_streams
        for archive in libraries:
            run([args.cc,'-std=c11','-O2','-D_CRT_SECURE_NO_WARNINGS',
                 '-I'+str(package/'include'),ROOT/'tests/wb_decode.c',archive,'-o',consumer])
            actual_rows=[]
            for stream in wb_streams:
                actual=output/'wb-actual.pcm'
                run([consumer,stream,actual])
                pcm=actual.read_bytes()
                assert pcm==(ROOT/'build/wb-corpus/oracle'/(stream.stem+'.pcm')).read_bytes()
                actual_rows.append(dict(stream=stream.name,frames=len(pcm)//640,
                    pcmSha256=hashlib.sha256(pcm).hexdigest()))
            if wb_rows:assert wb_rows==actual_rows
            wb_rows=actual_rows
            run([args.cc,'-std=c11','-O2','-D_CRT_SECURE_NO_WARNINGS',
                 '-I'+str(package/'include'),ROOT/'tests/wb_api.c',archive,'-o',consumer])
            run([consumer,wb_streams[-1]])
        report['wideband']=dict(profile='WB1-Q7-16',frames=sum(r['frames'] for r in wb_rows),
            streams=wb_rows,invalidCallsAndResetVerified=True,exactAgainstCompactProfileOracle=True)
    if args.enable_nb4:
        assert 'SPEEX_ENABLE_NB4=1' in manifest['definitions']
        higher=json.loads((ROOT/'build/higher-corpus/manifest.json').read_text(encoding='utf-8'))
        higher_rows=[]
        for archive in libraries:
            current=[]
            for wb,family in [(False,'nb4'),(True,'wb128')]:
                if wb and not args.wb:continue
                run([args.cc,'-std=c11','-O2','-DSPEEX_AVR_PROFILE',
                    '-I'+str(package/'include'),ROOT/('tests/wb_decode.c' if wb else 'tests/decode.c'),archive,'-o',consumer])
                for row in higher['streams']:
                    if row['family']!=family:continue
                    folder=ROOT/'build/higher-corpus'/family;stream=folder/'streams'/row['stream'];actual=output/'higher.pcm'
                    run([consumer,stream,actual,row['packetBytes']])
                    assert hashlib.sha256(actual.read_bytes()).hexdigest()==row['pcmSha256']
                    current.append(dict(family=family,stream=row['stream'],frames=row['frames'],pcmExact=True))
            # A separate consumer includes only the exported neutral public API.
            if args.wb:
                run([args.cc,'-std=c11','-O2','-I'+str(package/'include'),ROOT/'tests/decode_mixed.c',archive,'-o',consumer])
                for mixed in sorted((ROOT/'build/higher-native-final').glob('*.mixed')):
                    actual=output/'mixed.pcm';run([consumer,int(mixed.name.startswith('wb128')),mixed,actual])
                    assert actual.read_bytes()==mixed.with_suffix('.oracle.pcm').read_bytes()
            if higher_rows:assert higher_rows==current
            higher_rows=current
        report['higherProfiles']=dict(streams=higher_rows,frames=sum(r['frames'] for r in higher_rows),mixedModeAndRejectionChecks=args.wb)
    (ROOT / 'build/portable-library.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'streams'}, indent=2))

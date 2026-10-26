#!/usr/bin/env python3
"""Qualify the explicitly selected minimal fixed-IFFT mode on native and AVR."""
import argparse
import datetime
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_frontend as front
from verify_decoder import metrics
from audit_decoder_memory import device_memory
from study_fixed_precision import admissible
from generate_fixed_tables import generate

ROOT = front.ROOT
BUILD = ROOT.parents[1] / 'build/codec2/hybrid'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc', default='clang')
    parser.add_argument('--avr-gcc', default='avr-gcc')
    parser.add_argument('--node', default='node')
    parser.add_argument('--host-only', action='store_true')
    parser.add_argument('--frames', type=int)
    parser.add_argument('--record', action='store_true')
    args = parser.parse_args()
    if args.record and (args.host_only or args.frames): parser.error('--record requires complete AVR streams')
    BUILD.mkdir(parents=True, exist_ok=True)
    assert generate() == (ROOT / 'src/fixed_inverse_tables.inc').read_bytes()
    precision = json.loads((ROOT / 'reports/fixed-precision.json').read_text())
    assert precision['selection'] == {'component_bits': 16, 'twiddle_q': 9, 'wide_last': 0}
    for name, wanted in precision['sources'].items(): assert front.digest(ROOT / name) == wanted, name
    baseline = json.loads((ROOT / 'reports/compact-decoder.json').read_text())
    for name, wanted in baseline['sources'].items(): assert front.digest(ROOT / name) == wanted, name
    source = front.VENDOR / 'src'
    flags = ['-DCODEC2_FIXED_BITS=16', '-DCODEC2_FIXED_TWIDDLE_Q=9', '-DCODEC2_FIXED_WIDE_LAST=0']
    common = [args.cc, '-O2', '-fno-strict-aliasing', '-ffp-contract=off', '-D_CRT_SECURE_NO_WARNINGS',
              '-DCODEC2_FIXED_CHECKS=1', *flags, '-I'+str(ROOT/'include'), '-I'+str(ROOT/'src'), '-I'+str(source)]
    sources = [ROOT/'src/hybrid_decoder.c', ROOT/'src/fixed_inverse.c', ROOT/'src/compact_fft.c', ROOT/'src/parameters.c', source/'lsp.c']
    exe = '.exe' if os.name == 'nt' else ''
    libm = [] if os.name == 'nt' else ['-lm']
    program, api, fft = [BUILD/(name+exe) for name in ('decode', 'api', 'fft')]
    front.run([*common, *sources, ROOT/'tests/hybrid_decode.c', '-o', program, *libm])
    front.run([*common, *sources, ROOT/'tests/hybrid_api.c', '-o', api, *libm])
    front.run([*common, ROOT/'src/fixed_inverse.c', ROOT/'tests/fixed_inverse_fft.c',
               source/'kiss_fft.c', source/'kiss_fftr.c', '-o', fft, *libm])
    kernel = json.loads(front.run([fft], capture_output=True, text=True).stdout)
    assert kernel['snr_db'] >= 50
    legacy = ROOT/'AVR/Codec2_Tiny13_Quality_R2/tests'
    api_test = front.run([api, legacy/'speech.c2zx', legacy/'codec2_3200_8byte_frames.bin'], capture_output=True, text=True).stdout.strip()
    print(api_test, flush=True)
    streams = []
    for name, path in [('speech.c2zx', legacy/'speech.c2zx'), ('codec2_3200_8byte_frames.bin', legacy/'codec2_3200_8byte_frames.bin'), ('all-11333', front.BUILD/'frames.bin')]:
        old = next(s for s in baseline['streams'] if s['name'] == name)
        oracle = ROOT.parents[1]/'build/codec2/compact'/(name+'.upstream.pcm')
        assert front.digest(path) == old['packet_sha256'] and front.digest(oracle) == old['oracle_sha256']
        output = BUILD/(name+'.pcm')
        front.run([program, path, output])
        (BUILD/(name+'.upstream.pcm')).write_bytes(oracle.read_bytes())
        result = {'name': name, 'frames': path.stat().st_size//8, 'packet_sha256': front.digest(path),
                  'oracle_sha256': front.digest(oracle), 'output_sha256': front.digest(output), **metrics(output.read_bytes(), oracle.read_bytes())}
        assert admissible(result), result
        streams.append(result); print(json.dumps(result), flush=True)
    report = {'precision': precision['selection'], 'precision_study_sha256': front.digest(ROOT/'reports/fixed-precision.json'),
              'baseline_report_sha256': front.digest(ROOT/'reports/compact-decoder.json'),
              'host_compiler': front.run([args.cc, '--version'], capture_output=True, text=True).stdout.splitlines()[0],
              'kernel_test': kernel, 'api_test': api_test, 'streams': streams}
    if not args.host_only:
        output = BUILD/'atmega64a'; output.mkdir(exist_ok=True)
        memory = device_memory(args.avr_gcc, 'atmega64a')
        prefix = args.avr_gcc[:-3] if args.avr_gcc.endswith('gcc') else args.avr_gcc.replace('gcc.exe', '')
        front.run([args.avr_gcc, '-mmcu=atmega64a', '-Os', '-std=c99', '-fstack-usage', '-fno-strict-aliasing',
            '-ffunction-sections', '-fdata-sections', '-DCODEC2_FIXED_CHECKS=0', *flags,
            '-I'+str(ROOT/'include'), '-I'+str(ROOT/'src'), '-I'+str(source), *sources, ROOT/'tests/avr_hybrid.c',
            '-Wl,--gc-sections,-Map='+str(output/'decoder.map'),
            '-Wl,--defsym=__DATA_REGION_ORIGIN__='+str(0x800000+memory['RAMSTART']),
            '-Wl,--defsym=__DATA_REGION_LENGTH__='+str(memory['RAMEND']-memory['RAMSTART']+1),
            '-Wl,--defsym=__TEXT_REGION_LENGTH__='+str(memory['FLASHEND']+1), '-o', output/'decoder.elf', '-lm'], cwd=output)
        front.run([prefix+'objcopy', '-O', 'binary', output/'decoder.elf', output/'decoder.bin'])
        with (output/'symbols.txt').open('wb') as f: front.run([prefix+'nm', '-n', output/'decoder.elf'], stdout=f)
        report['avr_build'] = {'mcu': 'atmega64a', 'compiler': front.run([args.avr_gcc, '--version'], capture_output=True, text=True).stdout.splitlines()[0],
            'binary_sha256': front.digest(output/'decoder.bin'), 'manufacturer_header_memory': memory,
            'defines': [*flags, '-DCODEC2_FIXED_CHECKS=0'],
            'section_sizes': front.run([prefix+'size', '-A', output/'decoder.elf'], capture_output=True, text=True).stdout}
    front.dump(BUILD/'host-verification.json', report)
    if not args.host_only:
        front.run([args.node, ROOT/'tests/verify_hybrid_avr.mjs', *(['--frames', str(args.frames)] if args.frames else [])])
        report['avr_execution'] = json.loads((BUILD/'avr-execution.json').read_text())
    names = ['include/codec2_hybrid.h', 'src/hybrid_decoder.c', 'src/fixed_inverse.c', 'src/fixed_inverse.h',
             'src/fixed_inverse_tables.inc', 'src/fixed_table_access.h', 'src/table_access.h', 'tests/fixed_inverse_fft.c',
             'tests/hybrid_api.c', 'tests/hybrid_decode.c', 'tests/avr_hybrid.c', 'tests/verify_hybrid_avr.mjs',
             'tools/verify_hybrid.py', 'tools/generate_fixed_tables.py']
    report['sources'] = {**baseline['sources'], **{name: front.digest(ROOT/name) for name in names}}
    report['verified_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    report['scope'] = 'Full algorithm, fixed inverse FFT only; other stages remain float. No IRQ, board or real-time admission.'
    front.dump(BUILD/'verification.json', report)
    if args.record: front.dump(ROOT/'reports/hybrid-decoder.json', report)


if __name__ == '__main__':
    main()

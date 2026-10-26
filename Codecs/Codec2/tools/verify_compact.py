#!/usr/bin/env python3
"""Qualify full mode-3200 decoding with one FFT buffer and a small state."""
import argparse
import datetime
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_frontend as front
import verify_decoder as full
import generate_compact_tables
from audit_decoder_memory import device_memory

ROOT = front.ROOT
BUILD = ROOT.parents[1] / 'build/codec2/compact'
SOURCE = front.VENDOR / 'src'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc', default='clang')
    parser.add_argument('--avr-gcc', default='avr-gcc')
    parser.add_argument('--node', default='node')
    parser.add_argument('--host-only', action='store_true')
    parser.add_argument('--frames', type=int)
    parser.add_argument('--record', action='store_true')
    args = parser.parse_args()
    if args.record and (args.host_only or args.frames):
        parser.error('--record requires complete AVR streams')
    BUILD.mkdir(parents=True, exist_ok=True)
    if generate_compact_tables.generate(args.cc) != (ROOT / 'src/compact_tables.inc').read_bytes():
        raise RuntimeError('Compact ROM tables differ from pinned original generation')
    # Reuse the original-function oracle builder, in an independent output folder.
    full.BUILD = BUILD / 'oracle'
    selected = full.reference_sources(args.cc)
    common = [args.cc, '-O2', '-fno-strict-aliasing', '-ffp-contract=off', '-D_CRT_SECURE_NO_WARNINGS',
        '-I' + str(ROOT / 'include'), '-I' + str(ROOT / 'src'), '-I' + str(SOURCE),
        '-I' + str(full.BUILD / 'include')]
    libm = [] if os.name == 'nt' else ['-lm']
    exe = '.exe' if os.name == 'nt' else ''
    oracle = BUILD / ('upstream' + exe)
    kiss = [SOURCE / 'kiss_fft.c', SOURCE / 'kiss_fftr.c']
    front.run([*common, '-DCODEC2_MODE_EN_DEFAULT=0', '-DCODEC2_MODE_3200_EN=1', *selected,
        SOURCE / 'pack.c', SOURCE / 'codec2_fft.c', SOURCE / 'lsp.c', SOURCE / 'postfilter.c',
        *kiss, ROOT / 'tests/upstream_decode.c', '-o', oracle, *libm])
    fft_test = BUILD / ('fft' + exe)
    front.run([*common, ROOT / 'src/compact_fft.c', ROOT / 'tests/compact_fft.c', *kiss, '-o', fft_test, *libm])
    fft_result = front.run([fft_test], capture_output=True, text=True).stdout.strip()
    print(fft_result, flush=True)
    sources = [ROOT / 'src/compact_decoder.c', ROOT / 'src/compact_fft.c', ROOT / 'src/parameters.c', SOURCE / 'lsp.c']
    decoder = BUILD / ('decode' + exe)
    api = BUILD / ('api' + exe)
    front.run([*common, *sources, ROOT / 'tests/compact_decode.c', '-o', decoder, *libm])
    front.run([*common, *sources, ROOT / 'tests/compact_api.c', '-o', api, *libm])
    legacy = ROOT / 'AVR/Codec2_Tiny13_Quality_R2/tests'
    api_result = front.run([api, legacy / 'speech.c2zx', legacy / 'codec2_3200_8byte_frames.bin'], capture_output=True, text=True).stdout.strip()
    print(api_result, flush=True)
    streams = []
    inputs = [('speech.c2zx', legacy / 'speech.c2zx'), ('codec2_3200_8byte_frames.bin', legacy / 'codec2_3200_8byte_frames.bin'),
              ('all-11333', front.BUILD / 'frames.bin')]
    for name, path in inputs:
        expected, output = BUILD / (name + '.upstream.pcm'), BUILD / (name + '.pcm')
        front.run([oracle, path, expected])
        front.run([decoder, path, output])
        result = {'name': name, 'frames': path.stat().st_size // 8, 'packet_sha256': front.digest(path),
            'oracle_sha256': front.digest(expected), 'output_sha256': front.digest(output),
            **full.metrics(output.read_bytes(), expected.read_bytes())}
        print(json.dumps(result), flush=True)
        streams.append(result)
        assert output.read_bytes() == expected.read_bytes(), 'Compact native path must retain complete original PCM'
    report = {'upstream_commit': json.loads((front.VENDOR / 'UPSTREAM.json').read_text())['commit'],
        'host_compiler': front.run([args.cc, '--version'], capture_output=True, text=True).stdout.splitlines()[0],
        'fft_test': fft_result, 'api_test': api_result, 'streams': streams,
        'generated_reference_hashes': {p.name: front.digest(p) for p in selected}}
    if not args.host_only:
        mcu = 'atmega64a'
        output = BUILD / mcu
        output.mkdir(exist_ok=True)
        memory = device_memory(args.avr_gcc, mcu)
        prefix = args.avr_gcc[:-3] if args.avr_gcc.endswith('gcc') else args.avr_gcc.replace('gcc.exe', '')
        front.run([args.avr_gcc, '-mmcu=' + mcu, '-Os', '-std=c99', '-fstack-usage', '-fno-strict-aliasing',
            '-ffunction-sections', '-fdata-sections', '-I' + str(ROOT / 'include'), '-I' + str(SOURCE),
            *sources, ROOT / 'tests/avr_compact.c', '-Wl,--gc-sections,-Map=' + str(output / 'decoder.map'),
            '-Wl,--defsym=__DATA_REGION_ORIGIN__=' + str(0x800000 + memory['RAMSTART']),
            '-Wl,--defsym=__DATA_REGION_LENGTH__=' + str(memory['RAMEND'] - memory['RAMSTART'] + 1),
            '-Wl,--defsym=__TEXT_REGION_LENGTH__=' + str(memory['FLASHEND'] + 1), '-o', output / 'decoder.elf', '-lm'], cwd=output)
        front.run([prefix + 'objcopy', '-O', 'binary', output / 'decoder.elf', output / 'decoder.bin'])
        with (output / 'symbols.txt').open('wb') as handle:
            front.run([prefix + 'nm', '-n', output / 'decoder.elf'], stdout=handle)
        report['avr_build'] = {'mcu': mcu, 'binary_sha256': front.digest(output / 'decoder.bin'),
            'manufacturer_header_memory': memory,
            'compiler': front.run([args.avr_gcc, '--version'], capture_output=True, text=True).stdout.splitlines()[0],
            'section_sizes': front.run([prefix + 'size', '-A', output / 'decoder.elf'], capture_output=True, text=True).stdout}
    front.dump(BUILD / 'host-verification.json', report)
    if not args.host_only:
        front.run([args.node, ROOT / 'tests/verify_compact_avr.mjs', *(['--frames', str(args.frames)] if args.frames else [])])
        report['avr_execution'] = json.loads((BUILD / 'avr-execution.json').read_text())
    names = ('include/codec2_compact.h', 'src/compact_decoder.c', 'src/compact_fft.c', 'src/compact_fft.h',
        'src/compact_tables.inc', 'src/float_table_access.h', 'src/decoder_control.h', 'src/parameters.c',
        'tests/compact_fft.c', 'tests/compact_tables.c', 'tests/compact_api.c', 'tests/decoder_api.c', 'tests/compact_decode.c',
        'tests/avr_compact.c', 'tests/verify_compact_avr.mjs', 'tools/verify_compact.py', 'tools/generate_compact_tables.py',
        'vendor/codec2-1.2.0/UPSTREAM.json')
    report['sources'] = {name: front.digest(ROOT / name) for name in names}
    report['verified_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    report['scope'] = 'Full mode-3200 algorithm, one FFT buffer and Flash tables. No active-IRQ, real-time or physical board claim.'
    front.dump(BUILD / 'verification.json', report)
    if args.record:
        front.dump(ROOT / 'reports/compact-decoder.json', report)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Verify integer ten-LSP LPC reconstruction against pinned upstream and AVR ISA."""
import argparse
import datetime
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_frontend as front
import generate_cosine

ROOT = front.ROOT
BUILD = ROOT.parents[1] / 'build/codec2/lpc'


def vectors():
    expected = front.BUILD / 'expected.bin'
    prior = json.loads((front.BUILD / 'host-and-build.json').read_text())
    if front.digest(expected) != prior['expected_sha256']:
        raise RuntimeError('Run verify_frontend.py first; parameter oracle hash differs')
    records = expected.read_bytes()
    frames = [tuple(2 * x for x in struct.unpack_from('<10H', records, offset + 14))
              for offset in range(0, len(records), 34)]
    midway = [tuple((a + b) // 2 for a, b in zip(frames[i - 1], frames[i]))
              for i in range(1, len(frames))]
    cluster = [(i,) * 10 for i in range(640)]
    individual = []
    for field in range(10):
        for phase in range(640):
            row = list(range(32, 352, 32))
            row[field] = phase
            individual.append(tuple(row))
    boundaries = []
    for field in range(10):
        for phase in (0, 1, 159, 160, 161, 319, 320, 321, 479, 480, 481, 639, 640, 65535):
            row = list(range(32, 352, 32))
            row[field] = phase
            boundaries.append(tuple(row))
    cases = frames + midway + cluster + individual + boundaries
    # AVR subset retains both complete speech streams, their midpoints, all
    # clustered-root cosine phases and all per-root range-reduction boundaries.
    selected = (list(range(365)) + list(range(len(frames), len(frames) + 365))
                + list(range(len(frames) + len(midway), len(frames) + len(midway) + len(cluster)))
                + list(range(len(cases) - len(boundaries), len(cases))))
    (BUILD / 'vectors.bin').write_bytes(b''.join(struct.pack('<10H', *row) for row in cases))
    (BUILD / 'avr-vectors.bin').write_bytes(b''.join(struct.pack('<10H', *cases[i]) for i in selected))
    return cases, selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc', default='clang')
    parser.add_argument('--avr-gcc', default='avr-gcc')
    parser.add_argument('--node', default='node')
    parser.add_argument('--host-only', action='store_true')
    parser.add_argument('--record', action='store_true')
    args = parser.parse_args()
    if args.record and args.host_only:
        parser.error('--record requires AVR execution')
    BUILD.mkdir(parents=True, exist_ok=True)
    if (ROOT / 'src/cosine_q15.inc').read_bytes() != generate_cosine.contents():
        raise RuntimeError('Regenerate the cosine table')
    source = front.VENDOR / 'src'
    vendor = json.loads((front.VENDOR / 'UPSTREAM.json').read_text())
    for item in vendor['files']:
        if front.digest(front.VENDOR / item['path']) != item['sha256']:
            raise RuntimeError('Modified original source: ' + item['path'])
    cases, selected = vectors()
    program = BUILD / ('lpc.exe' if os.name == 'nt' else 'lpc')
    front.run([args.cc, '-O2', '-D_CRT_SECURE_NO_WARNINGS', '-I' + str(source),
               '-I' + str(ROOT / 'include'), source / 'lsp.c', ROOT / 'src/lpc.c',
               ROOT / 'tests/lpc.c', '-o', program, *([] if os.name == 'nt' else ['-lm'])])
    result = front.run([program, BUILD / 'vectors.bin', BUILD / 'expected.bin'], capture_output=True, text=True)
    print('Host:', result.stdout.strip(), flush=True)
    expected = (BUILD / 'expected.bin').read_bytes()
    assert len(expected) == len(cases) * 44
    (BUILD / 'avr-expected.bin').write_bytes(b''.join(expected[i * 44:(i + 1) * 44] for i in selected))
    report = {'upstream_commit': vendor['commit'], 'host': json.loads(result.stdout),
              'host_compiler': front.run([args.cc, '--version'], capture_output=True, text=True).stdout.splitlines()[0],
              'integer_format': 'Q15 cosine (nearest), Q23 coefficients, signed64 products; symmetric nearest product rounding and truncation at final /2',
              'vectors_sha256': front.digest(BUILD / 'vectors.bin'),
              'expected_sha256': front.digest(BUILD / 'expected.bin'),
              'avr_vectors_sha256': front.digest(BUILD / 'avr-vectors.bin'),
              'avr_expected_sha256': front.digest(BUILD / 'avr-expected.bin'),
              'avr_vector_count': len(selected), 'mcus': {}}
    if not args.host_only:
        prefix = args.avr_gcc[:-3] if args.avr_gcc.endswith('gcc') else args.avr_gcc.replace('gcc.exe', '')
        for mcu in ('attiny88', 'atmega328p'):
            output = BUILD / mcu
            output.mkdir(exist_ok=True)
            front.run([args.avr_gcc, '-mmcu=' + mcu, '-Os', '-std=c99', '-fstack-usage',
                       '-ffunction-sections', '-fdata-sections', '-I' + str(ROOT / 'include'),
                       ROOT / 'src/lpc.c', ROOT / 'tests/avr_lpc.c', '-Wl,--gc-sections,-Map=' + str(output / 'lpc.map'),
                       '-o', output / 'lpc.elf'], cwd=output)
            front.run([prefix + 'objcopy', '-O', 'binary', output / 'lpc.elf', output / 'lpc.bin'])
            with (output / 'symbols.txt').open('wb') as handle:
                front.run([prefix + 'nm', '-n', output / 'lpc.elf'], stdout=handle)
            report['mcus'][mcu] = {'binary_sha256': front.digest(output / 'lpc.bin'),
                'compiler': front.run([args.avr_gcc, '--version'], capture_output=True, text=True).stdout.splitlines()[0],
                'size': front.run([prefix + 'size', '-A', output / 'lpc.elf'], capture_output=True, text=True).stdout}
            macros = front.run([args.avr_gcc, '-mmcu=' + mcu, '-dM', '-E', '-include', 'avr/io.h', '-'],
                               input='', capture_output=True, text=True).stdout
            memory = {}
            for line in macros.splitlines():
                parts = line.split()
                if len(parts) == 3 and parts[1] in ('RAMSTART', 'RAMEND', 'FLASHEND'):
                    memory[parts[1]] = int(parts[2].strip('()'), 0)
            assert len(memory) == 3
            report['mcus'][mcu]['manufacturer_header_memory'] = memory
        front.dump(BUILD / 'build.json', report)
        front.run([args.node, ROOT / 'tests/verify_lpc_avr.mjs'])
        report['execution'] = json.loads((BUILD / 'avr-execution.json').read_text())
    report['sources'] = {name: front.digest(ROOT / name) for name in
                        ('src/lpc.c', 'src/cosine_q15.inc', 'src/table_access.h', 'include/codec2_lpc.h',
                         'tests/lpc.c', 'tests/avr_lpc.c', 'tests/verify_lpc_avr.mjs', 'tools/verify_lpc.py',
                         'tools/generate_cosine.py', 'vendor/codec2-1.2.0/src/lsp.c', 'vendor/codec2-1.2.0/UPSTREAM.json')}
    report['verified_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    report['scope'] = 'Integer ten-LSP to LPC stage; spectral amplitudes, phases, overlap/add, end-to-end quality, Tiny13 resource fit, and active-IRQ playback remain unproved.'
    front.dump(BUILD / 'verification.json', report)
    if args.record:
        front.dump(ROOT / 'reports/lpc-q23.json', report)


if __name__ == '__main__':
    main()

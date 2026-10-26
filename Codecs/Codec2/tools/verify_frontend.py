#!/usr/bin/env python3
"""Reproduce upstream/R3/C parameter checks and link GNU AVR baselines offline."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / 'vendor/codec2-1.2.0'
BUILD = ROOT.parents[1] / 'build/codec2/frontend'


def run(command, **kwargs):
    return subprocess.run([str(x) for x in command], check=True, **kwargs)


def dump(path, data):
    path.write_bytes((json.dumps(data, indent=2) + '\n').encode('utf-8'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def original_functions(source, signatures):
    """Keep complete upstream function bodies verbatim, including their notices.

    COFF linkers diagnose unresolved references in unused functions of the full
    quantise.c TU. Select only the oracle functions, without stubs or edits.
    """
    text = source.read_text(encoding='utf-8')
    result = text[:text.index('#include')] + '#include "quantise.h"\n#include "defines.h"\n'
    for signature in signatures:
        start = text.index(signature)
        at = text.index('{', start)
        depth = 1
        end = at + 1
        while depth:
            depth += (text[end] == '{') - (text[end] == '}')
            end += 1
        result += '\n' + text[start:end] + '\n'
    return result


def fixtures():
    baseline = ROOT / 'AVR/Codec2_Tiny13_Quality_R2/tests'
    data = b''.join((baseline / name).read_bytes() for name in ('speech.c2zx', 'codec2_3200_8byte_frames.bin'))
    rng = random.Random(0xC02DEC2)
    data += b''.join(rng.randbytes(8) for _ in range(10000))
    # Every possible value at every field position, in zero and maximum contexts.
    widths = [1, 1, 7, 5] + [5] * 10
    for maximum in (False, True):
        for field, width in enumerate(widths):
            for value in range(1 << width):
                values = [(1 << w) - 1 if maximum else 0 for w in widths]
                values[field] = value
                bits = 0
                for w, v in zip(widths, values):
                    bits = (bits << w) | (v ^ (v >> 1))
                data += bits.to_bytes(8, 'big')
    path = BUILD / 'frames.bin'
    path.write_bytes(data)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc', default='clang')
    parser.add_argument('--avr-gcc', default='avr-gcc')
    parser.add_argument('--node', default='node')
    parser.add_argument('--host-only', action='store_true')
    parser.add_argument('--record', action='store_true', help='Retain the complete verified report under reports/')
    args = parser.parse_args()
    if args.record and args.host_only:
        parser.error('--record requires complete AVR execution checks')
    BUILD.mkdir(parents=True, exist_ok=True)
    source = VENDOR / 'src'
    manifest = json.loads((VENDOR / 'UPSTREAM.json').read_text(encoding='utf-8'))
    for item in manifest['files']:
        if digest(VENDOR / item['path']) != item['sha256']:
            raise RuntimeError('Modified upstream source: ' + item['path'])
    exe = '.exe' if os.name == 'nt' else ''
    link = [] if os.name == 'nt' else ['-lm', '-Wl,--gc-sections']
    generator = BUILD / ('generate_codebook' + exe)
    run([args.cc, '-O2', '-D_CRT_SECURE_NO_WARNINGS', source / 'generate_codebook.c', '-o', generator, *link])
    with (BUILD / 'codebookd.c').open('wb') as output:
        run([generator, 'lsp_cbd', *[source / f'codebook/dlsp{i}.txt' for i in range(1, 11)]], stdout=output)
    (BUILD / 'quantise-params.c').write_bytes(original_functions(source / 'quantise.c',
        ['int lspd_bits(', 'void decode_lspds_scalar(']).encode('utf-8'))
    program = BUILD / ('frontend' + exe)
    run([args.cc, '-O2', '-ffunction-sections', '-fdata-sections',
         '-D_CRT_SECURE_NO_WARNINGS', '-I' + str(source), '-I' + str(ROOT / 'include'),
         source / 'pack.c', BUILD / 'quantise-params.c', BUILD / 'codebookd.c',
         ROOT / 'AVR/codec2_3200_full_parameters.c', ROOT / 'src/parameters.c',
         ROOT / 'tests/frontend.c', '-o', program, *link])
    inputs = fixtures()
    result = run([program, inputs, BUILD / 'expected.bin'], capture_output=True, text=True)
    print(result.stdout, end='')
    report = {'upstream_commit': manifest['commit'], 'host_compiler': run([args.cc, '--version'], capture_output=True, text=True).stdout.splitlines()[0],
              'packets': inputs.stat().st_size // 8, 'inputs_sha256': digest(inputs),
              'expected_sha256': digest(BUILD / 'expected.bin'), 'host_result': result.stdout.strip(),
              'source_hashes': {name: digest(ROOT / name) for name in ('include/codec2_3200.h', 'src/parameters.c', 'tests/frontend.c', 'tests/avr_frontend.c')}}
    if not args.host_only:
        avr_prefix = args.avr_gcc[:-3] if args.avr_gcc.endswith('gcc') else args.avr_gcc.replace('gcc.exe', '')
        for mcu in ('attiny13', 'atmega328p'):
            target = BUILD / mcu
            target.mkdir(exist_ok=True)
            run([args.avr_gcc, '-mmcu=' + mcu, '-Os', '-std=c99', '-fstack-usage',
                 '-ffunction-sections', '-fdata-sections', '-I' + str(ROOT / 'include'),
                 ROOT / 'src/parameters.c', ROOT / 'tests/avr_frontend.c',
                 '-Wl,--gc-sections,-Map=' + str(target / 'frontend.map'), '-o', target / 'frontend.elf'], cwd=target)
            with (target / 'symbols.txt').open('wb') as output:
                run([avr_prefix + 'nm', '-n', target / 'frontend.elf'], stdout=output)
            run([avr_prefix + 'objcopy', '-O', 'binary', target / 'frontend.elf', target / 'frontend.bin'])
            print(run([avr_prefix + 'size', target / 'frontend.elf'], capture_output=True, text=True).stdout, end='')
            report[mcu] = {'binary_sha256': digest(target / 'frontend.bin'), 'size': run([avr_prefix + 'size', '-A', target / 'frontend.elf'], capture_output=True, text=True).stdout}
        target = BUILD / 'r2-baseline'
        target.mkdir(exist_ok=True)
        run([args.avr_gcc, '-mmcu=attiny13', '-nostartfiles', '-nostdlib', '-x', 'assembler-with-cpp',
             ROOT / 'AVR/Codec2_Tiny13_Quality_R2/src/tiny13_pwm_resonator_demo.S',
             '-Wl,-e,reset,-Map=' + str(target / 'r2.map'), '-o', target / 'r2.elf'])
        run([avr_prefix + 'objcopy', '-O', 'binary', target / 'r2.elf', target / 'r2.bin'])
        with (target / 'symbols.txt').open('wb') as output:
            run([avr_prefix + 'nm', '-n', target / 'r2.elf'], stdout=output)
        original = ROOT / 'AVR/Codec2_Tiny13_Quality_R2/build/tiny13_quality_r2_demo.bin'
        report['r2_gnu'] = {'compiler': run([args.avr_gcc, '--version'], capture_output=True, text=True).stdout.splitlines()[0],
                            'flash_bytes': (target / 'r2.bin').stat().st_size, 'binary_sha256': digest(target / 'r2.bin'),
                            'identical_to_archived_llvm_binary': (target / 'r2.bin').read_bytes() == original.read_bytes(),
                            'shared_prefix_byte_differences': [{'offset': i, 'gnu': a, 'archived': b}
                                for i, (a, b) in enumerate(zip((target / 'r2.bin').read_bytes(), original.read_bytes())) if a != b],
                            'trailing_gnu_bytes': (target / 'r2.bin').read_bytes()[original.stat().st_size:].hex()}
        print('R2 GNU baseline:', report['r2_gnu'])
    dump(BUILD / 'host-and-build.json', report)
    if not args.host_only:
        for name in ('verify_frontend_avr.mjs', 'verify_r2_binary.mjs'):
            run([args.node, ROOT / 'tests' / name])
        complete = {'verified_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    'build': report,
                    'avr_frontend': json.loads((BUILD / 'avr-execution.json').read_text()),
                    'r2_machine_code': json.loads((BUILD / 'r2-machine-code.json').read_text()),
                    'scope': 'Mode-3200 parameter front end and archived approximate R2 baseline; full spectral/phase waveform decoder and active-IRQ streaming remain incomplete.',
                    'sources': {name: digest(ROOT / name) for name in
                        ('tools/verify_frontend.py', 'tests/verify_frontend_avr.mjs', 'tests/verify_r2_binary.mjs',
                         'vendor/codec2-1.2.0/UPSTREAM.json', 'package-lock.json')},
                    'generated_oracle_sha256': digest(BUILD / 'quantise-params.c'),
                    'generated_codebook_sha256': digest(BUILD / 'codebookd.c')}
        dump(BUILD / 'verification.json', complete)
        if args.record:
            (ROOT / 'reports').mkdir(exist_ok=True)
            dump(ROOT / 'reports/frontend-baseline.json', complete)


if __name__ == '__main__':
    main()

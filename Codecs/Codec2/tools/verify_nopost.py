#!/usr/bin/env python3
"""Measure the postfilter-off experiment against upstream with the same option."""
import argparse
import datetime
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_frontend as front
import verify_decoder as original
from verify_decoder import metrics
from study_fixed_precision import admissible
from audit_decoder_memory import device_memory
from generate_nopost import generate_decoder, generate_oracle

ROOT = front.ROOT
BUILD = ROOT.parents[1] / 'build/codec2/nopost'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', action='store_true')
    parser.add_argument('--frames', type=int)
    parser.add_argument('--host-only', action='store_true')
    args = parser.parse_args()
    if args.frames is not None and args.frames <= 0:
        parser.error('--frames must be positive')
    if args.record and (args.frames is not None or args.host_only):
        parser.error('--record requires all complete AVR streams')
    baseline = json.loads((ROOT / 'reports/matrix-decoder.json').read_text())
    study = json.loads((ROOT / 'reports/nopost-precision.json').read_text())
    assert study['baseline_report_sha256'] == front.digest(ROOT / 'reports/matrix-decoder.json')
    for name, wanted in study['sources'].items():
        assert front.digest(ROOT / name) == wanted, name
    assert study['selection'] is not None
    q = study['selection']['twiddle_q']
    guard = study['selection']['guard_bits']
    bits = study['selection']['fixed_bits']
    wide = study['selection']['wide_last']
    chosen = next(r for r in study['results'] if all(r[k] == v for k, v in study['selection'].items()))
    assert chosen['passes']
    assert generate_decoder() == (ROOT / 'src/nopost_decoder.c').read_bytes()
    assert generate_oracle() == (ROOT / 'tests/upstream_nopost.c').read_bytes()
    BUILD.mkdir(parents=True, exist_ok=True)
    vendor = front.VENDOR / 'src'
    flags = [x for x in baseline['avr_build']['defines'] if '_CHECKS=' not in x and not x.startswith(('-DCODEC2_FIXED_BITS=', '-DCODEC2_FIXED_WIDE_LAST=', '-DCODEC2_FIXED_TWIDDLE_Q=', '-DCODEC2_ANALYSIS_GUARD_BITS='))]
    flags.append('-DCODEC2_FIXED_TWIDDLE_Q=' + str(q))
    flags.append('-DCODEC2_ANALYSIS_GUARD_BITS=' + str(guard))
    flags.extend(['-DCODEC2_FIXED_BITS=' + str(bits), '-DCODEC2_FIXED_WIDE_LAST=' + str(wide)])
    includes = ['-I' + str(ROOT / 'include'), '-I' + str(ROOT / 'src'), '-I' + str(vendor)]
    sources = [ROOT / ('src/' + n) for n in ('nopost_decoder.c', 'adaptive_analysis.c',
        'matrix_analysis.c', 'fixed_inverse.c', 'compact_fft.c', 'parameters.c',
        'canonical_lpc.c', 'lpc_math.c')]
    suffix = '.exe' if os.name == 'nt' else ''
    libm = [] if os.name == 'nt' else ['-lm']
    checks = ['-DCODEC2_' + n + '_CHECKS=1' for n in ('LPC_MATH', 'ANALYSIS', 'FIXED', 'WEIGHT')]
    native = ['clang', '-O2', '-fno-strict-aliasing', '-ffp-contract=off',
              '-D_CRT_SECURE_NO_WARNINGS', *flags, *checks, *includes]
    program = BUILD / ('decode' + suffix)
    api = BUILD / ('api' + suffix)
    front.run([*native, *sources, ROOT / 'tests/hybrid_decode.c', '-o', program, *libm])
    front.run([*native, *sources, ROOT / 'tests/hybrid_api.c', '-o', api, *libm])
    legacy = ROOT / 'AVR/Codec2_Tiny13_Quality_R2/tests'
    api_test = front.run([api, legacy / 'speech.c2zx', legacy / 'codec2_3200_8byte_frames.bin'],
                         capture_output=True, text=True).stdout.strip()
    manifest = json.loads((front.VENDOR / 'UPSTREAM.json').read_text())
    for item in manifest['files']:
        assert front.digest(front.VENDOR / item['path']) == item['sha256']
    original.BUILD = BUILD / 'oracle'
    reference_sources = original.reference_sources('clang')
    oracle_program = BUILD / ('upstream' + suffix)
    front.run(['clang', '-O2', '-fno-strict-aliasing', '-ffp-contract=off',
        '-D_CRT_SECURE_NO_WARNINGS', '-DCODEC2_MODE_EN_DEFAULT=0', '-DCODEC2_MODE_3200_EN=1',
        *includes, '-I' + str(original.BUILD / 'include'), *reference_sources,
        *[vendor / n for n in ('pack.c', 'codec2_fft.c', 'lsp.c', 'postfilter.c', 'kiss_fft.c', 'kiss_fftr.c')],
        ROOT / 'tests/upstream_nopost.c', '-o', oracle_program, *libm])
    streams = []
    for previous in baseline['streams']:
        name = previous['name']
        if name == 'all-11333':
            packet = front.BUILD / 'frames.bin'
        elif name == 'conditioning-stress':
            packet = ROOT.parents[1] / 'build/codec2/matrix' / previous['packet_path']
        else:
            packet = legacy / name
        assert front.digest(packet) == previous['packet_sha256']
        local_packet = BUILD / (name + '.packets')
        local_packet.write_bytes(packet.read_bytes())
        output = BUILD / (name + '.pcm')
        oracle = BUILD / (name + '.upstream.pcm')
        front.run([oracle_program, packet, oracle])
        front.run([program, packet, output])
        default_pcm = ROOT.parents[1] / 'build/codec2/matrix' / (name + '.upstream.pcm')
        assert front.digest(default_pcm) == previous['oracle_sha256']
        record = {'name': name, 'packet_path': local_packet.name, 'frames': packet.stat().st_size // 8,
            'packet_sha256': front.digest(packet), 'oracle_sha256': front.digest(oracle),
            'output_sha256': front.digest(output), **metrics(output.read_bytes(), oracle.read_bytes()),
            'difference_from_default_postfiltered_upstream': metrics(output.read_bytes(), default_pcm.read_bytes())}
        # This gate checks implementation error against pf=0 upstream. It does
        # not accept the subjective quality change relative to the default pf=1.
        assert admissible(record), record
        if name != 'conditioning-stress':
            selected = next(s for s in chosen['streams'] if s['name'] == name)
            assert record['oracle_sha256'] == selected['oracle_sha256']
            assert record['output_sha256'] == selected['output_sha256']
        streams.append(record)
        print(json.dumps(record), flush=True)
    assert [s['name'] for s in streams] == ['speech.c2zx', 'codec2_3200_8byte_frames.bin', 'all-11333', 'conditioning-stress']
    report = {'api_test': api_test, 'streams': streams, 'precision': {**baseline['precision'], 'guard_bits': guard},
        'fixed_precision': study['selection'], 'precision_study_sha256': front.digest(ROOT / 'reports/nopost-precision.json'),
        'baseline_report_sha256': front.digest(ROOT / 'reports/matrix-decoder.json'),
        'upstream_manifest_sha256': front.digest(front.VENDOR / 'UPSTREAM.json'),
        'oracle_binary_sha256': front.digest(oracle_program),
        'host_compiler': front.run(['clang', '--version'], capture_output=True, text=True).stdout.splitlines()[0],
        'quality_scope': 'LPC postfilter/bass boost disabled. Numerical gate is to upstream pf=0 only. Perceived quality versus default pf=1 is unqualified; no listening-panel or live-speech evidence.'}
    if not args.host_only:
        target = BUILD / 'atmega64a'
        target.mkdir(exist_ok=True)
        memory = device_memory('avr-gcc', 'atmega64a')
        release = ['-DCODEC2_' + n + '_CHECKS=0' for n in ('LPC_MATH', 'ANALYSIS', 'FIXED', 'WEIGHT')]
        front.run(['avr-gcc', '-mmcu=atmega64a', '-Os', '-std=c99', '-fstack-usage',
            '-fno-strict-aliasing', '-ffunction-sections', '-fdata-sections', *flags, *release, *includes,
            *sources, ROOT / 'tests/avr_hybrid.c', '-Wl,--gc-sections,-Map=' + str(target / 'decoder.map'),
            '-Wl,--defsym=__DATA_REGION_ORIGIN__=' + str(0x800000 + memory['RAMSTART']),
            '-Wl,--defsym=__DATA_REGION_LENGTH__=' + str(memory['RAMEND'] - memory['RAMSTART'] + 1),
            '-Wl,--defsym=__TEXT_REGION_LENGTH__=' + str(memory['FLASHEND'] + 1), '-o', target / 'decoder.elf', '-lm'], cwd=target)
        front.run(['avr-objcopy', '-O', 'binary', target / 'decoder.elf', target / 'decoder.bin'])
        with (target / 'symbols.txt').open('wb') as out:
            front.run(['avr-nm', '-n', target / 'decoder.elf'], stdout=out)
        report['avr_build'] = {'mcu': 'atmega64a', 'compiler': front.run(['avr-gcc', '--version'], capture_output=True, text=True).stdout.splitlines()[0],
            'binary_sha256': front.digest(target / 'decoder.bin'), 'manufacturer_header_memory': memory, 'defines': flags + release}
        front.dump(BUILD / 'host-verification.json', report)
        front.run(['node', ROOT / 'tests/verify_nopost_avr.mjs', *(['--frames', str(args.frames)] if args.frames is not None else [])])
        report['avr_execution'] = json.loads((BUILD / 'avr-execution.json').read_text())
    names = ['src/nopost_decoder.c', 'tests/upstream_nopost.c', 'tests/verify_nopost_avr.mjs',
             'tools/generate_nopost.py', 'tools/prepare_nopost_oracle.py', 'tools/verify_nopost.py', 'tests/hybrid_api.c', 'tests/hybrid_decode.c', 'tests/avr_hybrid.c']
    report['sources'] = {**study['sources'], **{n: front.digest(ROOT / n) for n in names}}
    report['verified_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    front.dump(ROOT / 'reports/nopost-decoder.json' if args.record else BUILD / 'verification.json', report)


if __name__ == '__main__':
    main()

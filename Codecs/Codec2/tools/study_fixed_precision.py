#!/usr/bin/env python3
"""Measure component/twiddle precision against the full, pinned PCM corpus."""
import argparse
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_frontend as front
from verify_decoder import metrics
from generate_fixed_tables import generate

ROOT = front.ROOT
BUILD = ROOT.parents[1] / 'build/codec2/fixed-inverse'


def admissible(result):
    return result['max_absolute_error'] <= 256 and (result['snr_db'] is None or result['snr_db'] >= 50 or result['max_absolute_error'] <= 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc', default='clang')
    parser.add_argument('--record', action='store_true')
    args = parser.parse_args()
    BUILD.mkdir(parents=True, exist_ok=True)
    assert generate() == (ROOT / 'src/fixed_inverse_tables.inc').read_bytes()
    baseline = json.loads((ROOT / 'reports/compact-decoder.json').read_text())
    for p, wanted in baseline['sources'].items():
        assert front.digest(ROOT / p) == wanted, p
    oracle_build = ROOT.parents[1] / 'build/codec2/compact'
    legacy = ROOT / 'AVR/Codec2_Tiny13_Quality_R2/tests'
    corpus = [('speech.c2zx', legacy / 'speech.c2zx'), ('codec2_3200_8byte_frames.bin', legacy / 'codec2_3200_8byte_frames.bin'),
              ('all-11333', front.BUILD / 'frames.bin')]
    expected = {}
    for name, path in corpus:
        record = next(s for s in baseline['streams'] if s['name'] == name)
        pcm = oracle_build / (name + '.upstream.pcm')
        assert front.digest(path) == record['packet_sha256'] and front.digest(pcm) == record['oracle_sha256']
        expected[name] = pcm.read_bytes()
    common = [args.cc, '-O2', '-fno-strict-aliasing', '-ffp-contract=off', '-D_CRT_SECURE_NO_WARNINGS',
              '-DCODEC2_FIXED_CHECKS=1',
              '-I' + str(ROOT / 'include'), '-I' + str(ROOT / 'src'), '-I' + str(front.VENDOR / 'src')]
    sources = [ROOT / 'src/fixed_inverse.c', ROOT / 'src/hybrid_decoder.c', ROOT / 'src/compact_fft.c',
               ROOT / 'src/parameters.c', front.VENDOR / 'src/lsp.c', ROOT / 'tests/hybrid_decode.c']
    cases = [(8, 14, 0), (8, 14, 1)] + [(16, q, wide) for q in range(6, 15) for wide in (0, 1)] + [(24, 14, 1), (32, 14, 0)]
    results = []
    for bits, q, wide in cases:
        tag = f'i{bits}-q{q}-w{wide}'
        program = BUILD / (tag + ('.exe' if os.name == 'nt' else ''))
        front.run([*common, f'-DCODEC2_FIXED_BITS={bits}', f'-DCODEC2_FIXED_TWIDDLE_Q={q}', f'-DCODEC2_FIXED_WIDE_LAST={wide}',
                   *sources, '-o', program, *([] if os.name == 'nt' else ['-lm'])])
        streams = []
        for name, path in corpus:
            output = BUILD / (tag + '-' + name + '.pcm')
            front.run([program, path, output], capture_output=True)
            metric = metrics(output.read_bytes(), expected[name])
            streams.append({'name': name, 'output_sha256': front.digest(output), **metric, 'passes': admissible(metric)})
        record = {'component_bits': bits, 'twiddle_q': q, 'wide_last': wide, 'streams': streams,
                  'passes': all(s['passes'] for s in streams)}
        results.append(record)
        print(json.dumps({'bits': bits, 'q': q, 'wide': wide, 'passes': record['passes'], 'stress': streams[-1]}), flush=True)
    names = ['include/codec2_hybrid.h', 'src/hybrid_decoder.c', 'src/fixed_inverse.c', 'src/fixed_inverse.h',
             'src/fixed_inverse_tables.inc', 'src/fixed_table_access.h', 'tests/hybrid_decode.c',
             'tools/generate_fixed_tables.py', 'tools/study_fixed_precision.py']
    report = {'baseline_report_sha256': front.digest(ROOT / 'reports/compact-decoder.json'),
              'host_compiler': front.run([args.cc, '--version'], capture_output=True, text=True).stdout.splitlines()[0],
              'sources': {p: front.digest(ROOT / p) for p in names},
              'numerical_gate': {'minimum_snr_db': 50, 'maximum_absolute_error_pcm16': 256},
              'selection': {k: min((r for r in results if r['passes']), key=lambda r: (r['component_bits'], r['wide_last'], r['twiddle_q']))[k] for k in ('component_bits', 'twiddle_q', 'wide_last')},
              'results': results, 'scope': 'Native full decoder precision study with checked intermediates; 11333 packets plus two separately reset streams. No AVR speed or IRQ admission.'}
    destination = ROOT / 'reports/fixed-precision.json' if args.record else BUILD / 'precision.json'
    front.dump(destination, report)


if __name__ == '__main__':
    main()

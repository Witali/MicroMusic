#!/usr/bin/env python3
"""Reselect IFFT precision and conditioning guard with the LPC postfilter off."""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_frontend as front
from verify_decoder import metrics
from study_fixed_precision import admissible
from generate_nopost import generate_decoder, generate_oracle

ROOT = front.ROOT
BUILD = ROOT.parents[1] / 'build/codec2/nopost-study'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', action='store_true')
    args = parser.parse_args()
    baseline = json.loads((ROOT / 'reports/matrix-decoder.json').read_text())
    for name, wanted in baseline['sources'].items():
        assert front.digest(ROOT / name) == wanted, name
    assert generate_decoder() == (ROOT / 'src/nopost_decoder.c').read_bytes()
    assert generate_oracle() == (ROOT / 'tests/upstream_nopost.c').read_bytes()
    BUILD.mkdir(parents=True, exist_ok=True)
    flags = [x for x in baseline['avr_build']['defines'] if '_CHECKS=' not in x and not x.startswith(('-DCODEC2_FIXED_BITS=', '-DCODEC2_FIXED_WIDE_LAST=', '-DCODEC2_FIXED_TWIDDLE_Q=', '-DCODEC2_ANALYSIS_GUARD_BITS='))]
    flags += ['-DCODEC2_' + n + '_CHECKS=1' for n in ('LPC_MATH', 'ANALYSIS', 'FIXED', 'WEIGHT')]
    sources = [ROOT / ('src/' + n) for n in ('nopost_decoder.c', 'adaptive_analysis.c',
        'matrix_analysis.c', 'fixed_inverse.c', 'compact_fft.c', 'parameters.c', 'canonical_lpc.c', 'lpc_math.c')]
    inputs = ROOT.parents[1] / 'build/codec2/nopost'
    corpus = []
    for name in ('speech.c2zx', 'codec2_3200_8byte_frames.bin', 'all-11333'):
        packet = inputs / (name + '.packets')
        assert front.digest(packet) == next(s for s in baseline['streams'] if s['name'] == name)['packet_sha256']
        oracle = inputs / (name + '.upstream.pcm')
        corpus.append((name, packet, oracle))
    results = []
    cases = [(16, 0, q, guard) for q in range(9, 15) for guard in range(14, 19)]
    cases += [(16, 1, q, 14) for q in range(9, 15)]
    cases += [(24, 0, q, 18) for q in range(9, 15)]
    for bits, wide, q, guard in cases:
        tag = f'b{bits}-w{wide}-q{q}-g{guard}'
        program = BUILD / (tag + ('.exe' if os.name == 'nt' else ''))
        front.run(['clang', '-O2', '-fno-strict-aliasing', '-ffp-contract=off',
            '-D_CRT_SECURE_NO_WARNINGS', *flags, '-DCODEC2_FIXED_TWIDDLE_Q=' + str(q),
            '-DCODEC2_FIXED_BITS=' + str(bits), '-DCODEC2_FIXED_WIDE_LAST=' + str(wide),
            '-DCODEC2_ANALYSIS_GUARD_BITS=' + str(guard),
            *['-I' + str(ROOT / n) for n in ('include', 'src', 'vendor/codec2-1.2.0/src')],
            *sources, ROOT / 'tests/hybrid_decode.c', '-o', program, *([] if os.name == 'nt' else ['-lm'])])
        streams = []
        for name, packet, oracle in corpus:
            output = BUILD / (tag + '-' + name + '.pcm')
            front.run([program, packet, output], capture_output=True, text=True)
            record = {'name': name, **metrics(output.read_bytes(), oracle.read_bytes()),
                'packet_sha256': front.digest(packet), 'oracle_sha256': front.digest(oracle),
                'output_sha256': front.digest(output)}
            record['passes'] = admissible(record)
            streams.append(record)
        record = {'fixed_bits': bits, 'wide_last': wide, 'twiddle_q': q, 'guard_bits': guard, 'streams': streams, 'passes': all(s['passes'] for s in streams)}
        results.append(record)
        print(json.dumps({'bits': bits, 'wide': wide, 'q': q, 'guard': guard, 'passes': record['passes'], 'mixed_max': streams[-1]['max_absolute_error'], 'mixed_snr': streams[-1]['snr_db']}), flush=True)
    passing = [r for r in results if r['passes']]
    selection = {k: min(passing, key=lambda r: (r['fixed_bits'], r['wide_last'], r['twiddle_q'], -r['guard_bits']))[k] for k in ('fixed_bits', 'wide_last', 'twiddle_q', 'guard_bits')} if passing else None
    names = ['tools/study_nopost_precision.py', 'src/nopost_decoder.c', 'tests/upstream_nopost.c', 'tools/generate_nopost.py']
    report = {'baseline_report_sha256': front.digest(ROOT / 'reports/matrix-decoder.json'),
        'selection': selection, 'results': results,
        'sources': {**baseline['sources'], **{n: front.digest(ROOT / n) for n in names}},
        'scope': 'Native implementation precision to upstream pf=0. 42 choices: fixed16 Q9..14 guard14..18; fixed16 wide-last Q9..14 guard14; fixed24 Q9..14 guard18. Select lowest passing bits, wide-last, Q then highest guard; not a measured speed optimum. Other formats fixed. Not subjective quality, global precision minimum or AVR admission.'}
    front.dump(ROOT / 'reports/nopost-precision.json' if args.record else BUILD / 'verification.json', report)


if __name__ == '__main__':
    main()

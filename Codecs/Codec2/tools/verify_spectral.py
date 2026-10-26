#!/usr/bin/env python3
"""Qualify the fixed gamma-weighted LPC spectrum in the complete decoder."""
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
from generate_fifth_tables import generate as fifth_tables

ROOT = front.ROOT
BUILD = ROOT.parents[1] / 'build/codec2/spectral'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc', default='clang')
    parser.add_argument('--avr-gcc', default='avr-gcc')
    parser.add_argument('--node', default='node')
    parser.add_argument('--host-only', action='store_true')
    parser.add_argument('--frames', type=int)
    parser.add_argument('--record', action='store_true')
    parser.add_argument('--split24', action='store_true', help='Experiment with decomposed 24-bit multiplication')
    parser.add_argument('--avr-int24', action='store_true', help='Experiment with GNU AVR three-byte storage')
    parser.add_argument('--legacy-round', action='store_true', help='Use original int64 magnitude rounding')
    args = parser.parse_args()
    if args.record and (args.host_only or args.frames): parser.error('--record requires complete AVR streams')
    BUILD.mkdir(parents=True, exist_ok=True)
    assert generate() == (ROOT / 'src/fixed_inverse_tables.inc').read_bytes()
    weight_study=json.loads((ROOT/'reports/weight-direct-precision.json').read_text())
    for name,wanted in weight_study['sources'].items(): assert front.digest(ROOT/name)==wanted,name
    assert weight_study['selection']=={'component_bits':24,'twiddle_q':22,'ifft_twiddle_q':10,'direct_pair':True}
    root_study=json.loads((ROOT/'reports/postfilter-precision.json').read_text())
    for name,wanted in root_study['sources'].items(): assert front.digest(ROOT/name)==wanted,name
    root_precision=root_study['selection']
    generated=BUILD/'include'; generated.mkdir(exist_ok=True)
    table=generated/'fixed_fifth_tables.inc'
    table.write_bytes(fifth_tables(root_precision['q'],root_precision['table_bits']))
    body=(ROOT/'src/compact_decoder.c').read_text()
    assert body.count('powf(')==1 and 'powf(rw, 0.2f)' in body
    precision = json.loads((ROOT / 'reports/fixed-precision.json').read_text())
    assert precision['selection'] == {'component_bits': 16, 'twiddle_q': 9, 'wide_last': 0}
    for name, wanted in precision['sources'].items(): assert front.digest(ROOT / name) == wanted, name
    baseline = json.loads((ROOT / 'reports/compact-decoder.json').read_text())
    for name, wanted in baseline['sources'].items(): assert front.digest(ROOT / name) == wanted, name
    source = front.VENDOR / 'src'
    flags = ['-DCODEC2_FIXED_BITS=16', '-DCODEC2_FIXED_TWIDDLE_Q=10', '-DCODEC2_FIXED_WIDE_LAST=0']
    flags += ['-DCODEC2_ROOT_Q='+str(root_precision['q']), '-DCODEC2_ROOT_TABLE_BITS='+str(root_precision['table_bits'])]
    flags += ['-DCODEC2_WEIGHT_BITS=24','-DCODEC2_WEIGHT_TWIDDLE_Q=22','-DCODEC2_WEIGHT_SPLIT24='+str(int(args.split24)),
              '-DCODEC2_WEIGHT_DIRECT_PAIR=1','-DCODEC2_WEIGHT_ROUND_LEGACY='+str(int(args.legacy_round))]
    common = [args.cc, '-O2', '-fno-strict-aliasing', '-ffp-contract=off', '-D_CRT_SECURE_NO_WARNINGS',
              '-DCODEC2_FIXED_CHECKS=1', '-DCODEC2_WEIGHT_CHECKS=1', *flags, '-I'+str(generated), '-I'+str(ROOT/'include'), '-I'+str(ROOT/'src'), '-I'+str(source)]
    sources = [ROOT/'src/spectral_decoder.c', ROOT/'src/fixed_weight.c', ROOT/'src/fixed_fifth.c', ROOT/'src/fixed_inverse.c', ROOT/'src/compact_fft.c', ROOT/'src/parameters.c', source/'lsp.c']
    exe = '.exe' if os.name == 'nt' else ''
    libm = [] if os.name == 'nt' else ['-lm']
    program, api, fft = [BUILD/(name+exe) for name in ('decode', 'api', 'fft')]
    front.run([*common, *sources, ROOT/'tests/hybrid_decode.c', '-o', program, *libm])
    front.run([*common, *sources, ROOT/'tests/hybrid_api.c', '-o', api, *libm])
    front.run([*common, ROOT/'src/fixed_inverse.c', ROOT/'tests/fixed_inverse_fft.c',
               source/'kiss_fft.c', source/'kiss_fftr.c', '-o', fft, *libm])
    kernel = json.loads(front.run([fft], capture_output=True, text=True).stdout)
    assert kernel['snr_db'] >= 50
    split_program=BUILD/('mul24'+exe)
    front.run([*common,ROOT/'tests/weight_mul24.c','-o',split_program,*libm])
    split_test=front.run([split_program],capture_output=True,text=True).stdout.strip()
    round_program=BUILD/('round'+exe)
    front.run([*common,ROOT/'tests/weight_round.c','-o',round_program,*libm])
    round_test=front.run([round_program],capture_output=True,text=True).stdout.strip()
    weighted_program=BUILD/('weight'+exe)
    front.run([*common,ROOT/'src/fixed_weight.c',ROOT/'tests/fixed_weight.c',source/'kiss_fft.c',source/'kiss_fftr.c','-o',weighted_program,*libm])
    weighted_test=json.loads(front.run([weighted_program],capture_output=True,text=True).stdout)
    root_program=BUILD/('root'+exe)
    front.run([*common,ROOT/'src/fixed_fifth.c',ROOT/'tests/fixed_fifth.c','-o',root_program,*libm])
    root_test=json.loads(front.run([root_program],capture_output=True,text=True).stdout)
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
        chosen=next(s for s in weight_study['results'] if s['component_bits']==24 and s['twiddle_q']==22 and s['ifft_twiddle_q']==10)
        assert result['output_sha256']==next(s for s in chosen['streams'] if s['name']==name)['output_sha256'], 'Optimized C must preserve the checked wide reference PCM'
        streams.append(result); print(json.dumps(result), flush=True)
    report = {'precision': precision['selection'], 'precision_study_sha256': front.digest(ROOT/'reports/fixed-precision.json'),
              'baseline_report_sha256': front.digest(ROOT/'reports/compact-decoder.json'),
              'host_compiler': front.run([args.cc, '--version'], capture_output=True, text=True).stdout.splitlines()[0],
              'kernel_test': kernel, 'api_test': api_test, 'streams': streams}
    report['precision']={'component_bits':16,'twiddle_q':10,'wide_last':0}
    report.update({'weight_precision':weight_study['selection'],'weight_study_sha256':front.digest(ROOT/'reports/weight-direct-precision.json'),'weighted_test':weighted_test,'split_test':split_test,'round_test':round_test,'split24':args.split24,'avr_int24':args.avr_int24,'legacy_round':args.legacy_round})
    report.update({'root_precision':root_precision,'root_study_sha256':front.digest(ROOT/'reports/postfilter-precision.json'),'root_table_sha256':front.digest(table),'root_test':root_test})
    if not args.host_only:
        output = BUILD/'atmega64a'; output.mkdir(exist_ok=True)
        memory = device_memory(args.avr_gcc, 'atmega64a')
        prefix = args.avr_gcc[:-3] if args.avr_gcc.endswith('gcc') else args.avr_gcc.replace('gcc.exe', '')
        front.run([args.avr_gcc, '-mmcu=atmega64a', '-Os', '-std=c99', '-fstack-usage', '-fno-strict-aliasing',
            '-ffunction-sections', '-fdata-sections', '-DCODEC2_FIXED_CHECKS=0', '-DCODEC2_WEIGHT_CHECKS=0', '-DCODEC2_WEIGHT_AVR_INT24='+str(int(args.avr_int24)), *flags, '-I'+str(generated),
            '-I'+str(ROOT/'include'), '-I'+str(ROOT/'src'), '-I'+str(source), *sources, ROOT/'tests/avr_hybrid.c',
            '-Wl,--gc-sections,-Map='+str(output/'decoder.map'),
            '-Wl,--defsym=__DATA_REGION_ORIGIN__='+str(0x800000+memory['RAMSTART']),
            '-Wl,--defsym=__DATA_REGION_LENGTH__='+str(memory['RAMEND']-memory['RAMSTART']+1),
            '-Wl,--defsym=__TEXT_REGION_LENGTH__='+str(memory['FLASHEND']+1), '-o', output/'decoder.elf', '-lm'], cwd=output)
        front.run([prefix+'objcopy', '-O', 'binary', output/'decoder.elf', output/'decoder.bin'])
        with (output/'symbols.txt').open('wb') as f: front.run([prefix+'nm', '-n', output/'decoder.elf'], stdout=f)
        report['avr_build'] = {'mcu': 'atmega64a', 'compiler': front.run([args.avr_gcc, '--version'], capture_output=True, text=True).stdout.splitlines()[0],
            'binary_sha256': front.digest(output/'decoder.bin'), 'manufacturer_header_memory': memory,
            'defines': [*flags, '-DCODEC2_FIXED_CHECKS=0','-DCODEC2_WEIGHT_CHECKS=0','-DCODEC2_WEIGHT_AVR_INT24='+str(int(args.avr_int24))],
            'section_sizes': front.run([prefix+'size', '-A', output/'decoder.elf'], capture_output=True, text=True).stdout}
    front.dump(BUILD/'host-verification.json', report)
    if not args.host_only:
        front.run([args.node, ROOT/'tests/verify_spectral_avr.mjs', *(['--frames', str(args.frames)] if args.frames else [])])
        report['avr_execution'] = json.loads((BUILD/'avr-execution.json').read_text())
    names = ['include/codec2_hybrid.h', 'src/hybrid_decoder.c', 'src/fixed_inverse.c', 'src/fixed_inverse.h',
             'src/fixed_inverse_tables.inc', 'src/fixed_table_access.h', 'src/table_access.h', 'tests/fixed_inverse_fft.c',
             'tests/hybrid_api.c', 'tests/hybrid_decode.c', 'tests/avr_hybrid.c', 'tests/verify_hybrid_avr.mjs',
             'tools/verify_hybrid.py', 'tools/generate_fixed_tables.py']
    names += ['src/fixed_fifth.c','src/fixed_fifth.h','src/fixed_fifth_tables.inc','src/hybrid_postfilter.c','tests/fixed_fifth.c','tests/verify_postfilter_avr.mjs','tools/generate_fifth_tables.py','tools/verify_postfilter.py']
    names += ['src/fixed_weight.c','src/fixed_weight.h','src/fixed_weight_tables.inc','src/weight_mul24.h','src/weight_round.h','src/spectral_table_access.h','src/spectral_decoder.c','tests/fixed_weight.c','tests/weight_mul24.c','tests/weight_round.c','tests/verify_spectral_avr.mjs','tools/verify_spectral.py']
    report['sources'] = {**baseline['sources'], **{name: front.digest(ROOT/name) for name in names}}
    report['verified_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    report['scope'] = 'Full algorithm; fixed weighted LPC spectrum, inverse FFT and postfilter power. Base LPC spectrum and phase still float. No IRQ, board or real-time admission.'
    front.dump(BUILD/'verification.json', report)
    if args.record: front.dump(ROOT/'reports/spectral-decoder.json', report)


if __name__ == '__main__':
    main()

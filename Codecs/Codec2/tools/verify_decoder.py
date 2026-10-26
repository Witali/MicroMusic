#!/usr/bin/env python3
"""Build an original upstream waveform oracle and the complete portable decoder."""
import argparse
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_frontend as front
from audit_decoder_memory import device_memory

ROOT = front.ROOT
BUILD = ROOT.parents[1] / 'build/codec2/decoder'
VENDOR = front.VENDOR / 'src'


def function(source, signature):
    """Last signature occurrence avoids codec2.c's earlier forward declaration."""
    text = source.read_text(encoding='utf-8')
    start = text.rindex(signature)
    at = text.index('{', start)
    depth, end = 1, at + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end] + '\n'


def reference_sources(cc):
    source = BUILD / 'reference'
    source.mkdir(parents=True, exist_ok=True)
    inc = BUILD / 'include/codec2'
    inc.mkdir(parents=True, exist_ok=True)
    (inc / 'version.h').write_bytes(b'#define CODEC2_VERSION "1.2.0"\n')
    selections = {
        'codec2': ('void codec2_encode_3200(', ['static void ear_protection(', 'void synthesise_one_frame(', 'void codec2_decode_3200(']),
        'quantise': ('int lsp_bits(', ['int lspd_bits(', 'void decode_lspds_scalar(', 'float decode_Wo(', 'float decode_energy(',
                    'void lpc_post_filter(', 'void aks_to_M2(', 'void apply_lpc_correction(']),
        'interp': ('float sample_log_amp(', ['void interp_Wo2(', 'void interp_Wo(', 'float interp_energy(', 'void interpolate_lsp_ver2(']),
        'phase': ('void sample_phase(', ['void sample_phase(', 'void phase_synth_zero_order(']),
        'sine': ('C2CONST c2const_create(', ['C2CONST c2const_create(', 'void make_synthesis_window(', 'void synthesise(', 'int codec2_rand('])}
    selected = []
    for name, (first, signatures) in selections.items():
        original = VENDOR / (name + '.c')
        text = original.read_text(encoding='utf-8')
        prefix = text[:text.index(first)]
        if name == 'sine':
            assert 'static unsigned long next = 1;' in text
            prefix += '\nstatic unsigned long next = 1;\n'
        target = source / (name + '.c')
        target.write_bytes((prefix + '\n'.join(function(original, s) for s in signatures)).encode('utf-8'))
        selected.append(target)
    exe = '.exe' if os.name == 'nt' else ''
    generator = BUILD / ('generate_codebook' + exe)
    front.run([cc, '-O2', '-D_CRT_SECURE_NO_WARNINGS', VENDOR / 'generate_codebook.c', '-o', generator,
               *([] if os.name == 'nt' else ['-lm'])])
    with (source / 'codebookd.c').open('wb') as output:
        front.run([generator, 'lsp_cbd', *[VENDOR / f'codebook/dlsp{i}.txt' for i in range(1, 11)]], stdout=output)
    return selected + [source / 'codebookd.c']


def metrics(actual, expected):
    assert len(actual) == len(expected) and len(actual) % 2 == 0
    x = struct.unpack('<' + 'h' * (len(actual) // 2), actual)
    y = struct.unpack('<' + 'h' * (len(expected) // 2), expected)
    error = [a - b for a, b in zip(x, y)]
    signal = sum(a * a for a in y)
    noise = sum(e * e for e in error)
    return {'samples': len(x), 'different_samples': sum(e != 0 for e in error),
            'max_absolute_error': max(map(abs, error), default=0),
            'rmse': math.sqrt(noise / max(1, len(x))),
            'snr_db': None if noise == 0 else 10 * math.log10(max(1, signal) / noise)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc', default='clang')
    parser.add_argument('--avr-gcc', default='avr-gcc')
    parser.add_argument('--node', default='node')
    parser.add_argument('--frames', type=int, help='AVR smoke limit per stream; cannot be recorded as complete')
    parser.add_argument('--record', action='store_true')
    parser.add_argument('--trace', action='store_true', help='Diagnostic float stage capture, excluded from retained production report')
    parser.add_argument('--host-only', action='store_true')
    args = parser.parse_args()
    if args.record and (args.host_only or args.frames or args.trace):
        parser.error('--record requires the complete AVR streams')
    BUILD.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((front.VENDOR / 'UPSTREAM.json').read_text())
    for item in manifest['files']:
        if front.digest(front.VENDOR / item['path']) != item['sha256']:
            raise RuntimeError('Modified vendor source: ' + item['path'])
    selected = reference_sources(args.cc)
    common = [args.cc, '-O2', '-fno-strict-aliasing', '-ffp-contract=off', '-D_CRT_SECURE_NO_WARNINGS',
              '-I' + str(VENDOR), '-I' + str(ROOT / 'include'), '-I' + str(BUILD / 'include')]
    trace_flags = ['-DCODEC2_DECODER_TRACE'] if args.trace else []
    link = [] if os.name == 'nt' else ['-lm']
    exe = '.exe' if os.name == 'nt' else ''
    oracle = BUILD / ('upstream' + exe)
    kiss = [VENDOR / 'kiss_fft.c', VENDOR / 'kiss_fftr.c']
    front.run([*common, '-DCODEC2_MODE_EN_DEFAULT=0', '-DCODEC2_MODE_3200_EN=1', *selected,
               VENDOR / 'pack.c', VENDOR / 'codec2_fft.c', VENDOR / 'lsp.c', VENDOR / 'postfilter.c',
               *kiss, ROOT / 'tests/upstream_decode.c', '-o', oracle, *link])
    decoder = BUILD / ('decode' + exe)
    front.run([*common, *trace_flags, ROOT / 'src/decoder_float.c', ROOT / 'src/parameters.c', VENDOR / 'lsp.c',
               *kiss, ROOT / 'tests/decode.c', '-o', decoder, *link])
    api = BUILD / ('api' + exe)
    front.run([*common, ROOT / 'src/decoder_float.c', ROOT / 'src/parameters.c', VENDOR / 'lsp.c',
               *kiss, ROOT / 'tests/decoder_api.c', '-o', api, *link])
    baseline = ROOT / 'AVR/Codec2_Tiny13_Quality_R2'
    api_result = front.run([api, baseline / 'tests/speech.c2zx', baseline / 'tests/codec2_3200_8byte_frames.bin'],
                           capture_output=True, text=True)
    print(api_result.stdout.strip(), flush=True)
    results = []
    inputs = [('speech.c2zx', baseline / 'tests/speech.c2zx'),
              ('codec2_3200_8byte_frames.bin', baseline / 'tests/codec2_3200_8byte_frames.bin')]
    stress = front.BUILD / 'frames.bin'
    assert stress.stat().st_size == 11333 * 8, 'Run verify_frontend.py to prepare the deterministic stress corpus'
    inputs.append(('all-11333', stress))
    for name, path in inputs:
        reference = BUILD / (name + '.upstream.pcm')
        output = BUILD / (name + '.pcm')
        front.run([oracle, path, reference])
        front.run([decoder, path, output, *([BUILD / (name + '.native-trace.bin')] if args.trace else [])])
        result = {'name': name, 'frames': path.stat().st_size // 8, 'packet_sha256': front.digest(path),
                  'oracle_sha256': front.digest(reference), 'output_sha256': front.digest(output),
                  **metrics(output.read_bytes(), reference.read_bytes())}
        print(json.dumps(result), flush=True)
        results.append(result)
        assert output.read_bytes() == reference.read_bytes(), 'Native full decoder must match original upstream PCM'
    report = {'upstream_commit': manifest['commit'], 'streams': results, 'api': api_result.stdout.strip(),
              'host_compiler': front.run([args.cc, '--version'], capture_output=True, text=True).stdout.splitlines()[0],
              'generated_reference_hashes': {p.name: front.digest(p) for p in selected}}
    if not args.host_only:
        target = BUILD / 'atmega1284p'
        target.mkdir(exist_ok=True)
        prefix = args.avr_gcc[:-3] if args.avr_gcc.endswith('gcc') else args.avr_gcc.replace('gcc.exe', '')
        memory = device_memory(args.avr_gcc, 'atmega1284p')
        front.run([args.avr_gcc, '-mmcu=atmega1284p', '-Os', '-std=c99', '-fstack-usage', '-fno-strict-aliasing', *trace_flags,
                   '-ffunction-sections', '-fdata-sections', '-I' + str(ROOT / 'include'), '-I' + str(VENDOR),
                   ROOT / 'src/decoder_float.c', ROOT / 'src/parameters.c', VENDOR / 'lsp.c', *kiss,
                   ROOT / 'tests/avr_decoder.c', '-Wl,--gc-sections,-Map=' + str(target / 'decoder.map'),
                   '-Wl,--defsym=__DATA_REGION_ORIGIN__=' + str(0x800000 + memory['RAMSTART']),
                   '-Wl,--defsym=__DATA_REGION_LENGTH__=' + str(memory['RAMEND'] - memory['RAMSTART'] + 1),
                   '-Wl,--defsym=__TEXT_REGION_LENGTH__=' + str(memory['FLASHEND'] + 1),
                   '-o', target / 'decoder.elf', '-lm'], cwd=target)
        front.run([prefix + 'objcopy', '-O', 'binary', target / 'decoder.elf', target / 'decoder.bin'])
        with (target / 'symbols.txt').open('wb') as output:
            front.run([prefix + 'nm', '-n', target / 'decoder.elf'], stdout=output)
        report['avr_build'] = {'mcu': 'atmega1284p', 'binary_sha256': front.digest(target / 'decoder.bin'),
            'compiler': front.run([args.avr_gcc, '--version'], capture_output=True, text=True).stdout.splitlines()[0],
            'manufacturer_header_memory': memory,
            'size': front.run([prefix + 'size', '-A', target / 'decoder.elf'], capture_output=True, text=True).stdout}
    front.dump(BUILD / 'host-verification.json', report)
    if not args.host_only:
        front.run([args.node, ROOT / 'tests/verify_decoder_avr.mjs', *(['--frames', str(args.frames)] if args.frames else [])])
        report['avr_execution'] = json.loads((BUILD / 'avr-execution.json').read_text())
    report['verified_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    report['sources'] = {name: front.digest(ROOT / name) for name in ('include/codec2_decoder.h', 'include/codec2_3200.h',
        'src/decoder_float.c', 'src/parameters.c', 'tests/decode.c', 'tests/upstream_decode.c',
        'tests/decoder_api.c', 'tests/avr_decoder.c', 'tests/verify_decoder_avr.mjs', 'tools/verify_decoder.py',
        'tools/audit_decoder_memory.py',
        'vendor/codec2-1.2.0/UPSTREAM.json')}
    report['scope'] = 'Complete mode-3200 waveform algorithm, default upstream postfilters. No hardware playback, active-IRQ admission or Tiny13 fit is established.'
    front.dump(BUILD / 'verification.json', report)
    if args.record:
        front.dump(ROOT / 'reports/full-decoder.json', report)


if __name__ == '__main__':
    main()

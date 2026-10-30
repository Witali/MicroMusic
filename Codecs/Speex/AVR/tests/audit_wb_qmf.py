#!/usr/bin/env python3
"""Check source-bound exact QMF corpus/IRQ evidence; optionally rebuild images."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def digest(path, text=False):
    data = path.read_bytes()
    return hashlib.sha256(data.replace(b'\r\n', b'\n') if text else data).hexdigest()


def read(name):
    return json.loads((ROOT/'reports'/name).read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--avr-gcc', help='Also rebuild five final images; no C simulations')
    parser.add_argument('--corpus-root', type=Path, help='Codec root containing the original build corpora')
    args = parser.parse_args()
    admission = read('wb-qmf-admission.json')
    for name, sha in admission['sourceSha256'].items():
        assert digest(ROOT/name, True) == sha, name
    for name, sha in admission['binaryFixtureSha256'].items():
        assert digest(ROOT/name) == sha, name
    for name, sha in admission['reportSha256'].items():
        assert digest(ROOT/'reports'/name, True) == sha, name
    previous = read('group4-admission.json')
    for name, sha in admission['unchangedCAndHeaderSha256'].items():
        assert digest(ROOT/name, True) == sha == previous['sourceSha256'][name], name
    for mode, width in [('98', 25), ('128', 32)]:
        before, after = [read(f'wb-qmf-{step}-{mode}.json') for step in ['before', 'after']]
        old = next(r for r in previous['decoderImages']
                   if r['mode'] == 'wb'+mode and r['backend'] == 'asm')
        assert before['binarySha256'] == old['sha256']
        assert before['frames'] == after['frames'] == 10563
        assert before['flashBytes']-after['flashBytes'] == 64
        assert abs(before['meanCycles']-after['meanCycles']-2560) < 1e-9
        for key in ['staticSramBytes', 'peakStack', 'freeSram']:
            assert before[key] == after[key]
        assert len(before['streams']) == len(after['streams']) == 17
        for a, b in zip(before['streams'], after['streams']):
            assert a['name'] == b['name'] and a['frames'] == b['frames']
            assert b['pcmExact'] and b['reset']
            for key in ['minCycles', 'maxCycles', 'meanCycles']:
                assert a[key]-b[key] == 2560
        profiles = [read(f'wb-qmf-profile-{step}-{mode}.json') for step in ['before', 'after']]
        mappings = [{r['name']: r['cycles'] for r in p['functions']} for p in profiles]
        for p, result in zip(profiles, [before, after]):
            assert p['binarySha256'] == result['binarySha256']
            assert sum(r['cycles'] for r in p['functions']) == p['totalCycles']
            assert p['totalCycles']/p['frames'] == result['meanCycles']
        assert mappings[0].keys() == mappings[1].keys()
        for name, cycles in mappings[0].items():
            assert cycles-mappings[1][name] == (2560*10563 if name == 'speex_wb_qmf40_avr' else 0), name
        stream = read(f'wb-qmf-stream-{mode}.json')
        assert stream['packetBytes'] == width and stream['frames'] == 10563
        assert stream['includesInterrupts'] and stream['extraCpuCyclesPerFrame'] == 25600
        assert stream['underruns'] == 0 and not stream['physicalBoardTested']
        expected = {Path(r['stream']).name: r for r in admission['corpora']['wb'+mode]}
        assert len(stream['streams']) == len(expected) == 17
        for row in stream['streams']:
            binding = expected.pop(row['stream'])
            assert row['frames'] == row['measuredLoads'] == binding['frames']
            assert row['inputSha256'] == binding['inputSha256']
            assert row['pcmSha256'] == binding['pcmSha256']
            assert row['s16AndPwmExact'] and row['fullHistoryWithoutChunkReset'] and row['underruns'] == 0
            assert row['timerIntervalMinCycles'] >= 990 and row['timerIntervalMaxCycles'] <= 1010
            if args.corpus_root:
                for key, sha in [('stream', 'inputSha256'), ('oracle', 'pcmSha256')]:
                    assert digest(args.corpus_root/binding[key]) == binding[sha], binding[key]
    units = [read('wb-qmf-unit-'+step+'.json') for step in ['before', 'after']]
    for unit in units:
        assert unit['asmOnly'] and unit['qmfOnly'] and unit['fullInputs']
        row, = unit['streams']
        assert row['blocks'] == row['calleeSavedAndR1Returns'] == 2244
        assert row['pcmExact'] and row['mirroredHistoryExact'] and row['guards'] and row['aliasQmf']
    for key in ['minCycles', 'maxCycles']:
        assert units[0]['streams'][0][key]-units[1]['streams'][0][key] == 640
    flash = read('wb-qmf-flash.json')
    assert flash['frames'] == 256 and len(flash['streams']) == 2
    assert flash['includesInterrupts'] and flash['extraCpuCyclesPerFrame'] == 25600 and flash['underruns'] == 0
    for row, binding in zip(flash['streams'], admission['flashSlices']):
        assert row['passed'] and row['input']['frames'] == binding['frames'] == 128
        if args.corpus_root:
            raw = (args.corpus_root/binding['stream']).read_bytes()[:128*row['input']['packetBytes']]
            assert hashlib.sha256(raw).hexdigest() == row['input']['sha256']
    if args.avr_gcc:
        sys.path.insert(0, str(ROOT/'tools'))
        import build_wb
        out = ROOT/'build/wb-qmf-audit'
        for mode, width in [('98', 25), ('128', 32)]:
            image = build_wb.avr(args.avr_gcc, 'asm', packet_bytes=width, destination=out/mode)
            assert digest(image/'wb.bin') == read(f'wb-qmf-after-{mode}.json')['binarySha256']
            image = out/('stream-'+mode)
            subprocess.run([sys.executable, ROOT/'tools/build_wb_stream_test.py', '--avr-gcc', args.avr_gcc,
                            '--packet-bytes', str(width), '--out', image], check=True)
            assert digest(image/'wb.bin') == read(f'wb-qmf-stream-{mode}.json')['binarySha256']
        image = build_wb.avr(args.avr_gcc, 'asm', kernels=True, destination=out/'kernels')
        assert digest(image/'wb.bin') == units[1]['binarySha256']
    print('PASS: QMF sources, unchanged C fallback, exact corpus/cycle/ABI and active-IRQ admission'
          + ('; five final images rebuilt identically' if args.avr_gcc else ''))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Validate source-bound low-rate exact PCM, public API and active-IRQ evidence."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def read(name):
    return json.loads((ROOT/'reports'/name).read_text())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--corpus', type=Path, help='Optionally check retained low-corpus input/oracle files')
    args = p.parse_args()
    admission = read('low-final-admission.json')
    for name, expected in admission['sourceSha256'].items():
        assert digest(ROOT/name) == expected, name
    for name, expected in admission['reportSha256'].items():
        assert digest(ROOT/'reports'/name) == expected, name
    corpus = read('low-final-corpus.json')['streams']
    assert len(corpus) == 108
    widths = {'nb215': 6, 'nb395': 10, 'nb595': 15, 'wb395': 10, 'wb575': 15, 'wb775': 20}
    total = 0
    for label, width in widths.items():
        raw = read('low-final-'+label+'.json')
        assert raw['backend'] == 'asm' and not raw['includesInterrupts']
        assert raw['frames'] == 10627 and len(raw['streams']) == 18
        assert raw['maxCycles'] < 320000 and raw['flashBytes'] < 32768
        bindings = {r['stream']: r for r in corpus if r['profile'] == label}
        assert sum(r['frames'] for r in bindings.values()) == 10627
        for row in raw['streams']:
            name = row.get('name', row.get('stream'))
            binding = bindings[name]
            assert row['frames'] == binding['frames']
            assert row.get('reset', row.get('resetVerified'))
            if label.startswith('wb'):
                assert row['pcmExact']
            if args.corpus:
                for sub, key, filename in [('streams', 'inputSha256', name), ('oracle', 'pcmSha256', name.replace('.spxraw', '.pcm'))]:
                    actual = hashlib.sha256((args.corpus/label/sub/filename).read_bytes()).hexdigest()
                    assert actual == binding[key], (label, filename)
        total += raw['frames']
        if label.startswith('nb'):
            continue
        for suffix, load in [('irq', 0), ('load3', 9600)]:
            irq = read('low-final-'+label+'-'+suffix+'.json')
            assert irq['includesInterrupts'] and not irq['physicalBoardTested']
            assert irq['packetBytes'] == width and irq['extraCpuCyclesPerFrame'] == load
            assert irq['frames'] == 10627 and irq['underruns'] == 0 and len(irq['streams']) == 18
            for row in irq['streams']:
                binding = bindings[row['stream']]
                assert row['frames'] == binding['frames']
                for key in ['inputSha256', 'pcmSha256']:
                    assert row[key] == binding[key]
                assert row['s16AndPwmExact'] and row['fullHistoryWithoutChunkReset']
                assert row['underruns'] == 0 and row['freeSramAtPeak'] > 0
                assert row['timerIntervalMinCycles'] >= 990 and row['timerIntervalMaxCycles'] <= 1010
                assert row['measuredLoads'] == (row['frames'] if load else 0)
    for mode, count in [('nb8', 9100), ('nb11', 11587), ('wb98', 10563), ('wb128', 10563)]:
        raw = read('low-final-'+mode+'.json')
        assert raw['frames'] == count and raw['backend'] == 'asm'
        assert all(r.get('reset', r.get('resetVerified')) for r in raw['streams'])
        total += count
    for mode, rejects in [('nb', 6144), ('wb', 7168)]:
        api = read('low-final-api-'+mode+'.json')
        assert api['frames'] == 1024 and api['rejectedCalls'] == rejects
        assert api['pcmExact'] and api['resetExact'] and api['paddingIgnored']
        assert api['mixedEnabledModes'] == [1, 2, 8, 3, 4]
    disabled = read('low-final-disabled.json')['images']
    assert len(disabled) == 4 and all(r['byteIdentical'] for r in disabled)
    export = read('low-final-export.json')
    assert not export['handwrittenAssembly'] and not export['duplicateSources']
    assert export['widebandBitrates'] == [3950, 5750, 7750, 9800, 12800]
    features = read('low-final-features.json')['images']
    assert [r['lowerFeatureMask'] for r in features] == [1, 2, 4]
    assert all(r['frames'] == 128 and not r['nb4Enabled'] for r in features)
    flash = read('low-final-flash.json')
    assert flash['frames'] == 1024 and len(flash['streams']) == 8
    for row in flash['streams']:
        assert row['passed'] and row['includesInterrupts'] and not row['physicalBoardTested']
        assert row['frames'] == 128 and row['underruns'] == 0
        assert row['extraCpuCyclesPerFrame'] == 9600 and row['flashBytes'] <= 32768
    print('PASS:', total, 'exact ASM decoder frames; 63762 continuous IRQ frames; API, Flash and optional-feature admission')


if __name__ == '__main__':
    main()

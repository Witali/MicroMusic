#!/usr/bin/env python3
"""Exercise cached HB LPC with all codebook pairs and changing NB/gains.

The independent decoder retains Xiph interpolation and LPC recalculation.
Emit an additional small corpus for AVR machine-code verification.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EXE = 'decode.exe' if sys.platform == 'win32' else 'decode'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'build/wb-speed-repeats')
    parser.add_argument('--native', type=Path, default=ROOT / 'build/wb-native' / EXE)
    parser.add_argument('--reference', type=Path, default=ROOT / 'build/wb-reference' / EXE)
    args = parser.parse_args()
    data = (ROOT / 'build/wb-corpus/streams/coverage_lsp4096.spxraw').read_bytes()
    assert len(data) == 4096 * 25
    packets = [data[i:i + 25] for i in range(0, len(data), 25)]
    triplets = []
    for i, packet in enumerate(packets):
        assert ((packet[20] & 15) << 8 | packet[21]) == i
        # A, A, A, B, B, B ... : reuse the HB LSP while both the NB packet
        # (including its own LPC/excitation) and all four HB gains change.
        triplets.append(b''.join(packets[(i + n) % 4096][:20] + packet[20:22] +
                                 packets[(i + n) % 4096][22:] for n in range(3)))
    selected = sorted(set(range(0, 4096, 17)) | {1, 63, 64, 127, 2047, 2048, 4095})
    streams = args.out / 'streams'
    oracle = args.out / 'oracle'
    streams.mkdir(parents=True, exist_ok=True)
    oracle.mkdir(exist_ok=True)
    cases = [('all_lsp4096', b''.join(triplets), args.out),
             ('repeat_lsp_avr', b''.join(triplets[i] for i in selected), streams)]
    rows = []
    for name, raw, directory in cases:
        source = directory / (name + '.spxraw')
        expected = oracle / (name + '.pcm')
        actual = args.out / (name + '-native.pcm')
        source.write_bytes(raw)
        subprocess.run([str(args.reference), '1', '25', str(source), str(expected)], check=True)
        subprocess.run([str(args.native), str(source), str(actual)], check=True)
        pcm = expected.read_bytes()
        assert len(pcm) == len(raw) // 25 * 640
        assert actual.read_bytes() == pcm, name
        rows.append(dict(name=name, frames=len(raw) // 25, inputSha256=digest(raw),
                         pcmSha256=digest(pcm), pcmExact=True))
    report = dict(scope='HB LPC cache: every codebook pair repeated three times with changing NB/gains',
                  reference='Independent Xiph NB/HB + separate compact QMF equation',
                  codebookPairs=4096, selectedAvrCodebookPairs=len(selected),
                  nativeBinarySha256=digest(args.native.read_bytes()),
                  referenceBinarySha256=digest(args.reference.read_bytes()), streams=rows)
    (args.out / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()

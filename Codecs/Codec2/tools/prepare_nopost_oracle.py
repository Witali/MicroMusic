#!/usr/bin/env python3
"""Bootstrap same-option upstream PCM for the postfilter-off precision study."""
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_frontend as front
import verify_decoder as original
from generate_nopost import generate_oracle

ROOT = front.ROOT
BUILD = ROOT.parents[1] / 'build/codec2/nopost'


def main():
    assert generate_oracle() == (ROOT / 'tests/upstream_nopost.c').read_bytes()
    baseline = json.loads((ROOT / 'reports/matrix-decoder.json').read_text())
    for name, wanted in baseline['sources'].items():
        assert front.digest(ROOT / name) == wanted, name
    manifest = json.loads((front.VENDOR / 'UPSTREAM.json').read_text())
    for item in manifest['files']:
        assert front.digest(front.VENDOR / item['path']) == item['sha256']
    BUILD.mkdir(parents=True, exist_ok=True)
    original.BUILD = BUILD / 'oracle'
    sources = original.reference_sources('clang')
    vendor = front.VENDOR / 'src'
    program = BUILD / ('upstream' + ('.exe' if os.name == 'nt' else ''))
    front.run(['clang', '-O2', '-fno-strict-aliasing', '-ffp-contract=off',
        '-D_CRT_SECURE_NO_WARNINGS', '-DCODEC2_MODE_EN_DEFAULT=0', '-DCODEC2_MODE_3200_EN=1',
        '-I' + str(ROOT / 'include'), '-I' + str(vendor), '-I' + str(original.BUILD / 'include'),
        *sources, *[vendor / n for n in ('pack.c', 'codec2_fft.c', 'lsp.c', 'postfilter.c', 'kiss_fft.c', 'kiss_fftr.c')],
        ROOT / 'tests/upstream_nopost.c', '-o', program, *([] if os.name == 'nt' else ['-lm'])])
    legacy = ROOT / 'AVR/Codec2_Tiny13_Quality_R2/tests'
    for previous in baseline['streams']:
        name = previous['name']
        if name == 'conditioning-stress':
            continue
        packet = front.BUILD / 'frames.bin' if name == 'all-11333' else legacy / name
        assert front.digest(packet) == previous['packet_sha256']
        (BUILD / (name + '.packets')).write_bytes(packet.read_bytes())
        output = BUILD / (name + '.upstream.pcm')
        front.run([program, packet, output])
        print(name + ': prepared original upstream pf=0 PCM')


if __name__ == '__main__':
    main()

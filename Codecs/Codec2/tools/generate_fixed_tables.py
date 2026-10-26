#!/usr/bin/env python3
"""Quantize the pinned KISS twiddle angles into a quarter-wave integer table."""
import argparse
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / 'src/fixed_inverse_tables.inc'


def generate():
    original = (ROOT / 'src/compact_tables.inc').read_text()
    floats = [float.fromhex(x[:-1]) for x in re.findall(r'-?0x[0-9a-f.]+p[+-]\d+f', original)]
    assert len(floats) == 928
    super_twiddles = floats[512:768]
    notice = original.split('*/', 1)[0] + '*/\n'
    text = notice + ('/* Generated from the pinned original KISS binary32 angles.\n'
                     ' * Quarter sine for a 512-point real FFT; nearest integer.\n */\n')
    for q in range(6, 15):
        values = [0] + [round(-super_twiddles[2 * (i - 1)] * (1 << q)) for i in range(1, 129)]
        def sine(k):
            k %= 512
            return values[k] if k <= 128 else values[256-k] if k <= 256 else -sine(k-256)
        for k in range(256):
            assert round(floats[2*k] * (1 << q)) == sine(2*k+128)
            assert round(-floats[2*k+1] * (1 << q)) == sine(2*k)
        deviations = []
        for k in range(128):
            assert round(super_twiddles[2*k] * (1 << q)) == sine(257+k)
            deviations.append(abs(round(-super_twiddles[2*k+1] * (1 << q)) - sine(129+k)))
        # Original cosf/sinf phase rounding crosses one Q14 half-step. A shared
        # quarter wave is allowed one quantization unit; full PCM gates remain.
        assert max(deviations) <= 1
        text += f'/* Q{q}: shared quarter wave differs from original super twiddles by at most {max(deviations)} unit. */\n'
        text += f'#if CODEC2_FIXED_TWIDDLE_Q == {q}\n'
        text += f'static const uint{8 if q == 6 else 16}_t fixed_sine[129] CODEC2_TABLE_STORAGE = {{\n'
        for at in range(0, 129, 12):
            text += '    ' + ', '.join(str(v) for v in values[at:at+12]) + ',\n'
        text += '};\n#endif\n'
    return text.encode('utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    data = generate()
    if args.check:
        assert DESTINATION.read_bytes() == data
    else:
        DESTINATION.write_bytes(data)

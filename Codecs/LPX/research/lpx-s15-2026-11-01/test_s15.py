"""Finite format/native/model contracts; synthetic input only."""
import argparse
from pathlib import Path
import json
import numpy as np
from s15_format import pack, unpack, expand, decode_model, POSITIONS
from s15_native import build, Native
from standard_metrics import pwm_duties


def fixture(n):
    frames = (n+319)//320
    spectra = [[3+i*5+(fi%2) for i in range(10)] for fi in range(frames)]
    params = [(10+fi%3, 18+fi%128, (fi%8)*2) for fi in range(frames)]
    pulses = [(POSITIONS[(i*13)%64], -8 if i%2 else 7) for i in range(frames*4)]
    return pack(n, spectra, params, pulses, 8192, 11469)[0]


def contracts(common, only):
    valid = 0
    invalid = 0
    for n in (1, 19, 20, 79, 80, 81, 159, 160, 319, 320, 321, 641):
        blob = fixture(n)
        args = unpack(blob)
        assert pack(*args)[0] == blob
        expanded = expand(blob)
        expected = decode_model(blob)
        for native in (common, only):
            assert native.expand(blob) == expanded
            assert np.array_equal(native.decode(blob, n), expected)
            assert np.array_equal(native.decode(blob, n, True), pwm_duties(expected))
            # Version8 can only enter through the explicit experimental path.
            assert native.decoder.decode_one_s16(blob, n) is None
        valid += 1
    blob = fixture(320)
    bad = [blob[:i] for i in range(len(blob))] + [blob+b'\0']
    for offset in (4, 5, 6, 16, 18):
        item = bytearray(blob)
        item[offset] ^= 1
        bad.append(bytes(item))
    item = bytearray(blob)
    item[20:22] = (len(blob)-21).to_bytes(2, 'little')
    item.append(0)
    bad.append(bytes(item))
    # Initial repeat has no previous spectrum.
    item = bytearray(blob)
    item[22] &= 254
    bad.append(bytes(item))
    for candidate in bad:
        try:
            unpack(candidate)
        except ValueError:
            pass
        else:
            raise AssertionError('Malformed synthetic S15 accepted by Python')
        assert common.expand(candidate) is None and only.expand(candidate) is None
        invalid += 1
    # Legal v5/P4 lower bound, including the minimum initial spectrum and padding.
    import speech_compact as v5
    minimum, meta = v5.pack(19200, 4, [list(range(10))]*60,
                           [(0, 18, 0)]*120, [(0, 8)]*960, 0, 0)
    assert len(minimum) == 858 and meta['payload_bits'] == 6681
    assert len(POSITIONS) == len(set(POSITIONS)) == 64 and POSITIONS[-1] == 79
    return dict(status='PASS', synthetic_valid_streams=valid, invalid_streams=invalid,
                native_paths=2, v5_rejects_version8=True, v5_p4_minimum_bytes_19200=858)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--compiler', required=True)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    libraries = [a.output / name for name in ('common.so', 'v5-only.so')]
    for library, compact in zip(libraries, (False, True)):
        build(library, a.compiler, compact)
    report = contracts(*[Native(p) for p in libraries])
    (a.output / 'contracts-private.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))

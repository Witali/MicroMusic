#!/usr/bin/env python3
"""Offline QMF response/resource screening; no decoder or timing admission."""
import argparse
import cmath
import hashlib
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    vendor = ROOT / 'vendor/speex-1.2.1/libspeex/sb_celp.c'
    match = re.search(r'h0\[64\] = \{([^}]+)', vendor.read_text())
    upstream = [int(v) for v in match[1].split(',')]
    assert len(upstream) == 64 and upstream == upstream[::-1]
    production = ROOT / 'src/wb_qmf.c'
    match = re.search(r'h\[16\] AVR_TABLE=\{([^}]+)', production.read_text())
    current = [int(v) for v in match[1].split(',')]
    rows = []
    for taps in [16, 20, 24, 32, 64]:
        center = upstream[32-taps//2:32+taps//2]
        coefficients = upstream if taps == 64 else [
            math.floor(256*v/sum(center)+0.5) for v in center]
        if taps == 16:
            assert coefficients == current, 'Reproduce actual production taps'
        divisor = 65536 if taps == 64 else 256

        def db(frequency):
            value = sum(v*cmath.exp(-2j*math.pi*frequency*i/16000)
                        for i, v in enumerate(coefficients))/divisor
            return 20*math.log10(max(1e-12, abs(value)))

        # Uniform 2-Hz grid, normalized to ideal DC, not each filter's DC.
        passband = [db(f) for f in range(0, 3001, 2)]
        stopband = [db(f) for f in range(5000, 8001, 2)]
        absolute = [sum(abs(v) for v in coefficients[p::2]) for p in [0, 1]]
        bound = max(absolute)*32768+32
        rows.append(dict(
            name='full-Xiph-Q15' if taps == 64 else f'center-{taps}-Q7',
            production=taps == 16, taps=taps, coefficients=coefficients,
            dcGain=sum(coefficients)/divisor,
            passband0to3kMinDb=min(passband), passband0to3kMaxDb=max(passband),
            stopband5to8kMaxDb=max(stopband),
            responseDb={str(f): db(f) for f in [3000, 3500, 4000, 4500, 5000, 7000]},
            mirroredHalfHistoryBytes=4*taps,
            fortyPairsRestoreCursorToZero=40 % (taps//2) == 0,
            nonzeroCoefficientProductsPerFrame=160*sum(v != 0 for v in coefficients),
            signed8Coefficients=all(-128 <= v <= 127 for v in coefficients),
            phaseAbsoluteCoefficientSums=absolute,
            signed24Q7Bound=bound if taps != 64 else None,
            fitsCurrentSigned24Q7Accumulator=taps != 64 and bound < 2**23,
            currentMirrorStoreDisplacementsFitLdd=2*taps+3 <= 63))
    result = dict(
        scope='Offline linear filter response only; no speech quality, assembly speed or playback admission.',
        source='Vendored unmodified Xiph Speex 1.2.1 h0; COPYING retains BSD provenance.',
        sourceSha256={str(p.relative_to(ROOT)).replace('\\', '/'): digest(p)
                      for p in [vendor, production, Path(__file__)]},
        frequencyGridHz=2, sampleRateHz=16000,
        rounding='Q7 center taps scaled to sum 256 before nearest rounding; ties toward positive infinity.',
        candidates=rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes((json.dumps(result, indent=2)+'\n').encode())
    for row in rows:
        print(row['name'], 'passband dB', round(row['passband0to3kMinDb'], 3),
              round(row['passband0to3kMaxDb'], 3), 'stopband dB',
              round(row['stopband5to8kMaxDb'], 3), 'history', row['mirroredHalfHistoryBytes'])


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Characterize exact HB1 interpolation candidates; do not run a decoder.

The default check needs only Python's standard library. It exhausts the
finite old/new endpoint values independently for every component and checks
selected complete vectors through the sequential margin repair. The optional
NumPy mode checks all 4096**2 endpoint vector pairs at all four quarters.
This characterizes an optimization opportunity, not target timing admission.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / 'vendor/speex-1.2.1/libspeex/high_lsp_tables.c'
EXPECTED_BOUNDS = [(2704, 9024), (4800, 11168), (6880, 15088),
                   (8880, 17936), (12272, 20560), (13856, 22784),
                   (17328, 24256), (19760, 25600)]


def endpoints():
    text = TABLE.read_text(encoding='utf-8')
    tables = []
    for name in ['high_lsp_cdbk', 'high_lsp_cdbk2']:
        match = re.search(r'\b' + name + r'\[512\]\s*=\s*\{(.*?)\}', text, re.S)
        assert match, name
        words = list(map(int, re.findall(r'-?\d+', match.group(1))))
        assert len(words) == 512 and all(-128 <= n <= 127 for n in words)
        tables.append([words[i:i + 8] for i in range(0, 512, 8)])
    return [tuple(6144 + 2560*i + 32*a[i] + 16*b[i] for i in range(8))
            for a in tables[0] for b in tables[1]]


def reference_word(old, new, quarter):
    # Xiph's two separately rounded MULT16_16_P14 products, not a combined
    # weighted average. Integral codebook terms make their rounding exact.
    fraction = 4096 * quarter
    return ((old*(16384-fraction) + 8192) >> 14) + ((new*fraction + 8192) >> 14)


def difference_word(old, new, quarter):
    delta = new - old
    if quarter == 1:
        return old + (delta >> 2)
    if quarter == 2:
        return old + (delta >> 1)
    if quarter == 3:
        return new - (delta >> 2)
    return new


def margin(raw, candidate=False):
    out = list(raw)
    if not candidate and out[0] < 410:
        out[0] = 410
    if out[7] > 25736-410:
        out[7] = 25736-410
    for i in range(1, 7):
        if (not candidate or i != 4) and out[i] < out[i-1]+410:
            out[i] = out[i-1]+410
        if (not candidate or i != 3) and out[i] > out[i+1]-410:
            out[i] = (out[i] >> 1) + ((out[i+1]-410) >> 1)
    return out


def fast_check(values):
    bounds = [(min(x[i] for x in values), max(x[i] for x in values)) for i in range(8)]
    assert bounds == EXPECTED_BOUNDS
    assert len(values) == 4096
    assert all(0 <= n <= 32767 and n % 16 == 0 for x in values for n in x)
    assert max(high-low for low, high in bounds) == 9056 < 32768
    assert bounds[0][0] >= 410
    assert bounds[7][1] > 25736-410, 'The last endpoint clamp is still required'
    pairs = checks = 0
    counts = []
    for i in range(8):
        domain = sorted({x[i] for x in values})
        counts.append(len(domain))
        for old in domain:
            for new in domain:
                pairs += 1
                assert -32768 <= new-old <= 32767
                for q in (1, 2, 3, 4):
                    actual = difference_word(old, new, q)
                    assert actual == reference_word(old, new, q), (i, old, new, q)
                    assert bounds[i][0] <= actual <= bounds[i][1]
                    checks += 1
    vectors = 0
    for at, new in enumerate(values):
        # Equal, reversed and cyclic endpoints exercise both motion directions
        # and retain valid correlated codebook components in every vector.
        for old in [new, values[-at-1], values[(at+117) % len(values)]]:
            for q in (1, 2, 3, 4):
                raw = [reference_word(a, b, q) for a, b in zip(old, new)]
                other = [difference_word(a, b, q) for a, b in zip(old, new)]
                assert raw == other
                assert margin(raw) == margin(other, candidate=True)
                vectors += 1
    return dict(componentBounds=bounds, distinctComponentValues=counts,
                componentEndpointPairs=pairs, quarterComponentChecks=checks,
                selectedCompleteMarginVectors=vectors)


def exhaustive_margin(values, numpy_path):
    if numpy_path:
        sys.path.insert(0, str(numpy_path))
    import numpy as np
    ep = np.array(values, dtype=np.int32)
    mins = np.full((6, 2), 2**30, dtype=np.int32)
    repairs = np.zeros((6, 2), dtype=np.int64)
    cases = 0
    for at in range(0, len(ep), 32):
        old, new = ep[at:at+32, None, :], ep[None, :, :]
        for q in (1, 2, 3, 4):
            f = 4096*q
            x = ((old*(16384-f)+8192) >> 14) + ((new*f+8192) >> 14)
            if q == 1:
                y = old + ((new-old) >> 2)
            elif q == 2:
                y = old + ((new-old) >> 1)
            elif q == 3:
                y = new - ((new-old) >> 2)
            else:
                y = np.broadcast_to(new, x.shape).copy()
            assert np.array_equal(x, y), (at, q, 'raw interpolation')
            assert (x[:, :, 0] >= 410).all()
            x[:, :, 0] = np.maximum(x[:, :, 0], 410)
            x[:, :, 7] = np.minimum(x[:, :, 7], 25326)
            y[:, :, 7] = np.minimum(y[:, :, 7], 25326)
            for i in range(1, 7):
                lower = x[:, :, i]-x[:, :, i-1]-410
                mins[i-1, 0] = min(int(mins[i-1, 0]), int(lower.min()))
                repairs[i-1, 0] += int((lower < 0).sum())
                x[:, :, i] = np.maximum(x[:, :, i], x[:, :, i-1]+410)
                upper = x[:, :, i+1]-410-x[:, :, i]
                mins[i-1, 1] = min(int(mins[i-1, 1]), int(upper.min()))
                repairs[i-1, 1] += int((upper < 0).sum())
                x[:, :, i] = np.where(upper < 0, (x[:, :, i] >> 1) +
                                      ((x[:, :, i+1]-410) >> 1), x[:, :, i])
                if i != 4:
                    y[:, :, i] = np.maximum(y[:, :, i], y[:, :, i-1]+410)
                if i != 3:
                    y[:, :, i] = np.where(y[:, :, i] > y[:, :, i+1]-410,
                                          (y[:, :, i] >> 1) +
                                          ((y[:, :, i+1]-410) >> 1), y[:, :, i])
            assert np.array_equal(x, y), (at, q, 'sequential margin')
            cases += x.shape[0]*x.shape[1]
    assert cases == 67108864
    assert mins.tolist() == [[-682, -42], [-21, -426], [-213, 38],
                            [38, -266], [-133, -266], [-133, -330]]
    assert repairs[2, 1] == repairs[3, 0] == 0
    return dict(completeMarginVectors=cases, quarterValues=[1, 2, 3, 4],
                minimumSequentialSlack=mins.tolist(), sequentialRepairCounts=repairs.tolist(),
                exact=True, omittedChecks=['first endpoint lower clamp',
                                          'index 3 upper repair', 'index 4 lower repair'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exhaustive-margin', action='store_true',
                        help='Require NumPy and check every complete endpoint vector pair')
    parser.add_argument('--numpy-path', type=Path, help='Optional existing local NumPy package directory')
    parser.add_argument('--output', type=Path, help='Optional JSON evidence output')
    args = parser.parse_args()
    values = endpoints()
    report = dict(scope='Finite pinned HB1 codebook arithmetic only; no decoder execution or target timing',
                  sourceSha256=hashlib.sha256(TABLE.read_bytes().replace(b'\r\n', b'\n')).hexdigest(),
                  **fast_check(values), marginFullVectorExhaustive=args.exhaustive_margin)
    if args.exhaustive_margin:
        report['exhaustiveMargin'] = exhaustive_margin(values, args.numpy_path)
    text = json.dumps(report, indent=2) + '\n'
    if args.output:
        args.output.write_text(text, encoding='utf-8')
    print(text, end='')


if __name__ == '__main__':
    main()

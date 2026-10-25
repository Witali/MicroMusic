#!/usr/bin/env python3
"""Offline, bit-exact L4HY v2 repacking; no decoder changes.

Scale aliases are solved globally. Excitation and LSF bitfields are copied,
so this pass does not silently change subframe search or decoder workload.
"""
import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from lpx4 import BitReader, BitWriter, decode, getplane, get_rice, HUFF3_DECODE
from rice_v4_reference import read_scale, write_scale
from q0_model import table
from output_paths import protect_outputs


@dataclass
class Span:
    start: int
    end: int


@dataclass
class Chunk(Span):
    mode: tuple
    payload: int
    count: int


@dataclass
class Block(Span):
    scale_start: int
    scale_end: int
    chunks: list
    frame: Span | None


def layout(blob):
    """Validated bit spans, including partial final frames/blocks/subframes."""
    frames, blocks, q = decode(blob)
    r = BitReader(blob, 20)
    here = lambda: r.o * 8 - r.n
    result = []
    previous = 0
    for index, block in enumerate(blocks):
        frame = None
        if index % 2 == 0:
            start = here()
            if r.get(1):
                if not r.get(1):
                    for _ in range(10): r.get(8); r.get(2)
                else:
                    raw = r.get(1)
                    for _ in range(10):
                        if raw: r.get(8)
                        else: getplane(r)
            frame = Span(start, here())
        start = here()
        width = r.get(3)
        scale_start = here()
        previous = read_scale(r, previous)
        scale_end = here()
        chunks = []
        for at in range(0, len(block['q']), 40):
            count = min(40, len(block['q']) - at)
            begin = here()
            typ = r.get(2)
            if typ == 0:
                k = r.get(3); mode = ('direct', k)
            else:
                lag, gain = r.get(7) + 18, r.get(5)
                k = r.get(3) if typ == 1 else r.get(4)
                mode = ('exact', lag, gain, k) if typ == 1 else ('sparse', lag, gain, k)
            payload = here()
            if typ == 2:
                for _ in range(k): r.get(6); r.get(5)
            else:
                for _ in range(count):
                    if typ == 0 and k == 0:
                        if width: r.get(width)
                    elif typ == 0 and k == 7:
                        word = ''
                        while word not in HUFF3_DECODE: word += str(r.get(1))
                    elif typ == 1 and k == 7: r.get(8)
                    else: get_rice(r, k)
            chunks.append(Chunk(begin, here(), mode, payload, count))
        result.append(Block(start, here(), scale_start, scale_end, chunks, frame))
    return frames, blocks, q, result


def copy_bits(w, blob, start, end):
    r = BitReader(blob, start // 8)
    if start % 8: r.get(start % 8)
    for at in range(start, end, 8): w.put(r.get(min(8, end - at)), min(8, end - at))


def scale_cost(previous, value):
    delta = np.asarray(value) - np.asarray(previous)
    z = np.where(delta >= 0, 2 * delta, -2 * delta - 1)
    return np.where((z >> 4) < 6, (z >> 4) + 5, 14)


def optimal_scales(blocks):
    """Minimum scale bits; secondary objective changes the fewest indices.

    All 256 indices are legal for zero q, even when source width is nonzero.
    This preserves both excitation symbols and the pitch ring at later blocks.
    """
    if not blocks: return [], 0
    steps = table('scale_table.inc')
    transition = scale_cost(np.arange(256)[:, None], np.arange(256)[None, :])
    weight = len(blocks) + 1
    unreachable = np.int64(1 << 60)
    costs = np.full(256, unreachable, np.int64); costs[0] = 0
    trace = []
    for block in blocks:
        original = block['scale']
        allowed = (steps == steps[original]) if any(block['q']) else np.ones(256, bool)
        trial = costs[:, None] + transition * weight
        parent = np.argmin(trial, axis=0)
        costs = trial[parent, np.arange(256)] + (np.arange(256) != original)
        costs[~allowed] = unreachable
        trace.append(parent.astype(np.uint8))
    current = int(np.argmin(costs)); bits = int(costs[current] // weight)
    path = []
    for parent in reversed(trace):
        path.append(current); current = int(parent[current])
    return path[::-1], bits


def optimize_scales(blob, decoder=None):
    started = time.perf_counter()
    _, blocks, q, spans = layout(blob)
    scales, after = optimal_scales(blocks)
    before = sum(b.scale_end - b.scale_start for b in spans)
    w = BitWriter(); previous = 0; cursor = 160
    for value, span in zip(scales, spans):
        copy_bits(w, blob, cursor, span.scale_start)
        write_scale(w, previous, value); previous = value
        cursor = span.scale_end
    copy_bits(w, blob, cursor, spans[-1].end)
    w.aligned(); result = blob[:20] + w.get()
    if len(result) > len(blob) or after > before: raise AssertionError('Scale DP grew the stream')
    if after == before: result = blob
    new_frames, new_blocks, new_q = decode(result)
    if new_q != q: raise AssertionError('Scale DP changed q')
    steps = table('scale_table.inc')
    for a, b in zip(blocks, new_blocks):
        if any(a['q']) and steps[a['scale']] != steps[b['scale']]:
            raise AssertionError('Scale DP changed excitation step')
    if decoder is not None:
        a = decoder.decode_one_s16(blob, len(q)); b = decoder.decode_one_s16(result, len(q))
        if a is None or b is None or not np.array_equal(a, b):
            raise AssertionError('Scale DP changed native PCM16')
    return result, {'bytes_before': len(blob), 'bytes_after': len(result),
        'scale_bits_before': before, 'scale_bits_after': after,
        'changed_indices': sum(a['scale'] != b['scale'] for a, b in zip(blocks, new_blocks)),
        'input_sha256': hashlib.sha256(blob).hexdigest(),
        'output_sha256': hashlib.sha256(result).hexdigest(),
        'native_pcm16_verified': decoder is not None, 'decoder_unchanged': True,
        'seconds': time.perf_counter() - started}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('input', type=Path); ap.add_argument('output', type=Path)
    ap.add_argument('--report', type=Path)
    args = ap.parse_args()
    protect_outputs([args.input], [args.output] + ([args.report] if args.report else []))
    from batch_decoder import BatchSession
    with BatchSession('batch') as decoder:
        result, report = optimize_scales(args.input.read_bytes(), decoder)
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_bytes(result)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()

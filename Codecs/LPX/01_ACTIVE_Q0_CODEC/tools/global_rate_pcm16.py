#!/usr/bin/env python3
"""A3: global block-rate allocation, followed by exact native acceptance.

Pareto/DP combines 80-sample bit-width/scale alternatives. Its local costs
use the current decoder state and pitch history: they are a surrogate, not
an additive model of the final stream. Each proposed allocation is repacked
in full, C++ decoded, model checked, and gated against ORIGINAL size, full
PCM16 error, STOI and native read-cost peaks. The MCU decoder is unchanged.
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import time
import numpy as np
import soundfile as sf
from lpx4 import decode, encode, BitWriter
from fast_lpx4 import select_chunk_fast
from rice_v4_reference import write_scale, plane_cost
from q0_model import coefficient_trace, table, synthesize, trace_states
from wav_to_lpx4 import quantize_trial, quality
from tune_pcm16 import read_wav16
from batch_decoder import BatchSession
from optimize_q0 import cost_probe, probe
from output_paths import protect_outputs


@dataclass(slots=True)
class _Node:
    cost: int
    loss: float
    previous: object
    choice: int


def allocate(curves, budget, max_states=1024):
    """Multiple-choice Pareto DP; exact unless its explicit state cap prunes.

    Input curves contain (integer bit cost, nonnegative local loss) pairs.
    Returned paths are nondominated in the retained search, not a claim about
    the true codec objective. The tiny unconstrained case is brute-force tested.
    """
    if budget < 0 or max_states < 2:
        raise ValueError('Invalid DP bit budget or state cap')
    frontier = [_Node(0, 0., None, -1)]
    pruned = peak = 0
    for curve in curves:
        if not curve or any(c < 0 or int(c) != c or not np.isfinite(v) or v < 0 for c, v in curve):
            raise ValueError('Invalid rate/distortion curve')
        choices = {}
        for node in frontier:
            for index, (cost, loss) in enumerate(curve):
                total = node.cost + int(cost)
                if total > budget:
                    continue
                value = node.loss + loss
                if total not in choices or value < choices[total][0]:
                    choices[total] = value, node, index
        best = float('inf')
        kept = []
        for cost in sorted(choices):
            loss, previous, index = choices[cost]
            if loss < best:
                kept.append((cost, loss, previous, index))
                best = loss
        peak = max(peak, len(kept))
        if len(kept) > max_states:
            pruned += len(kept) - max_states
            kept = [kept[i] for i in np.linspace(0, len(kept) - 1, max_states, dtype=int)]
        frontier = [_Node(*item) for item in kept]
        if not frontier:
            break
    paths = []
    for node in frontier:
        selected, current = [], node
        while current.previous is not None:
            selected.append(current.choice)
            current = current.previous
        if len(selected) == len(curves):
            paths.append((node.cost, node.loss, tuple(reversed(selected))))
    return paths, {'pruned_states': pruned, 'peak_frontier_states': peak,
                   'retained_states': len(paths), 'state_cap': max_states}


@dataclass
class _Option:
    cost: int
    loss: float
    bits: int
    scale: int
    q: np.ndarray
    baseline: bool = False


def _document(header, frames, blocks):
    raw = bytearray(header)
    raw[:5] = b'L3AV\x01'
    return {'raw': bytes(raw), 'sampleCount': int.from_bytes(raw[8:12], 'little'),
            'frames': frames, 'blocks': blocks}


def _frame_bits(frames):
    return sum(1 if f[0] == 0 else 102 if f[0] == 5 else 3 + min(80, plane_cost(f[1:])) for f in frames)


def _block_bits(q, bits, scale, previous_scale, history):
    writer = BitWriter()
    write_scale(writer, previous_scale, scale)
    cost = 3 + writer.total
    history = list(history[-145:])
    for start in range(0, len(q), 40):
        chunk = q[start:start + 40].tolist()
        cost += select_chunk_fast(chunk, history, bits)[0]
        history.extend(chunk)
    return int(cost)


def _options(ref, blocks, q, co, steps, pre, bright):
    pcm, histories, previous, clips = trace_states(q, np.asarray([b['scale'] for b in blocks]), co, steps, pre, bright)
    all_options = []
    for bi, block in enumerate(blocks):
        start, end = bi * 80, min(len(ref), (bi + 1) * 80)
        old_q = q[start:end].copy()
        old_scale, old_bits = block['scale'], block['bits']
        prev_scale = blocks[bi - 1]['scale'] if bi else 0
        history = q[max(0, start - 145):start].tolist()
        diff = ref[start:end].astype(np.float64) - pcm[start:end]
        opts = [_Option(_block_bits(old_q, old_bits, old_scale, prev_scale, history),
                        float(np.dot(diff, diff)), old_bits, old_scale, old_q, True)]
        rms = max(1., float(np.sqrt(np.mean((ref[start:end].astype(float) / 2) ** 2))))
        for bits in (0, 2, 3, 4, 5, 6):
            if bits == 0:
                scales = {prev_scale, old_scale, 0}
            else:
                seed = round(128 + 16 * np.log2(max(1., rms / ((1 << (bits - 1)) - .5)) / 16.384))
                center = old_scale + 16 * (old_bits - bits) if old_bits and steps[old_scale] else seed
                scales = {max(0, min(255, center + d)) for d in (-16, -8, -4, 0, 4, 8, 16)}
                scales.add(max(0, min(255, seed)))
            for scale in sorted(scales):
                if bits and steps[scale] == 0:
                    continue
                codes, loss, _, _, _ = quantize_trial(ref[start:end], co[start:end], histories[bi],
                    previous[bi], clips[bi], pre, bright, int(steps[scale]), bits)
                cost = _block_bits(codes, bits, scale, prev_scale, history)
                opts.append(_Option(cost, float(loss), bits, scale, codes))
        # Keep the original block, plus the local rate/distortion frontier.
        best, retained = float('inf'), [opts[0]]
        for op in sorted(opts[1:], key=lambda v: (v.cost, v.loss, v.bits, v.scale)):
            if op.loss < best:
                retained.append(op)
                best = op.loss
        all_options.append(retained)
    return all_options, pcm


def _materialize(header, frames, options, choices, ref, co, steps, pre, bright, refit):
    hist, previous, clipped = np.zeros(10, np.int64), 0, 0
    blocks = []
    for bi, (curve, choice) in enumerate(zip(options, choices)):
        op = curve[choice]
        codes = op.q
        if refit:
            start, end = bi * 80, min(len(ref), (bi + 1) * 80)
            codes, _, hist, previous, clipped = quantize_trial(ref[start:end], co[start:end],
                hist, previous, clipped, pre, bright, int(steps[op.scale]), op.bits)
        blocks.append({'bits': op.bits, 'scale': op.scale, 'q': codes.tolist()})
    return encode(_document(header, frames, blocks), fast=True)[0]


def optimize(blob, ref, decoder, rounds=2, max_states=1024, max_candidates=32,
             kind='speech', max_cost_growth=0., probe_executable=None,timing_gate=None):
    ref = np.asarray(ref)
    if ref.ndim != 1 or ref.dtype.kind not in 'iu' or np.any(ref < -32768) or np.any(ref > 32767):
        raise ValueError('Expected mono integer PCM16 reference')
    ref = ref.astype(np.int16)
    if not 1 <= rounds <= 4 or max_states < 2 or max_candidates < 1 or not 0 <= max_cost_growth <= .5:
        raise ValueError('Invalid search limits')
    if kind not in ('speech', 'music') or not 20 <= len(blob) <= 65535 or not 1 <= len(ref) <= 64000:
        raise ValueError('Expected one Q0 segment of <=64000 samples')
    first = decoder.decode_one_s16(blob, len(ref))
    if first is None:
        raise ValueError('Native decoder rejected the input/reference pair')
    frames, _, _ = decode(blob)
    co, steps = coefficient_trace(frames, len(ref)), table('scale_table.inc')
    pre, bright = int.from_bytes(blob[12:14], 'little'), int.from_bytes(blob[14:16], 'little')
    executable = Path(probe_executable) if probe_executable else cost_probe()
    old_cost = probe(blob, executable)
    before = quality(ref, first, kind)
    target = ref.astype(np.float64)
    def error(p):
        d = target - p
        return float(np.dot(d, d))
    cur, pcm, best_error = blob, first, error(first)
    original_size = len(blob)
    trials, accepted, searches, seen = [], [], [], {hashlib.sha256(blob).digest()}
    started = time.perf_counter()

    def consider(candidate, label, allow_repack=True):
        nonlocal cur, pcm, best_error
        digest = hashlib.sha256(candidate).digest()
        if digest in seen or len(trials) >= max_candidates:
            return
        seen.add(digest)
        record = {'source': label, 'bytes': len(candidate), 'accepted': False}
        trials.append(record)
        if len(candidate) > original_size:
            record['rejected'] = 'actual byte cap'
            return
        decoded = decoder.decode_one_s16(candidate, len(ref))
        if decoded is None:
            raise AssertionError('Generated stream failed native decoding')
        ff, bb, qq = decode(candidate)
        if ff != frames or not np.array_equal(decoded, synthesize(np.asarray(qq, np.int64),
                np.asarray([b['scale'] for b in bb]), co, steps, pre, bright)):
            raise AssertionError('Independent bitstream/model/native verification failed')
        sse = error(decoded)
        if (sse, len(candidate)) >= (best_error, len(cur)):
            record['rejected'] = 'complete waveform objective'
            return
        met = quality(ref, decoded, kind)
        if before['stoi'] is not None and met['stoi'] < before['stoi'] - 1e-12:
            record['rejected'] = 'original STOI floor'
            return
        cost = probe(candidate, executable)
        fields = ('bit_calls', 'rom_reads', 'max_bit_calls_sample', 'max_bit_calls_80', 'max_bit_calls_160')
        timing=timing_gate(candidate) if timing_gate else None
        proxy_bad=(cost['samples'] != old_cost['samples'] or cost['lsf_converts'] != old_cost['lsf_converts'] or
                any(cost[k] > old_cost[k] * (1 + max_cost_growth) for k in fields))
        if (timing is not None and not timing['accepted']) or (timing is None and proxy_bad):
            record['rejected'] = 'AVR cycle cap' if timing is not None else 'native decode-cost proxy cap'
            record['timing']=timing
            record['decode_cost'] = cost
            if allow_repack:
                for slack in (4, 16, 40):
                    if len(trials) >= max_candidates:
                        break
                    repacked=encode(_document(blob[:20],ff,bb),fast=True,raw_slack_bits=slack)[0]
                    consider(repacked,label+f':raw_slack={slack}',allow_repack=False)
            return
        record.update(accepted=True, quality=met, decode_cost=cost,timing=timing)
        cur, pcm, best_error = candidate, decoded, sse
        accepted.append(len(trials) - 1)

    for iteration in range(rounds):
        if len(trials) >= max_candidates:
            break
        beginning = cur
        ff, blocks, qq = decode(cur)
        # Exact zero excitation does not need a nonzero bit width.
        for policy in ('original', 'previous', 'zero'):
            transformed, previous_scale = [], 0
            for block in blocks:
                b = dict(block)
                if not any(b['q']):
                    b['bits'] = 0
                    b['scale'] = previous_scale if policy == 'previous' else 0 if policy == 'zero' else b['scale']
                transformed.append(b)
                previous_scale = b['scale']
            consider(encode(_document(blob[:20], ff, transformed), fast=True)[0], f'{iteration + 1}:zero:{policy}')
        if best_error == 0 or len(trials) >= max_candidates:
            break
        ff, blocks, qq = decode(cur)
        options, model_pcm = _options(ref, blocks, np.asarray(qq, np.int64), co, steps, pre, bright)
        if not np.array_equal(model_pcm, pcm):
            raise AssertionError('Prefix states differ from native baseline')
        budget = 8 * original_size - 160 - _frame_bits(ff)
        for objective in ('absolute', 'normalized'):
            if len(trials) >= max_candidates:
                break
            curves = []
            for bi, curve in enumerate(options):
                energy = max(1024. ** 2, float(np.mean(target[bi * 80:(bi + 1) * 80] ** 2)))
                curves.append([(op.cost, op.loss / energy if objective == 'normalized' else op.loss) for op in curve])
            paths, stats = allocate(curves, max(0, budget), max_states)
            searches.append({'round': iteration + 1, 'objective': objective, **stats,
                             'blocks': len(options), 'options': sum(map(len, options))})
            indices = np.linspace(len(paths) - 1, 0, min(8, len(paths)), dtype=int) if paths else []
            for index in indices:
                _, _, choices = paths[index]
                for refit in (True, False):
                    if len(trials) >= max_candidates:
                        break
                    candidate = _materialize(blob[:20], ff, options, choices, ref, co, steps, pre, bright, refit)
                    consider(candidate, f'{iteration + 1}:{objective}:{index}:refit={refit}')
        if cur == beginning:
            break
    check = decoder.decode_one_s16(cur, len(ref))
    if check is None or not np.array_equal(pcm, check):
        raise AssertionError('Final independent native re-decode failed')
    return cur, pcm, {'before': before, 'after': quality(ref, pcm, kind),
        'input_bytes': original_size, 'output_bytes': len(cur),
        'input_sha256': hashlib.sha256(blob).hexdigest(), 'output_sha256': hashlib.sha256(cur).hexdigest(),
        'decoder_cost_before': old_cost, 'decoder_cost_after': probe(cur, executable),
        'max_cost_growth': max_cost_growth, 'trials': trials, 'accepted_trials': accepted, 'searches': searches,
        'decoder_source_sha256': hashlib.sha256((Path(__file__).resolve().parents[1]/'src/Lpx4HybridCore.cpp').read_bytes()).hexdigest(),
        'elapsed_seconds': time.perf_counter() - started,
        'contract': 'Original byte/SSE/STOI floors; '+('full AVR cycle caps' if timing_gate else 'native cost caps')+'; unchanged LPC/header/decoder',
        'native_proxy_caps_enforced':timing_gate is None,
        'surrogate_note': 'Local state/pitch/scale costs are estimates; full regenerated streams decide acceptance.',
        'avr_cycles_measured':bool(getattr(timing_gate,'avr_cycles_measured',False))}


def run(source, reference_wav, output, **kwargs):
    source, reference_wav, output = Path(source), Path(reference_wav), Path(output)
    protect_outputs([source, reference_wav],
        [output, output.with_suffix('.wav'), output.with_suffix('.json')], replace=(source, output))
    ref = read_wav16(reference_wav)
    with BatchSession('batch') as decoder:
        blob, pcm, report = optimize(source.read_bytes(), ref, decoder, **kwargs)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(blob)
    sf.write(str(output.with_suffix('.wav')), pcm, 8000, subtype='PCM_16')
    output.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('input', type=Path);ap.add_argument('reference_wav', type=Path);ap.add_argument('output', type=Path)
    ap.add_argument('--rounds', type=int, default=2)
    ap.add_argument('--max-states', type=int, default=1024)
    ap.add_argument('--max-candidates', type=int, default=32)
    ap.add_argument('--kind', choices=('speech', 'music'), default='speech')
    ap.add_argument('--max-cost-growth', type=float, default=0.)
    a = ap.parse_args()
    print(json.dumps(run(a.input, a.reference_wav, a.output, rounds=a.rounds, max_states=a.max_states,
        max_candidates=a.max_candidates, kind=a.kind, max_cost_growth=a.max_cost_growth), indent=2))

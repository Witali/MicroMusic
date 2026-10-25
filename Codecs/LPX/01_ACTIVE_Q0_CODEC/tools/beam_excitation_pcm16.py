#!/usr/bin/env python3
"""Delayed decisions over equal-length excitation codewords, host only.

Keep multiple alternatives (including temporarily worse paths) across a
20/40-sample window. Rank partial paths using unchanged-future rollout through
the original C++ decoder and an additional error tail. Accept only full-clip
SER/STOI improvements. Rice quotients, codeword widths and stream layout are
fixed. No MCU code, modes, tables or read-bit lengths are added.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from batch_decoder import BatchSession
from refine_excitation_pcm16 import scan_tokens
from refine_lsf_pcm16 import patch_bits
from tune_pcm16 import read_wav16
from wav_to_lpx4 import quality


def optimize(blob, ref, decoder, beam_width=4, window=20, tail=80,
             max_trials=2500, tokens_per_window=6, max_delta=2,
             stoi_drop=0., kind='speech', max_windows=None):
    if beam_width not in (1, 4, 8, 16) or window not in (20, 40) or tail < 0:
        raise ValueError('Expected beam 1/4/8/16, window 20/40 and nonnegative tail')
    if max_trials < 0 or not 1 <= tokens_per_window <= window or max_delta < 1:
        raise ValueError('Invalid search budget')
    if not 0 <= stoi_drop <= .01 or kind not in ('speech', 'music'):
        raise ValueError('Invalid quality gate')
    if max_windows is not None and max_windows < 1:
        raise ValueError('max_windows must be positive')
    if len(ref) != int.from_bytes(blob[8:12], 'little'):
        raise ValueError('Reference sample count mismatch')
    t0 = time.perf_counter()
    baseline = decoder.decode_one_s16(blob, len(ref))
    if baseline is None:
        raise ValueError('C++ decoder rejected baseline')
    before = quality(ref, baseline, kind)
    target = ref.astype(np.float64)

    def full_error(pcm):
        diff = target - pcm
        return float(np.dot(diff, diff))

    cur, current_pcm = blob, baseline
    best_error = initial_error = full_error(baseline)
    error = (target - baseline) ** 2
    starts = sorted(range(0, len(ref), window), key=lambda s: (-float(np.sum(error[s:s + window])), s))
    if max_windows is not None:
        starts = starts[:max_windows]
    trials = batches = visited = 0
    changes = []
    for start in starts:
        if trials >= max_trials or best_error == 0:
            break
        tokens = [t for t in scan_tokens(cur) if start <= t.sample < start + window and t.possible(max_delta)]
        # Limit branching positions, retaining temporal order within each window.
        tokens = sorted(sorted(tokens, key=lambda t: (-float((target[t.sample] - current_pcm[t.sample]) ** 2), t.sample))[:tokens_per_window], key=lambda t: t.sample)
        if not tokens:
            continue
        visited += 1
        end = min(len(ref), start + window + tail)

        def rank(state):
            data, pcm, total = state
            diff = target[start:end] - pcm[start:end]
            return float(np.dot(diff, diff)), total, data

        states = [(cur, current_pcm, best_error)]
        for tok in tokens:
            candidates, seen = [], {s[0] for s in states}
            for state, _, _ in states:
                for value, patch in tok.possible(max_delta):
                    trial = patch_bits(state, *patch)
                    if trial not in seen:
                        seen.add(trial)
                        candidates.append(trial)
            candidates = candidates[:max(0, max_trials - trials)]
            if not candidates:
                break
            pcms = decoder.decode_many_s16(candidates, len(ref))
            trials += len(candidates)
            batches += 1
            states.extend((data, pcm, full_error(pcm)) for data, pcm in zip(candidates, pcms) if pcm is not None)
            states.sort(key=rank)
            states = states[:beam_width]
        # Global gate includes the entire tail, not only the ranking window.
        for data, pcm, total in sorted(states, key=lambda s: (s[2], s[0])):
            if total >= best_error - 1e-9:
                break
            met = quality(ref, pcm, kind)
            if before['stoi'] is not None and met['stoi'] < before['stoi'] - stoi_drop - 1e-12:
                continue
            changes.append({'start_sample': start, 'sse_before': best_error, 'sse_after': total})
            cur, current_pcm, best_error = data, pcm, total
            break
    # Reparse and decode independently before returning an accepted candidate.
    final_tokens = scan_tokens(cur)
    original_tokens = scan_tokens(blob)
    signature = lambda ts: [(t.sample, t.offset, t.width, t.code_type, t.k, t.b, t.quotient) for t in ts]
    if len(cur) != len(blob) or signature(final_tokens) != signature(original_tokens):
        raise AssertionError('Equal-length excitation contract violated')
    native = decoder.decode_one_s16(cur, len(ref))
    if native is None or not np.array_equal(native, current_pcm):
        raise AssertionError('Final independent C++ decode mismatch')
    after = quality(ref, native, kind)
    if best_error > initial_error + 1e-9:
        raise AssertionError('Global waveform error increased')
    return cur, native, {'before': before, 'after': after, 'trials': trials, 'batches': batches,
                        'visited_windows': visited, 'accepted_windows': changes,
                        'beam_width': beam_width, 'window_samples': window, 'tail_samples': tail,
                        'tokens_per_window': tokens_per_window, 'max_delta': max_delta,
                        'input_bytes': len(blob), 'output_bytes': len(cur),
                        'input_sha256': hashlib.sha256(blob).hexdigest(),
                        'output_sha256': hashlib.sha256(cur).hexdigest(),
                        'codeword_structure_unchanged': True, 'elapsed_seconds': time.perf_counter() - t0,
                        'avr_cycles_measured': False}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('input', type=Path)
    ap.add_argument('reference_wav', type=Path)
    ap.add_argument('output', type=Path)
    ap.add_argument('--beam', type=int, choices=(1, 4, 8, 16), default=4)
    ap.add_argument('--window', type=int, choices=(20, 40), default=20)
    ap.add_argument('--tail', type=int, default=80)
    ap.add_argument('--max-trials', type=int, default=2500)
    ap.add_argument('--tokens-per-window', type=int, default=6)
    ap.add_argument('--kind', choices=('speech', 'music'), default='speech')
    a = ap.parse_args()
    ref = read_wav16(a.reference_wav)
    with BatchSession('batch') as decoder:
        blob, pcm, report = optimize(a.input.read_bytes(), ref, decoder, beam_width=a.beam,
            window=a.window, tail=a.tail, max_trials=a.max_trials,
            tokens_per_window=a.tokens_per_window, kind=a.kind)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_bytes(blob)
    a.output.with_suffix('.pcm16le').write_bytes(pcm.astype('<i2').tobytes())
    a.output.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()

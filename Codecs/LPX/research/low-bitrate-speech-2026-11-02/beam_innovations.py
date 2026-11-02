"""Bounded delayed innovation decisions with unchanged spectra/metadata.

See BEAM_PROTOCOL.md. This is a host-only proposal generator; the protected
incumbent and complete-output native/quality gates decide every admission.
"""
from __future__ import annotations

import time

import numpy as np
from numba import njit

from round_admission import RoundAdmission, fields
import speech_compact as compact
import speech_sparse80 as sparse
from encode_low_bitrate_speech import trial_group
from q0_model import coefficient_trace, table
from wav_lpc import pack_frames


@njit(cache=True)
def search_beam(reference, co, parameters, steps, pre, sparse80, width, clip_guard):
    group, block = (80, 320) if sparse80 else (20, 160)
    groups = len(reference)//group
    history = np.zeros((width, 10), np.int64)
    ring = np.zeros((width, 256), np.int64)
    dd = np.zeros(width, np.int64)
    cc = np.zeros(width, np.int64)
    costs = np.zeros(width, np.int64)
    paths = np.zeros((width, groups, 2), np.int64)
    active = 1
    evaluations = 0
    for at_group in range(groups):
        next_history = np.zeros((width, 10), np.int64)
        next_ring = np.zeros((width, 256), np.int64)
        next_dd = np.zeros(width, np.int64)
        next_cc = np.zeros(width, np.int64)
        next_costs = np.full(width, np.int64(9223372036854775807), np.int64)
        next_paths = np.zeros((width, groups, 2), np.int64)
        next_active = 0
        start = at_group*group
        scale, lag, gain = parameters[start//block]
        for parent in range(active):
            for code in range(64 if sparse80 else 16):
                position = code+((code+2)>>2)
                for sign in range(2):
                    amplitude = -8 if sign == 0 else (7 if sparse80 else 8)
                    loss, h, d, c, q, _ = trial_group(reference, co, history[parent],
                        dd[parent], cc[parent], ring[parent], start, group, steps[scale*8],
                        lag, gain, position, amplitude, pre, clip_guard)
                    evaluations += 1
                    total = costs[parent]+loss
                    slot = width
                    for rank in range(width):
                        if total < next_costs[rank]:
                            slot = rank
                            break
                    if slot == width:
                        continue
                    for rank in range(width-1, slot, -1):
                        next_costs[rank] = next_costs[rank-1]
                        next_history[rank] = next_history[rank-1]
                        next_ring[rank] = next_ring[rank-1]
                        next_dd[rank] = next_dd[rank-1]
                        next_cc[rank] = next_cc[rank-1]
                        next_paths[rank] = next_paths[rank-1]
                    next_costs[slot] = total
                    next_history[slot], next_ring[slot] = h, q
                    next_dd[slot], next_cc[slot] = d, c
                    next_paths[slot] = paths[parent]
                    next_paths[slot, at_group, 0] = position
                    next_paths[slot, at_group, 1] = amplitude
                    next_active = min(width, next_active+1)
        history, ring, dd, cc = next_history, next_ring, next_dd, next_cc
        costs, paths, active = next_costs, next_paths, next_active
    return paths[0], evaluations, costs[0]


def run(reference, incumbent, output, common, only, *, speech=True):
    n, sparse80, spectra, parameters, _, pre, bright = fields(incumbent)
    if len(reference) != n or n % 320 or bright:
        raise ValueError('Beam round requires the exact320-aligned zero-brightness target')
    shift = 4 if sparse80 else 5
    vectors = [[(int(value)<<shift)+(1<<(shift-1)) for value in vector]
               for vector in spectra for _ in range(2)]
    co = coefficient_trace(pack_frames(vectors), n)
    journal = RoundAdmission(reference, incumbent, output, common, only, speech=speech)
    started = time.perf_counter()
    for clip_guard in (False, True):
        for width in (2, 4):
            pulses, evaluations, loss = search_beam(np.asarray(reference, np.int64), co,
                np.asarray(parameters, np.int64), table('scale_table.inc'), pre,
                sparse80, width, clip_guard)
            blob = (sparse.pack(n, spectra, parameters, pulses.tolist(), pre, bright) if sparse80 else
                    compact.pack(n, 4, spectra, parameters, pulses.tolist(), pre, bright)[0])
            journal.add(blob, origin=dict(beam_width=width, clipping_guard=clip_guard,
                        proposal_loss=int(loss)),
                        work=dict(group_position_sign_trials=int(evaluations),
                                  trial_synthesized_samples=int(evaluations)*(80 if sparse80 else 20)))
    return journal.finish(operator='bounded-innovation-beam', seconds=time.perf_counter()-started,
                          new_complete_attempts=4, metadata_and_spectra_unchanged=True)

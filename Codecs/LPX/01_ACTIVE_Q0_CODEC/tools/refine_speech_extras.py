"""Optional-pulse refinement using the existing exact integer replay.

This low-level phase owns no LPC/controller policy. Callers supply validated
fields, an exact prefix state and their active-extra capacity.
"""
from __future__ import annotations

import numpy as np
from numba import njit

from enhance_speech_compact import advance, sse


@njit(cache=True)
def refit_extra_group(reference, co, params, pulses, extras, steps, pre, bright,
                      at, stop, hist, dd, cc, ring, active_count, capacity):
    """Return position, amplitude, local SSE and trials for one 40-sample group.

    Preserve the cheap refitter's candidate order, strict-improvement ties and
    amplitude rule. The caller-owned extras array is temporary trial storage;
    its original row is restored before normal return. No other field changes.
    """
    index = at//40
    original = extras[index].copy()
    best = original.copy()
    target = reference[at:stop]
    out, _, _, _, _ = advance(co, params, pulses, extras, steps, pre, bright,
                              at, stop, hist, dd, cc, ring)
    loss = sse(target, out)
    evaluations = 1
    valid = min(40, len(reference)-at)
    positions = np.zeros(40, np.uint8)
    peak, peak_error = 0, -1
    for j in range(valid):
        error = abs(np.int64(target[j])-np.int64(out[j]))
        if error > peak_error:
            peak_error, peak = error, j
    positions[peak] = 1
    if original[1]:
        for delta in (-1, 0, 1):
            pos = original[0]+delta
            if 0 <= pos < valid:
                positions[pos] = 1
    for pos in range(valid):
        if not positions[pos]:
            continue
        for amp in range(-8, 8):
            if not (amp in (-4, -2, 0, 2, 4) or abs(amp-original[1]) <= 1):
                continue
            if amp and not original[1] and active_count >= capacity:
                continue
            extras[index, 0] = pos if amp else -1
            extras[index, 1] = amp
            trialout, _, _, _, _ = advance(co, params, pulses, extras, steps, pre, bright,
                                          at, stop, hist, dd, cc, ring)
            trial = sse(target, trialout)
            evaluations += 1
            if trial < loss:
                loss, best = trial, extras[index].copy()
    extras[index] = original
    return best[0], best[1], loss, evaluations

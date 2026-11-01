"""Bounded closed-loop80-sample innovation fitting; original pitch seeds only."""
import numpy as np
from numba import njit
from s15_format import POSITIONS
from q0_model import clamp


@njit(cache=True)
def trial80(target, co, hist, dd, cc, ring, start, step, lag, gain, pos, amp, pre, bright):
    h = hist.copy()
    qring = ring.copy()
    output = np.empty(80, np.int16)
    loss = np.int64(0)
    for j in range(80):
        at = start+j
        q = min(31, max(-32, (gain*qring[(at-lag)&255]+8)>>4))
        q = min(31, max(-32, q+(amp if j == pos else 0)))
        qring[at&255] = q
        acc = np.int64(0)
        for k in range(10):
            acc += (co[at, k]*h[k])>>12
        pred = clamp(q*step-acc)
        for k in range(9, 0, -1):
            h[k] = h[k-1]
        h[0] = pred
        dd = clamp(pred+((pre*dd)>>14))
        clipped = clamp(dd, -16384, 16384)
        out = clamp(clipped-((bright*cc)>>14), -16384, 16384)
        cc = clipped
        output[j] = clamp(out*2, -32768, 32767)
        d = np.int64(output[j])-target[at]
        loss += d*d
    return loss, h, dd, cc, qring, output


@njit(cache=True)
def fit_frame(target, co, hist, dd, cc, ring, start, step, lag, gain, pre, bright):
    h = hist.copy()
    qring = ring.copy()
    pulses = np.empty((4, 2), np.int64)
    output = np.empty(320, np.int16)
    loss = np.int64(0)
    for group in range(4):
        at = start+group*80
        best = np.int64(9223372036854775807)
        best_pos = 0
        best_amp = -8
        for code in range(64):
            pos = code+((code+2)>>2)
            for amp in (-8, 7):
                err, _, _, _, _, _ = trial80(target, co, h, dd, cc, qring, at,
                                             step, lag, gain, pos, amp, pre, bright)
                if err < best:
                    best = err
                    best_pos, best_amp = pos, amp
        err, h, dd, cc, qring, out = trial80(target, co, h, dd, cc, qring, at,
                                           step, lag, gain, best_pos, best_amp, pre, bright)
        pulses[group, 0], pulses[group, 1] = best_pos, best_amp
        output[group*80:group*80+80] = out
        loss += err
    return loss, h, dd, cc, qring, pulses, output


@njit(cache=True)
def search(reference, co, steps, seed_params, pre, bright=0):
    n = len(reference)
    params = np.empty((n//320, 3), np.int64)
    pulses = np.empty((n//80, 2), np.int64)
    output = np.empty(n, np.int16)
    h, ring = np.zeros(10, np.int64), np.zeros(256, np.int64)
    dd = cc = 0
    # This inverse filter only proposes scale; it never changes target level.
    emphasized, residual = np.zeros(n, np.float64), np.zeros(n, np.float64)
    for j in range(n):
        emphasized[j] = reference[j]/2-(pre*(reference[j-1]/2) if j else 0)/16384
        residual[j] = emphasized[j]
        for k in range(10):
            if j > k:
                residual[j] += co[j, k]*emphasized[j-k-1]/4096
    frame_evaluations = 0
    pulse_evaluations = 0
    for fi in range(n//320):
        start = fi*320
        desired = max(1., np.sqrt(np.mean(residual[start:start+320]**2)*80)/7.5)
        center = int(np.rint((128+16*np.log2(desired/16.384))/8))
        center = max(1, min(31, center))
        seed_scale = min(31, max(seed_params[fi*2, 0], seed_params[fi*2+1, 0])+2)
        scales = np.asarray([max(0, center-1), center, min(31, center+1), seed_scale])
        # All lag candidates come from the frozen original-level seed track.
        lags = np.asarray([seed_params[fi*2, 1], seed_params[fi*2+1, 1]])
        gains = np.asarray([0, max(seed_params[fi*2, 2], seed_params[fi*2+1, 2]), 14])
        best = np.int64(9223372036854775807)
        best_scale, best_lag, best_gain = 0, 18, 0
        for si in range(len(scales)):
            if si and np.any(scales[:si] == scales[si]):
                continue
            scale = scales[si]
            for li in range(len(lags)):
                if li and np.any(lags[:li] == lags[li]):
                    continue
                lag = lags[li]
                for gi in range(len(gains)):
                    if gi and np.any(gains[:gi] == gains[gi]):
                        continue
                    gain = gains[gi]
                    err, _, _, _, _, _, _ = fit_frame(reference, co, h, dd, cc, ring,
                        start, steps[scale*8], lag, gain, pre, bright)
                    frame_evaluations += 1
                    pulse_evaluations += 4*128
                    if err < best:
                        best = err
                        best_scale, best_lag, best_gain = scale, lag, gain
        _, h, dd, cc, ring, pp, pcm = fit_frame(reference, co, h, dd, cc, ring,
            start, steps[best_scale*8], best_lag, best_gain, pre, bright)
        # Winner replay is additional paid work, not a free search result.
        pulse_evaluations += 4*128
        params[fi] = np.asarray([best_scale, best_lag, best_gain])
        pulses[fi*4:fi*4+4] = pp
        output[start:start+320] = pcm
    return params, pulses, output, frame_evaluations, pulse_evaluations

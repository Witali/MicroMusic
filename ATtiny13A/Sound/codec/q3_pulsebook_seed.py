"""Offline inverse-lattice seeds for fixed-timing four-by-sixteen pulse books.

Only returned integer frames, durations and 64 signed table values reach the
decoder. Training never shifts/crops the target or stretches a residual cycle.
"""
import math

import numpy as np
from numba import njit
from scipy.signal import find_peaks

from hq4_core import pack_stream
from q3_phasebook import inverse_residual
from q3_pulsebook import SCHEMA, legacy_tables, validate


@njit(cache=True)
def timing(frames, durations):
    """Exact oracle frame/lag schedule, including first frame's minus-one."""
    n = int(durations.sum())
    owner, lag = np.empty(n, np.int32), np.full(n, -1, np.int32)
    fi, next_t, period, phase = 0, int(durations[0])-1, 0, 0
    for t in range(n):
        if t == 0 or t == next_t:
            if t:
                fi = (fi+1) % len(frames)
                next_t += int(durations[fi])
            period, phase = int(frames[fi, 0]), int(frames[fi, 0])
        owner[t] = fi
        if period:
            phase = (phase-1) & 255
            if not phase:
                phase = period
                lag[t] = 0
            else:
                lag[t] = period-phase
    return owner, lag


@njit(cache=True)
def _signed(value):
    return ((value+128) & 255)-128


@njit(cache=True)
def _multiply(value, coefficient, nearest):
    value = _signed(value)
    if coefficient < 0:
        value = _signed(-value)
    return _signed((value*abs(coefficient)+(4 if nearest else 0)) >> 3)


@njit(cache=True)
def byte_inverse(target, frames, durations, nearest=False):
    """Exact modular inverse driven by target signed-byte output samples."""
    out = np.empty(len(target), np.int16)
    state = np.zeros(8, np.int32)
    fi, next_t, previous = 0, int(durations[0])-1, 0
    k = np.zeros(8, np.int32)
    for t in range(len(target)):
        if t == 0 or t == next_t:
            if t:
                fi = (fi+1) % len(frames)
                next_t += int(durations[fi])
            for j in range(4):
                k[2*j], k[2*j+1] = (int(frames[fi, 2+j]) & 15)-8, (int(frames[fi, 2+j]) >> 4)-8
        y = int(target[t])
        value = _signed(y-previous+(previous >> 1))
        previous = y
        z = value
        old = state.copy()
        state[0] = z
        for j in range(8):
            if j < 7:
                state[j+1] = _signed(old[j]+_multiply(value, k[j], nearest))
            value = _signed(value+_multiply(old[j], k[j], nearest))
        out[t] = value
    return out


def _balanced(wave):
    wave = np.clip(np.rint(wave), -7, 7).astype(np.int8)
    while int(wave.sum()):
        positive = wave.sum() > 0
        index = int(np.argmax(wave) if positive else np.argmin(wave))
        wave[index] += -1 if positive else 1
    return wave


def _stats(segment, period, ages=None):
    if not period:
        return np.zeros(16), np.zeros(16), float(np.dot(segment, segment))
    # First sample after every frame reset is lag1; period-th sample is lag0.
    lags = ((np.arange(len(segment)) if ages is None else ages)+1) % period
    keep = lags < 16
    return (np.bincount(lags[keep], weights=segment[keep], minlength=16),
            np.bincount(lags[keep], minlength=16).astype(float), float(np.dot(segment, segment)))


def _initial_book(sums, counts, active, balance):
    means = sums/np.maximum(counts, 1.)
    energies = np.sum(means*means, axis=1)
    selected = np.flatnonzero(active & (energies > 1e-10))
    if not len(selected):
        return legacy_tables()
    data = means[selected]/np.maximum(np.sqrt(energies[selected, None]), 1e-20)
    centres = [data[int(np.argmax(energies[selected]))].copy()]
    while len(centres) < 4:
        distance = np.min(np.sum((data[:, None, :]-np.array(centres)[None, :, :])**2, axis=2), axis=1)
        centres.append(data[int(np.argmax(distance))].copy())
    centres = np.asarray(centres)
    for _ in range(8):
        labels = np.argmin(np.sum((data[:, None, :]-centres[None, :, :])**2, axis=2), axis=1)
        for group in range(4):
            if np.any(labels == group):
                centres[group] = np.mean(data[labels == group], axis=0)
    out = []
    for centre in centres:
        wave = np.rint(centre*7/max(float(np.max(abs(centre))), 1e-20))
        out.append(_balanced(wave) if balance else np.clip(wave, -7, 7).astype(np.int8))
    return np.asarray(out, np.int8)


def _pitch_options(reference, residual, starts, stops, frames, local):
    options = []
    for index, frame in enumerate(frames):
        period = int(frame[0])
        candidates = {period}
        if period and local:
            candidates.update(p for p in range(period-2, period+3) if 1 <= p <= 126)
            centre = (int(starts[index])+int(stops[index]))//2
            left = max(0, min(len(reference)-512, centre-256))
            window = residual[left:left+min(512, len(reference))]
            window = window-window.mean()
            ac = np.array([np.dot(window[p:], window[:-p])/
                (np.linalg.norm(window[p:])*np.linalg.norm(window[:-p])+1e-20) for p in range(1, 127)])
            peaks, _ = find_peaks(ac)
            # Same generic 65..850-Hz source-analysis domain as LPC2. A
            # sufficiently periodic residual suggests alternatives, not a mask.
            peaks = peaks[(peaks+1 >= math.ceil(7500/850)) & (peaks+1 <= min(126, math.floor(7500/65)))]
            for peak in sorted(peaks, key=lambda p: -ac[p])[:2]:
                if ac[peak] >= .35:
                    candidates.add(int(peak)+1)
        options.append(sorted(candidates, key=lambda p: (abs(p-period), p)))
    return options


def initialize(reference, frames, durations, *, nearest=False, inverse='float',
               local_pitch=False, balance=True, iterations=8, noise_gain='incumbent', stream_budget=615):
    """Fit source packets under exact resets; return an independently decodable model.

    Residual least squares proposes a seed, not a perceptual acceptance test.
    The caller must rank exact oracle PCM against STOI/spectral/budget targets.
    """
    x = np.asarray(reference, float)
    f, d = np.asarray(frames), np.asarray(durations)
    validate(f, d, legacy_tables(), samples=len(x), stream_budget=stream_budget)
    if (x.ndim != 1 or len(x) < 3072 or not np.all(np.isfinite(x)) or inverse not in ('float', 'byte')
            or noise_gain not in ('incumbent', 'rms') or not 1 <= iterations <= 16):
        raise ValueError('Expected complete finite source and bounded seed configuration')
    f, d = f.astype(np.uint8).copy(), d.astype(np.uint16).copy()
    incumbent = f.copy()
    if inverse == 'float':
        residual = inverse_residual(x, f, d)*128
    else:
        target = np.clip(np.rint(x*128), -128, 127).astype(np.int16)
        residual = byte_inverse(target, f, d, nearest).astype(float)
    owner, _ = timing(f, d)
    starts = np.r_[0, np.cumsum(d.astype(int))[:-1]-1]
    stops = np.r_[starts[1:], len(x)-1]
    positions = [np.arange(start, stop) for start, stop in zip(starts, stops)]
    ages = [np.arange(len(row)) for row in positions]
    # The unchanged oracle advances back to frame0 at the final sample N-1.
    # Fit that sample at reset lag1, not as a continuation of either packet.
    positions[0] = np.r_[positions[0], len(x)-1]
    ages[0] = np.r_[ages[0], 0]
    options = _pitch_options(x, residual, starts, stops, f, local_pitch)
    cache = [[_stats(residual[indices], p, age) for p in opts]
             for indices, age, opts in zip(positions, ages, options)]
    sums = np.array([row[0][0] for row in cache])
    counts = np.array([row[0][1] for row in cache])
    book = _initial_book(sums, counts, f[:, 0] > 0, balance)
    best = None
    history = []
    total_bytes = len(pack_stream(f, d))
    for epoch in range(iterations):
        chosen = []
        total_error = 0.
        for i, (opts, row) in enumerate(zip(options, cache)):
            if not int(incumbent[i, 0]):
                if noise_gain == 'rms':
                    gain = int(np.clip(np.rint(np.sqrt(row[0][2]/max(1, len(positions[i])))), 0, 15))
                    f[i, 1] = (int(f[i, 1]) & 48) | gain
                chosen.append(0)
                continue
            choice = None
            for oi, (p, (s, c, energy)) in enumerate(zip(opts, row)):
                change = int(p > 63 and int(d[i]) != 192)-int(f[i, 0] > 63 and int(d[i]) != 192)
                if total_bytes+change > stream_budget:
                    continue
                dot, norm = book.astype(float)@s, (book.astype(float)**2)@c
                gains = np.clip(np.rint(dot/np.maximum(norm, 1e-20)), 0, 15).astype(int)
                errors = energy-2*gains*dot+gains*gains*norm
                mode = int(np.argmin(errors))
                item = (float(errors[mode]), oi, mode, int(gains[mode]), p, change)
                if choice is None or item[0] < choice[0]-1e-10:
                    choice = item
            error, oi, mode, gain, p, change = choice
            f[i, 0], f[i, 1] = p, mode*16+gain
            total_bytes += change
            total_error += error
            chosen.append(oi)
        score = float(total_error)
        voiced_samples = int(np.count_nonzero(incumbent[owner, 0]))
        history.append(dict(iteration=epoch+1, voiced_excitation_mse=score/max(1, voiced_samples), stream_bytes=len(pack_stream(f, d))))
        if best is None or score < best[0]:
            best = score, f.copy(), book.copy()
        numerator, denominator = np.zeros((4,16)), np.zeros((4,16))
        for i, oi in enumerate(chosen):
            if not f[i, 0]:
                continue
            mode, gain = int(f[i, 1] >> 4), int(f[i, 1] & 15)
            s, c, _ = cache[i][oi]
            numerator[mode] += gain*s
            denominator[mode] += gain*gain*c
        for mode in range(4):
            wave = np.where(denominator[mode] > 0, numerator[mode]/np.maximum(denominator[mode], 1e-20), book[mode])
            book[mode] = _balanced(wave) if balance else np.clip(np.rint(wave), -7, 7).astype(np.int8)
    _, f, book = best
    validate(f, d, book, samples=len(x), stream_budget=stream_budget)
    model = dict(schema=SCHEMA, sample_rate=7500, samples=len(x), tilt_shift=1, nearest=bool(nearest),
                 frames=f.tolist(), durations=d.tolist(), pulsebook=book.tolist())
    report = dict(inverse=inverse, local_pitch=bool(local_pitch), balance=bool(balance), noise_gain=noise_gain,
        iterations=iterations, stream_bytes=len(pack_stream(f, d)), history=history,
        target_analysis_quantization='Signed8bit rounding only for byte inverse' if inverse == 'byte' else 'Unchanged float source',
        alignment='Exact frame-reset lag windows; first sample lag1, lag0 at period-1; no phase shift/resampling',
        table_sums=book.astype(int).sum(axis=1).tolist(),
        changed_pitch_frames=int(np.sum(f[:, 0] != incumbent[:, 0])),
        residual_rms_pwm=float(np.sqrt(np.mean(residual**2))))
    return model, report

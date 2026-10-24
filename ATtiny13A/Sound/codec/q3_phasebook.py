"""PC exact-byte Q3/T1 prototype with learned periodic excitation cycles.

Pitch bytes are DDS increments in units of 32/65536 cycles per sample, not
the original period field. Phase remains continuous across voiced frames;
zero pitch selects unchanged LFSR noise. This is a separate, tagged profile.
"""
import numpy as np
from numba import njit
from hq4_q3 import multiply, signed


@njit(cache=True)
def render(frames, durations, waves):
    n = int(np.sum(durations))
    out = np.empty(n, np.uint8)
    states = np.zeros(8, np.int32)
    coefficients = np.zeros(8, np.int32)
    counts = np.zeros(4, np.int64)
    seed, phase, fi, next_t = 0xa7, 0, 0, int(durations[0])-1
    pitch = gain = mode = previous = 0
    length = waves.shape[1]
    for t in range(n):
        if t == 0 or t == next_t:
            if t:
                fi += 1
                if fi == len(frames):
                    fi = 0
                next_t += int(durations[fi])
            pitch = int(frames[fi, 0])
            gain, mode = int(frames[fi, 1]) & 15, (int(frames[fi, 1]) >> 4) & 3
            for j in range(4):
                value = int(frames[fi, 2+j])
                coefficients[j*2] = (value & 15)-8
                coefficients[j*2+1] = (value >> 4)-8
        if pitch:
            phase = (phase+(pitch << 5)) & 65535
            index = phase*length >> 16
            ex = int(multiply(int(waves[mode % waves.shape[0], index]), gain))
        else:
            low = seed & 1
            seed >>= 1
            if low:
                seed ^= 0xb8
            ex = -gain if seed & 1 else gain
        for j in range(7, -1, -1):
            old, coefficient = states[j], coefficients[j]
            counts[2] += int(old == -128 and coefficient < 0)
            raw = ex-multiply(old, coefficient)
            counts[0] += int(raw < -128 or raw > 127)
            ex = signed(raw)
            if j < 7:
                counts[2] += int(ex == -128 and coefficient < 0)
                raw = old+multiply(ex, coefficient)
                counts[1] += int(raw < -128 or raw > 127)
                states[j+1] = signed(raw)
        states[0] = ex
        raw = ex+previous-(previous >> 1)
        counts[3] += int(raw < -128 or raw > 127)
        previous = signed(raw)
        out[t] = (previous+128) & 255
    return out, counts


def inverse_residual(reference, frames, durations):
    """Offline float inverse of retained Q3 lattice and T1, for book learning."""
    x = np.asarray(reference, float)
    # Arbitrary overall source level disappears when each cycle is normalized.
    raw = x-.5*np.r_[0., x[:-1]]
    states = np.zeros(8)
    residual = np.empty(len(x))
    fi, next_t = 0, int(durations[0])-1
    k = np.zeros(8)
    for t in range(len(x)):
        if t == 0 or t == next_t:
            if t:
                fi = (fi+1) % len(frames)
                next_t += int(durations[fi])
            k[::2] = (frames[fi, 2:] & 15).astype(float)/8-1
            k[1::2] = (frames[fi, 2:] >> 4).astype(float)/8-1
        value = raw[t]
        previous = states.copy()
        states[0] = value
        for j in range(8):
            if j < 7:
                states[j+1] = previous[j]+k[j]*value
            value += k[j]*previous[j]
        residual[t] = value
    return residual


def learn_waves(reference, frames, durations, length=8, count=4):
    """Normalize actual residual cycles, align closure peaks and cluster them."""
    residual = inverse_residual(reference, frames, durations)
    cycles, owners = [], []
    offset = 0
    for fi, (frame, duration) in enumerate(zip(frames, durations)):
        period = int(frame[0])
        end = min(len(reference), offset+int(duration))
        if period >= 16:
            for start in range(offset, end-period+1, period):
                wave = residual[start:start+period].copy()
                wave -= wave.mean()
                norm = float(np.sqrt(np.mean(wave**2)))
                if norm < 1e-7:
                    continue
                peak = int(np.argmax(abs(wave)))
                wave = np.roll(wave, -peak)
                if wave[0] < 0:
                    wave = -wave
                # Periodic interpolation preserves the original selected cycle.
                wave = np.interp(np.arange(length)*period/length,
                                 np.arange(period+1), np.r_[wave, wave[0]])
                wave -= wave.mean()
                wave /= np.sqrt(np.mean(wave**2))+1e-20
                cycles.append(wave)
                owners.append(fi)
        offset = end
    if len(cycles) < count:
        raise ValueError('Not enough non-silent original residual cycles to learn a source book')
    cycles = np.asarray(cycles)
    centres = [cycles[int(np.argmax(np.sum(cycles**2, axis=1)))]]
    while len(centres) < count:
        distance = np.min(np.sum((cycles[:, None, :]-np.array(centres)[None, :, :])**2, axis=2), axis=1)
        centres.append(cycles[int(np.argmax(distance))])
    centres = np.asarray(centres)
    labels = np.zeros(len(cycles), int)
    for _ in range(12):
        labels = np.argmin(np.sum((cycles[:, None, :]-centres[None, :, :])**2, axis=2), axis=1)
        for group in range(count):
            if np.any(labels == group):
                centres[group] = np.mean(cycles[labels == group], axis=0)
    waves = np.empty((count, length), np.int8)
    for group, centre in enumerate(centres):
        wave = np.rint(centre/(np.max(abs(centre))+1e-20)*31).astype(int)
        # Exact zero cycle sum avoids adding a periodic DC component.
        while wave.sum():
            index = int(np.argmax(wave)) if wave.sum() > 0 else int(np.argmin(wave))
            wave[index] -= 1 if wave.sum() > 0 else -1
        waves[group] = wave
    selected = np.zeros(len(frames), int)
    for fi in range(len(frames)):
        local = labels[np.asarray(owners) == fi]
        if len(local):
            selected[fi] = int(np.argmax(np.bincount(local, minlength=count)))
    return waves, selected

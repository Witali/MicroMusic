"""Initial, rate-constrained HQ4 encoding for arbitrary complete recordings.

Analysis only proposes a starting point: all ranking and search use the exact
signed-byte decoder. There are no phrase names, speaker-specific F0 limits or
hand-marked phonemes. The stream remains compatible with the 406-byte decoder.
"""
import math
import random

import numpy as np
from scipy.signal import find_peaks
from pystoi import stoi

from auto_encoder import SpectralObjective
from hq4_core import pack_stream
from hq4_speech_search import deterministic_estoi, proposal, validate
from model import decode

VERSION = 'new-hq4-encoder-v1'
DECODER_BYTES = 406
MAX_STREAM_BYTES = 1024-DECODER_BYTES-1


def validate_reference(reference, sample_rate=7500):
    x = np.asarray(reference, dtype=np.float64)
    if (sample_rate != 7500 or x.ndim != 1 or len(x) < 3072
            or len(x) % 64 or not np.all(np.isfinite(x))):
        raise ValueError('Expected finite mono 7500-Hz PCM, >=3072 samples, length divisible by 64')
    if np.max(abs(x)) < 1e-6:
        raise ValueError('Cannot encode a silent reference')
    return x


def reflection_coefficients(x, scale=16):
    """Regularized order-eight autocorrelation LPC, quantized for Q4 lattice.

    The old C initializer used scale eight; it is retained as an alternative
    initializer, because the limited decoder range need not favor clipped LPC.
    The decoder actually multiplies by coefficient/16, with signed coefficients
    from -8 through 7. Analysis is not claimed to be a closed-form optimum.
    """
    y = np.asarray(x, dtype=float)*np.hanning(len(x))
    r = np.array([np.dot(y[k:], y[:len(y)-k]) for k in range(9)])
    r[0] *= 1.0001
    a = np.zeros(9)
    variance = max(r[0], 1e-14)
    result = []
    for m in range(1, 9):
        k = np.clip(-(r[m]+np.dot(a[1:m], r[m-1:0:-1]))/variance, -.97, .97)
        previous = a.copy()
        a[1:m] = previous[1:m]+k*previous[m-1:0:-1]
        a[m] = k
        variance = max(variance*(1-k*k), 1e-14)
        result.append(int(np.clip(round(k*scale), -8, 7))+8)
    return np.array(result[::2], np.uint8) | (np.array(result[1::2], np.uint8) << 4)


def pitch_period(x):
    """Soft local periodicity candidate, including a genuine unvoiced option."""
    y = np.asarray(x, dtype=float)
    y = y-np.mean(y)
    y = np.r_[y[0], y[1:]-.65*y[:-1]]
    if np.dot(y, y) < 1e-10:
        return 0
    correlations = np.zeros(127)
    for lag in range(12, min(127, len(y)//2)):
        a, b = y[lag:], y[:-lag]
        correlations[lag] = np.dot(a, b)/(np.linalg.norm(a)*np.linalg.norm(b)+1e-20)
    peaks, _ = find_peaks(correlations)
    peaks = peaks[(peaks >= 12) & (peaks <= 126)]
    if not len(peaks):
        return 0
    peak = int(peaks[np.argmax(correlations[peaks]-.0003*peaks)])
    if correlations[peak] < .28:
        return 0
    # Prefer the first strong peak to an integer multiple of the same period.
    choices = peaks[correlations[peaks] >= max(.28, correlations[peak]*.92)]
    return int(choices[0]) if len(choices) else peak


def analyze(reference, *, hop=128, preemphasis=0., coefficient_scale=16):
    x = validate_reference(reference)
    if hop not in (64, 128, 256):
        raise ValueError('HQ4 analysis hop must be 64, 128 or 256')
    frames, durations = [], []
    emphasized = np.r_[x[0], x[1:]-preemphasis*x[:-1]]
    rms_max = max(float(np.sqrt(np.mean(x*x))), .001)
    for start in range(0, len(x), hop):
        length = min(hop, len(x)-start)
        center = start+length//2
        left = max(0, min(len(x)-256, center-128))
        window = x[left:left+256]
        period = pitch_period(window)
        rms = float(np.sqrt(np.mean(x[start:start+length]**2)))
        # Relative energy survives global RMS matching in the objective. Gains
        # near 15 improve the eight-bit signal/noise ratio without silent pads.
        gain = int(np.clip(round(rms/rms_max*(9 if period else 5)), 0, 15))
        if rms < rms_max*.025:
            gain = 0
        coeff = reflection_coefficients(emphasized[left:left+256], coefficient_scale)
        frames.append([period, gain, *map(int, coeff)])
        durations.append(length)
    return np.asarray(frames, np.uint8), np.asarray(durations, np.uint16)


def reuse_coefficients(frames, threshold):
    """Share spectral halves only when their Q4 coefficient distance is small.

    Increasing threshold monotonically saves update opportunities, although the
    serialized byte count also depends on how future frames reference updates.
    This never removes samples or changes pitch, gain or excitation duration.
    """
    f = frames.copy()
    previous = f[0, 2:].copy()
    for row in f[1:]:
        for half in (slice(0, 2), slice(2, 4)):
            new, old = row[2:][half], previous[half]
            a = np.r_[new & 15, new >> 4].astype(int)
            b = np.r_[old & 15, old >> 4].astype(int)
            if float(np.mean((a-b)**2)) <= threshold:
                row[2:][half] = old
        previous = row[2:].copy()
    return f


class Objective(SpectralObjective):
    def evaluate(self, frames, durations, *, full=False):
        pcm = decode(frames, durations, 0)
        signed = pcm.astype(np.int16)-128
        peak = int(np.max(abs(signed)))
        steps = int(np.sum(abs(np.diff(signed)) >= 48))
        if peak > 115 or steps:
            return None
        audio = signed.astype(float)/128
        spectral = self.spectrum(audio)
        quality = float(stoi(self.reference, audio, self.sr))
        if not math.isfinite(quality):
            return None
        # STOI has priority but a measurable spectral cost prevents its most
        # conspicuous timbre failures. No score is described as human quality.
        score = dict(**spectral, stoi=quality,
                     objective=quality-.08*spectral['loss'], peak_signed=peak,
                     steps_ge_48=steps, stream_bytes=len(pack_stream(frames, durations)))
        if full:
            score['estoi'] = deterministic_estoi(self.reference, audio, self.sr)
        return score


def initial_model(reference, *, stream_budget=MAX_STREAM_BYTES):
    """Select the best exact-decoded, size-feasible automatic initialization."""
    x = validate_reference(reference)
    if not 8 <= stream_budget <= MAX_STREAM_BYTES:
        raise ValueError('Stream budget must be between 8 and 617 bytes')
    objective = Objective(x)
    best = None
    trials = []
    seen = set()
    for hop in (128, 256, 64):
        # Two bytes per frame, plus first four coefficients, is the format's
        # lower bound. Reject impossible grids before doing their LPC analysis.
        if 2*math.ceil(len(x)/hop)+4 > stream_budget:
            continue
        for emphasis, scale in ((0., 16), (.65, 16), (.65, 8)):
            base, durations = analyze(x, hop=hop, preemphasis=emphasis, coefficient_scale=scale)
            for threshold in (0., .5, 1.5, 3., 6., 12., 24., 64., 225.):
                shared = reuse_coefficients(base, threshold)
                if len(pack_stream(shared, durations)) > stream_budget:
                    continue
                for gain_scale in (1., .65, .35):
                    frames = shared.copy()
                    gains = np.rint((frames[:, 1] & 15)*gain_scale).astype(np.uint8)
                    frames[:, 1] = (frames[:, 1] & 48) | gains
                    packed = pack_stream(frames, durations)
                    if packed in seen:
                        continue
                    seen.add(packed)
                    score = objective.evaluate(frames, durations)
                    settings = dict(hop=hop, preemphasis=emphasis, coefficient_scale=scale,
                                    reuse_threshold=threshold, gain_scale=gain_scale)
                    trials.append(dict(settings=settings, score=score))
                    if score is not None and (best is None or score['objective'] > best[2]['objective']):
                        best = frames.copy(), durations.copy(), score.copy(), settings
    if best is None:
        raise ValueError('No click-safe HQ4 initialization fits the complete recording in the stream budget')
    return best, trials


def search(reference, frames, durations, *, proposals=2000, seed=23105,
           stream_budget=MAX_STREAM_BYTES, progress=None):
    """Seeded joint frame/boundary optimization with exact synthesis checks.

    A new phrase has no archived HQ4 quality floor. Elite STOI cannot fall below
    the initial model, and its spectrum may worsen by at most three percent.
    The selected balanced objective, rather than either proxy alone, improves.
    """
    objective = Objective(validate_reference(reference))
    payload = validate(frames, durations, len(reference))
    if (proposals < 0 or not 8 <= stream_budget <= MAX_STREAM_BYTES
            or len(payload) > stream_budget):
        raise ValueError('Search must preserve samples and fit its positive proposal/byte budgets')
    first = objective.evaluate(frames, durations)
    if first is None:
        raise ValueError('Starting model exceeds peak or discontinuity limits')
    rng = random.Random(seed)
    best = frames.copy(), durations.copy(), first.copy()
    current = best
    evaluated = accepted = improvements = 0
    history = []
    for index in range(proposals):
        if index % 500 == 0:
            current = best
        anchor = best if rng.random() < .7 else current
        f, d = proposal(anchor[0], anchor[1], rng)
        if np.array_equal(f, anchor[0]) and np.array_equal(d, anchor[1]):
            continue
        # Reuse an existing spectral half instead of consuming scarce stream
        # bytes; these proposals allow compressed starts to change formants.
        if rng.random() < .15 and len(f) > 1:
            j = rng.randrange(1, len(f))
            half = slice(2, 4) if rng.randrange(2) else slice(4, 6)
            f[j, half] = f[j-1, half]
        if len(pack_stream(f, d)) > stream_budget:
            continue
        evaluated += 1
        score = objective.evaluate(f, d)
        if score is None:
            continue
        feasible = (score['stoi']+1e-12 >= first['stoi']
                    and score['loss'] <= first['loss']*1.03+1e-12)
        if feasible and score['objective'] > best[2]['objective']+1e-10:
            best = f.copy(), d.copy(), score.copy()
            improvements += 1
            history.append(dict(proposal=index+1, **score))
        temperature = .0015*(.05**((index % 500)/499))
        delta = score['objective']-current[2]['objective']
        if delta > 0 or rng.random() < math.exp(max(-700., min(0., delta/temperature))):
            current = f, d, score
            accepted += 1
        if progress and (index+1) % 500 == 0:
            progress(index+1, best[2])
    final = objective.evaluate(best[0], best[1], full=True)
    return best[0], best[1], dict(initial=first, final=final, proposals=proposals,
                                 evaluated=evaluated, accepted=accepted,
                                 improvements=improvements, history=history)

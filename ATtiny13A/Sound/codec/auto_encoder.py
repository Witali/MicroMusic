"""Feedback encoder: exact HQ4-T synthesis, spectral loss and resumable search.

The annealing working state may temporarily violate the STOI target; the saved
elite never does. Only the elite is exported. No AVR firmware changes are needed.
"""
import base64
import copy
import math
import random
import numpy as np
from scipy.signal import butter, sosfilt, stft
from pystoi import stoi
from hq4_core import pack_stream, unpack_stream
from hq4_timbre import decode

VERSION = 'hq4-auto-v1'
DECODER_BYTES = 422
MAX_STREAM_BYTES = 1024 - DECODER_BYTES - 1


class SpectralObjective:
    """Cached, level-independent comparison of audible 7.5 kHz PCM.

    Both signals pass through the same 70 Hz, second-order Butterworth highpass.
    The decoded output is RMS-matched to the reference. Loss combines mean log
    magnitude error (80%) and relative linear spectral error (20%), averaged
    over 128/256/512-sample Hann STFTs with 50% overlap. No time alignment or
    frequency warping is fitted. STOI is separately measured on unfiltered PCM.
    """
    def __init__(self, reference, sr=7500):
        self.reference = np.asarray(reference, dtype=np.float64)
        if sr != 7500 or self.reference.ndim != 1 or len(reference) < 3072:
            raise ValueError('Expected at least 3072 mono samples at 7500 Hz')
        if not np.all(np.isfinite(self.reference)):
            raise ValueError('Reference contains non-finite samples')
        self.sr = sr
        self.hp = butter(2, 70, fs=sr, btype='highpass', output='sos')
        filtered = sosfilt(self.hp, self.reference)
        self.rms = float(np.sqrt(np.mean(filtered * filtered)))
        if self.rms < 1e-6:
            raise ValueError('Reference is silent')
        self.targets = []
        for size in (128, 256, 512):
            mag = self.magnitude(filtered, size)
            self.targets.append((size, mag, np.log(np.maximum(mag, .0005)),
                                 float(np.linalg.norm(mag))))

    @staticmethod
    def magnitude(x, size):
        return abs(stft(x, nperseg=size, noverlap=size // 2)[2])

    def spectrum(self, signed_audio):
        x = sosfilt(self.hp, signed_audio)
        x *= self.rms / (np.sqrt(np.mean(x * x)) + 1e-10)
        log_error = linear_error = 0.
        for size, target, logged, norm in self.targets:
            mag = self.magnitude(x, size)
            log_error += float(np.mean(abs(np.log(np.maximum(mag, .0005)) - logged)))
            linear_error += float(np.linalg.norm(mag - target) / max(norm, 1e-10))
        log_error /= len(self.targets)
        linear_error /= len(self.targets)
        return dict(loss=.8 * log_error + .2 * linear_error,
                    log_spectral_error=log_error, relative_spectral_error=linear_error)

    def evaluate(self, frames, durations):
        pcm = decode(frames, durations)
        signed = pcm.astype(np.int16) - 128
        peak = int(np.max(abs(signed)))
        steps = int(np.sum(abs(np.diff(signed)) >= 48))
        if peak > 115 or steps:
            return None
        audio = signed.astype(np.float64) / 128
        return dict(**self.spectrum(audio), stoi=float(stoi(self.reference, audio, self.sr)),
                    peak_signed=peak, steps_ge_48=steps, stream_bytes=len(pack_stream(frames, durations)))


def validate_stream(frames, durations, samples):
    if frames.ndim != 2 or frames.shape[1] != 6 or not len(frames) or len(frames) != len(durations):
        raise ValueError('Invalid frame array')
    if int(np.sum(durations)) != samples or any(int(v) not in (64, 128, 192, 256) for v in durations):
        raise ValueError('Frame durations must preserve the exact reference length')
    if any(int(v) > 126 for v in frames[:, 0]) or any(int(v) > 63 for v in frames[:, 1]):
        raise ValueError('Invalid pitch/gain/excitation header')
    stream = pack_stream(frames, durations)
    if len(stream) > MAX_STREAM_BYTES:
        raise ValueError('Code, stream and end marker exceed 1024 bytes')
    return stream


def _field(row, dim, delta):
    if dim < 8:
        j, shift = 2 + dim // 2, 4 * (dim & 1)
        old = (int(row[j]) >> shift) & 15
        value = max(0, min(15, old + delta))
        row[j] = (int(row[j]) & (15 if shift else 240)) | (value << shift)
    elif dim == 8:
        row[1] = (int(row[1]) & 48) | max(0, min(15, (int(row[1]) & 15) + delta))
    elif dim == 9:
        row[1] = (int(row[1]) & 15) | (((int(row[1]) >> 4) + delta) % 4) << 4
    else:
        pitch = int(row[0])
        row[0] = max(16, min(126, pitch + delta)) if pitch else 0


def propose(frames, durations, rng):
    """Single, joint, correlated, boundary, split/merge and voicing proposals."""
    f, d = frames.copy(), durations.copy()
    idx = rng.randrange(len(f))
    kind = rng.randrange(100)
    if kind < 32:
        _field(f[idx], rng.randrange(11), rng.choice((-3, -2, -1, 1, 2, 3)))
    elif kind < 61:
        # Coordinated pitch/gain or reflection edits cross single-coordinate barriers.
        for _ in range(rng.randint(2, 4)):
            j = max(0, min(len(f) - 1, idx + rng.choice((-1, 0, 0, 1))))
            _field(f[j], rng.randrange(11), rng.choice((-2, -1, 1, 2)))
    elif kind < 78:
        dim, step = rng.randrange(11), rng.choice((-2, -1, 1, 2))
        for j in range(idx, min(len(f), idx + rng.randint(2, 4))):
            _field(f[j], dim, step)
    elif kind < 89 and len(f) > 1:
        idx = min(idx, len(f) - 2)
        change = rng.choice((-64, 64))
        a, b = int(d[idx]) + change, int(d[idx + 1]) - change
        if 64 <= a <= 256 and 64 <= b <= 256:
            d[idx], d[idx + 1] = a, b
    elif kind < 94:
        if d[idx] >= 128:
            length = int(d[idx])
            a = rng.choice(list(range(64, length, 64)))
            f = np.insert(f, idx + 1, f[idx], axis=0)
            d = np.insert(d, idx + 1, length - a); d[idx] = a
            _field(f[idx + rng.randrange(2)], rng.randrange(11), rng.choice((-1, 1)))
    elif kind < 98 and len(f) > 1:
        idx = min(idx, len(f) - 2)
        length = int(d[idx]) + int(d[idx + 1])
        if length <= 256:
            f[idx] = f[idx + rng.randrange(2)]
            f = np.delete(f, idx + 1, axis=0)
            d[idx] = length; d = np.delete(d, idx + 1)
    else:
        # Unlike the old local search, permit voiced/unvoiced transitions.
        f[idx, 0] = 0 if f[idx, 0] else rng.randint(18, 90)
    return f, d


def _tuples(value):
    return tuple(_tuples(v) for v in value) if isinstance(value, list) else value


class EncoderSearch:
    """Deterministic multistart annealing, elite retention and exact resume."""
    def __init__(self, objective, frames, durations, *, floor=.9005, seed=23062,
                 restart_every=3000, temperature=.008, checkpoint=None):
        self.objective = objective
        self.config = dict(version=VERSION, floor=floor, seed=seed,
                           restart_every=restart_every, temperature=temperature)
        if not 0 < floor < 1 or restart_every < 2 or not temperature > 0:
            raise ValueError('Invalid search configuration')
        validate_stream(frames, durations, len(objective.reference))
        score = objective.evaluate(frames, durations)
        if score is None or score['stoi'] < floor:
            raise ValueError('Starting stream must satisfy STOI, peak and step constraints')
        self.rng = random.Random(seed)
        self.current = (frames.copy(), durations.copy(), score)
        self.best = copy.deepcopy(self.current)
        self.initial = copy.deepcopy(score)
        self.proposals = self.evaluated = self.accepted = self.improvements = 0
        self.history = []
        if checkpoint:
            self.restore(checkpoint)

    def feasible(self, score):
        return score is not None and score['stoi'] >= self.config['floor']

    def energy(self, score):
        return score['loss'] + 40 * max(0., self.config['floor'] - score['stoi'])

    def step(self):
        cycle = self.proposals % self.config['restart_every']
        if cycle == 0:
            self.current = copy.deepcopy(self.best)
        # Keep testing the best feasible neighbourhood while an exploratory
        # chain is below the STOI floor. Otherwise all evaluations can be spent
        # improving an infeasible basin without ever improving the export.
        anchor = self.best if self.rng.random() < .5 else self.current
        f, d = propose(anchor[0], anchor[1], self.rng)
        self.proposals += 1
        if np.array_equal(f, anchor[0]) and np.array_equal(d, anchor[1]):
            return
        try:
            validate_stream(f, d, len(self.objective.reference))
        except ValueError:
            return
        score = self.objective.evaluate(f, d)
        self.evaluated += 1
        if score is None or score['stoi'] < self.config['floor'] - .02:
            return
        if self.feasible(score) and score['loss'] < self.best[2]['loss'] - 1e-9:
            self.best = (f.copy(), d.copy(), score.copy())
            self.improvements += 1
            self.history.append(dict(proposal=self.proposals, evaluated=self.evaluated, **score))
        # Fixed-length temperature cycles make a resumed run independent of its
        # stopping budget. The exported elite is never replaced by a worse state.
        temp = self.config['temperature'] * (.05 ** (cycle / (self.config['restart_every'] - 1)))
        delta = self.energy(score) - self.energy(self.current[2])
        if delta < 0 or self.rng.random() < math.exp(-min(700., max(0., delta / temp))):
            self.current = (f, d, score)
            self.accepted += 1

    def checkpoint(self):
        def snapshot(state):
            f, d, score = state
            return dict(stream=base64.b64encode(pack_stream(f, d)).decode('ascii'), score=score)
        return dict(config=self.config, proposals=self.proposals, evaluated=self.evaluated,
                    accepted=self.accepted, improvements=self.improvements, initial=self.initial,
                    best=snapshot(self.best), current=snapshot(self.current),
                    rng=self.rng.getstate(), history=self.history)

    def restore(self, checkpoint):
        if checkpoint['config'] != self.config:
            raise ValueError('Checkpoint configuration differs from the requested search')
        def snapshot(saved):
            f, d = unpack_stream(base64.b64decode(saved['stream'], validate=True))
            validate_stream(f, d, len(self.objective.reference))
            actual = self.objective.evaluate(f, d)
            if actual is None or any(abs(actual[k] - v) > 1e-10 for k, v in saved['score'].items()):
                raise ValueError('Checkpoint score does not reproduce with this objective/runtime')
            return f, d, actual
        self.best, self.current = snapshot(checkpoint['best']), snapshot(checkpoint['current'])
        if not self.feasible(self.best[2]):
            raise ValueError('Checkpoint elite violates the STOI constraint')
        for key in ('proposals', 'evaluated', 'accepted', 'improvements', 'initial', 'history'):
            setattr(self, key, copy.deepcopy(checkpoint[key]))
        self.rng.setstate(_tuples(checkpoint['rng']))

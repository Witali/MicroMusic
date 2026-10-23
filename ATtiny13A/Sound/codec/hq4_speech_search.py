"""Refine frozen HQ4 streams without weakening their intelligibility limits.

All search work is offline. The unchanged 406-byte assembler decodes the export.
Exploratory states may be worse; only a feasible, spectrally improved elite is
exported. Frequency-band envelopes supplement, rather than replace, STOI/eSTOI.
"""
import base64
import copy
import math
import random

import numpy as np
from pystoi import stoi

from auto_encoder import SpectralObjective, _tuples, propose
from hq4_core import pack_stream, unpack_stream
from model import decode

VERSION = 'hq4-speech-search-v1'
DECODER_BYTES = 406
MAX_STREAM_BYTES = 1024 - DECODER_BYTES - 1


def validate(frames, durations, samples):
    if (frames.ndim != 2 or frames.shape[1] != 6 or not len(frames)
            or durations.ndim != 1 or len(frames) != len(durations)
            or frames.dtype.kind not in 'ui' or durations.dtype.kind not in 'ui'):
        raise ValueError('Expected integer HQ4 frames and durations')
    if (np.any(frames < 0) or np.any(frames > 255) or np.any(frames[:, 0] > 126)
            or np.any(frames[:, 1] > 63)):
        raise ValueError('Invalid HQ4 field')
    if (int(np.sum(durations)) != samples
            or any(int(n) not in (64, 128, 192, 256) for n in durations)):
        raise ValueError('HQ4 durations must preserve the entire recording')
    payload = pack_stream(frames, durations)
    if len(payload) > MAX_STREAM_BYTES:
        raise ValueError('406-byte decoder, stream and marker exceed 1024 bytes')
    return payload


class SpeechObjective(SpectralObjective):
    def __init__(self, reference, sr=7500, *, band_objective=None, band_weight=.2):
        super().__init__(reference, sr)
        if not 0 <= band_weight <= 1:
            raise ValueError('Band weight must be between zero and one')
        self.band_objective = band_objective
        self.band_weight = band_weight if band_objective is not None else 0.

    def evaluate(self, frames, durations):
        pcm = decode(frames, durations, 0)
        signed = pcm.astype(np.int16) - 128
        peak = int(np.max(abs(signed)))
        steps = int(np.sum(abs(np.diff(signed)) >= 48))
        if peak > 115 or steps:
            return None
        audio = signed.astype(np.float64) / 128
        spectral = self.spectrum(audio)
        bands = self.band_objective.evaluate(audio) if self.band_objective is not None else {}
        spectral['spectral_loss'] = spectral.pop('loss')
        loss = ((1-self.band_weight)*spectral['spectral_loss']
                + self.band_weight*bands.get('band_loss', 0.))
        return dict(loss=float(loss), **spectral, **bands,
                    stoi=float(stoi(self.reference, audio, self.sr)),
                    estoi=float(stoi(self.reference, audio, self.sr, extended=True)),
                    peak_signed=peak, steps_ge_48=steps,
                    stream_bytes=len(pack_stream(frames, durations)))


def proposal(frames, durations, rng):
    # The existing HQ4-T structural search also works on the original format.
    # Explicit octave alternatives are soft candidates, never mandatory F0 masks.
    if rng.randrange(8):
        return propose(frames, durations, rng)
    f, d = frames.copy(), durations.copy()
    i = rng.randrange(len(f))
    p = int(f[i, 0])
    values = (p//2, p*2, p-1, p+1, p-2, p+2)
    target = rng.choice(values) if p else rng.randint(16, 126)
    if 16 <= target <= 126:
        f[i, 0] = target
        if i+1 < len(f) and rng.random() < .5:
            f[i+1, 0] = target
    return f, d


class SpeechSearch:
    def __init__(self, objective, frames, durations, *, seed=23101,
                 restart_every=1500, temperature=.004, checkpoint=None):
        if restart_every < 2 or not math.isfinite(temperature) or temperature <= 0:
            raise ValueError('Invalid search schedule')
        validate(frames, durations, len(objective.reference))
        score = objective.evaluate(frames, durations)
        if score is None or not all(math.isfinite(v) for v in score.values()):
            raise ValueError('Starting HQ4 exceeds peak/step limits or has invalid metrics')
        self.objective = objective
        self.config = dict(version=VERSION, seed=seed, restart_every=restart_every,
                           temperature=temperature, band_weight=objective.band_weight,
                           stoi_floor=score['stoi'], estoi_floor=score['estoi'],
                           spectral_ceiling=score['spectral_loss'],
                           log_spectral_ceiling=score['log_spectral_error'])
        self.initial = copy.deepcopy(score)
        self.best = (frames.copy(), durations.copy(), copy.deepcopy(score))
        self.current = copy.deepcopy(self.best)
        self.rng = random.Random(seed)
        self.proposals = self.evaluated = self.accepted = self.improvements = 0
        self.history = []
        if checkpoint is not None:
            self.restore(checkpoint)

    def feasible(self, score):
        return (score is not None and all(math.isfinite(v) for v in score.values())
                and score['stoi']+1e-12 >= self.config['stoi_floor']
                and score['estoi']+1e-12 >= self.config['estoi_floor']
                and score['spectral_loss'] <= self.config['spectral_ceiling']+1e-12
                and score['log_spectral_error'] <= self.config['log_spectral_ceiling']+1e-12)

    def energy(self, score):
        return (score['loss'] + 30*max(0., self.config['stoi_floor']-score['stoi'])
                + 15*max(0., self.config['estoi_floor']-score['estoi'])
                + 4*max(0., score['spectral_loss']-self.config['spectral_ceiling']))

    def step(self):
        cycle = self.proposals % self.config['restart_every']
        if cycle == 0:
            self.current = copy.deepcopy(self.best)
        anchor = self.best if self.rng.random() < .65 else self.current
        f, d = proposal(anchor[0], anchor[1], self.rng)
        self.proposals += 1
        if np.array_equal(f, anchor[0]) and np.array_equal(d, anchor[1]):
            return
        try:
            validate(f, d, len(self.objective.reference))
        except ValueError:
            return
        score = self.objective.evaluate(f, d)
        self.evaluated += 1
        if (score is None or not all(math.isfinite(v) for v in score.values())
                or score['stoi'] < self.config['stoi_floor']-.025
                or score['estoi'] < self.config['estoi_floor']-.04):
            return
        if self.feasible(score) and score['loss'] < self.best[2]['loss']-1e-10:
            self.best = (f.copy(), d.copy(), score.copy())
            self.improvements += 1
            self.history.append(dict(proposal=self.proposals, evaluated=self.evaluated, **score))
        temp = self.config['temperature']*(.05**(cycle/(self.config['restart_every']-1)))
        delta = self.energy(score)-self.energy(self.current[2])
        if delta < 0 or self.rng.random() < math.exp(-min(700., max(0., delta/temp))):
            self.current = (f, d, score)
            self.accepted += 1

    def checkpoint(self):
        def state(value):
            f, d, score = value
            return dict(stream=base64.b64encode(pack_stream(f, d)).decode('ascii'), score=score)
        return dict(config=self.config, initial=self.initial, proposals=self.proposals,
                    evaluated=self.evaluated, accepted=self.accepted,
                    improvements=self.improvements, history=self.history,
                    best=state(self.best), current=state(self.current), rng=self.rng.getstate())

    def restore(self, saved):
        if saved['config'] != self.config or saved['initial'] != self.initial:
            raise ValueError('HQ4 checkpoint configuration or baseline differs')
        def state(value):
            f, d = unpack_stream(base64.b64decode(value['stream'], validate=True))
            validate(f, d, len(self.objective.reference))
            score = self.objective.evaluate(f, d)
            if (score is None or score.keys() != value['score'].keys()
                    or any(abs(score[k]-v) > 1e-10 for k, v in value['score'].items())):
                raise ValueError('HQ4 checkpoint metrics do not reproduce')
            return f, d, score
        best, current = state(saved['best']), state(saved['current'])
        if not self.feasible(best[2]) or best[2]['loss'] > self.initial['loss']+1e-12:
            raise ValueError('HQ4 checkpoint elite violates the baseline guards')
        self.best, self.current = best, current
        for key in ('proposals', 'evaluated', 'accepted', 'improvements', 'history'):
            setattr(self, key, copy.deepcopy(saved[key]))
        self.rng.setstate(_tuples(saved['rng']))

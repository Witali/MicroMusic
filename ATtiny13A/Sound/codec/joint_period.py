"""Joint analysis-by-synthesis search in the existing period-residual v1 format.

Encoder-only changes. FrameSynth cache and residual contributions are linear;
the independently decoded exported model must agree to 1e-11. Retained elites
respect the initial STOI floor and an explicit absolute spectral-error ceiling.
"""
import base64
from copy import deepcopy
import math
import random
import numpy as np
from pystoi import stoi
from period_wave import FrameSynthesis, noise_colors, HOP, SR
from period_residual import decode_residual, pack_residual

VERSION = 'joint-period-v1'


def tuples(value):
    return tuple(tuples(x) for x in value) if isinstance(value, list) else value


class JointSynthesis:
    def __init__(self, model):
        self.base = FrameSynthesis(model['base'])
        self.template = deepcopy(model)
        count = len(model['gains'])
        centres = np.arange(count)*HOP+HOP/2
        position = np.interp(np.arange(self.base.samples), centres, np.arange(count))
        noise = noise_colors(self.base.samples)[12]*model['scale_u16']/65535/15
        self.residual = []
        for i, region in enumerate(self.base.slices):
            self.residual.append(noise[region]*np.maximum(0., 1-abs(position[region]-i)))

    def contribution(self, i, frame, gain):
        return self.base.contribution(i, frame) + self.residual[i]*gain

    def render(self, frames, gains):
        audio = np.zeros(self.base.samples)
        for i in range(len(frames)):
            audio[self.base.slices[i]] += self.contribution(i, frames[i], gains[i])
        return audio

    def model(self, frames, gains):
        model = deepcopy(self.template)
        model['base']['frames'] = frames.tolist()
        model['gains'] = gains.tolist()
        return model


class JointSearch:
    def __init__(self, model, objective, *, seed=23068, stoi_weight=6.,
                 spectral_ceiling=None, restart_every=1500, checkpoint=None):
        if stoi_weight <= 0 or restart_every < 2:
            raise ValueError('Invalid search configuration')
        self.objective = objective
        self.cache = JointSynthesis(model)
        frames = np.array(model['base']['frames'], dtype=int)
        gains = np.array(model['gains'], dtype=int)
        audio = self.cache.render(frames, gains)
        if not np.allclose(audio, decode_residual(model), atol=1e-11, rtol=0):
            raise ValueError('Initial cache differs from decoder')
        initial = self.score(audio)
        self.config = dict(version=VERSION, seed=seed, stoi_weight=stoi_weight,
                           spectral_ceiling=spectral_ceiling or initial['log_spectral_error']*1.15,
                           stoi_floor=initial['stoi'], restart_every=restart_every,
                           max_peak=max(.95, initial['peak']))
        self.initial = initial
        if not self.feasible(initial):
            raise ValueError('Initial model violates spectral ceiling')
        self.current = (frames, gains, audio, initial)
        self.best = deepcopy(self.current)
        self.rng = random.Random(seed)
        self.proposals = self.evaluated = self.accepted = self.improvements = 0
        self.history = []
        self.data_bytes = len(pack_residual(model))
        if checkpoint is not None:
            self.restore(checkpoint)

    def score(self, audio):
        return dict(**self.objective.spectrum(audio), stoi=float(stoi(self.objective.reference, audio, SR)),
                    peak=float(np.max(abs(audio))))

    def feasible(self, score):
        return (score['stoi'] >= self.config['stoi_floor']-1e-12 and
                score['log_spectral_error'] <= self.config['spectral_ceiling'] and
                score['peak'] <= self.config['max_peak'])

    def energy(self, score):
        return (score['loss'] + self.config['stoi_weight']*(1-score['stoi']) +
                50*max(0., score['log_spectral_error']-self.config['spectral_ceiling']) +
                50*max(0., self.config['stoi_floor']-score['stoi']) +
                50*max(0., score['peak']-self.config['max_peak']))

    def step(self):
        cycle = self.proposals % self.config['restart_every']
        if cycle == 0:
            self.current = deepcopy(self.best)
        anchor = self.best if self.rng.random() < .3 else self.current
        frames, gains, audio, score = anchor
        nf, ng, candidate = frames.copy(), gains.copy(), audio.copy()
        i = self.rng.randrange(len(frames))
        kind = self.rng.randrange(8)
        changed = {i}
        if kind == 7:
            changed.update(range(i, min(len(frames), i+self.rng.randint(2, 4))))
        for j in sorted(changed):
            if kind in (0, 3, 5, 7):
                nf[j, 2] = self.rng.randrange(8)
            if kind in (1, 3, 6):
                nf[j, 1] = self.rng.randrange(16)
            if kind in (2, 6):
                nf[j, 3] ^= 1
            if kind in (4, 5, 6, 7):
                ng[j] = self.rng.randrange(16)
            candidate[self.cache.base.slices[j]] += self.cache.contribution(j, nf[j], ng[j])-self.cache.contribution(j, frames[j], gains[j])
        self.proposals += 1
        if np.array_equal(nf, frames) and np.array_equal(ng, gains):
            return
        value = self.score(candidate)
        self.evaluated += 1
        energy, before = self.energy(value), self.energy(score)
        temperature = .003*(.2+.8*(1-cycle/self.config['restart_every']))
        if energy < before or self.rng.random() < math.exp(min(0., (before-energy)/temperature)):
            self.current = nf, ng, candidate, value
            self.accepted += 1
        if self.feasible(value) and energy < self.energy(self.best[3]):
            self.best = nf, ng, candidate, value
            self.improvements += 1
            self.history.append(dict(proposals=self.proposals, **value))

    def export(self):
        model = self.cache.model(self.best[0], self.best[1])
        exact = decode_residual(model)
        if not self.feasible(self.best[3]) or not np.allclose(exact, self.best[2], atol=1e-11, rtol=0):
            raise AssertionError('Invalid joint-search elite')
        if len(pack_residual(model)) != self.data_bytes:
            raise AssertionError('Joint search changed the payload budget')
        return model

    def checkpoint(self):
        def state(value):
            frames, gains, audio, score = value
            return dict(frames=frames.tolist(), gains=gains.tolist(), score=score,
                        audio_f64le=base64.b64encode(audio.astype('<f8').tobytes()).decode())
        return dict(config=self.config, initial=self.initial, current=state(self.current), best=state(self.best),
                    rng_state=self.rng.getstate(), proposals=self.proposals, evaluated=self.evaluated,
                    accepted=self.accepted, improvements=self.improvements, history=self.history)

    def restore(self, checkpoint):
        if checkpoint['config'] != self.config or checkpoint['initial'] != self.initial:
            raise ValueError('Checkpoint configuration or initial model differs')
        def state(value):
            return (np.array(value['frames'], dtype=int), np.array(value['gains'], dtype=int),
                    np.frombuffer(base64.b64decode(value['audio_f64le']), dtype='<f8').copy(), value['score'])
        self.current, self.best = state(checkpoint['current']), state(checkpoint['best'])
        self.rng.setstate(tuples(checkpoint['rng_state']))
        for field in ('proposals', 'evaluated', 'accepted', 'improvements', 'history'):
            setattr(self, field, checkpoint[field])
        self.export()

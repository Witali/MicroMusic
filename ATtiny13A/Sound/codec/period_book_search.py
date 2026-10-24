"""Jointly trained period shapes: sparse waveform derivatives, fixed payload.

Frame pitch/levels/noise stay fixed. Opposite coefficient edits preserve each
period's DC sum. The exact colored decoder verifies every exported elite.
"""
from copy import deepcopy
import math
import numpy as np
from colored_period import decode_colored, pack_colored, ColoredSynthesis
from joint_period import JointSearch
from period_wave import GAIN_LEVELS, HOP, PERIOD


class BookSynthesis:
    decode = staticmethod(decode_colored)
    pack = staticmethod(pack_colored)

    def __init__(self, model):
        self.template = deepcopy(model)
        samples = model['base']['samples']
        frames = np.array(model['base']['frames'], dtype=int)
        centres = np.arange(len(frames))*HOP+HOP/2
        position = np.interp(np.arange(samples), centres, np.arange(len(frames)))
        left = np.floor(position).astype(int)
        right = np.minimum(left+1, len(frames)-1)
        blend = position-left
        phase = model['base']['initial_phase_u16']/65536 + np.r_[0., np.cumsum(np.repeat(frames[:, 0], HOP)[:samples-1]*32/65536)]
        lookup = np.remainder(phase, 1)*PERIOD
        a = np.floor(lookup).astype(int) % PERIOD
        b, fraction = (a+1) % PERIOD, lookup-np.floor(lookup)
        amplitude = GAIN_LEVELS[frames[:, 2]]*model['base']['scale_u16']/65535*frames[:, 3]
        weights = np.zeros((16, samples))
        np.add.at(weights, (frames[left, 1], np.arange(samples)), amplitude[left]*(1-blend))
        np.add.at(weights, (frames[right, 1], np.arange(samples)), amplitude[right]*blend)
        self.basis = []
        for word in range(16):
            for k in range(PERIOD):
                support = np.flatnonzero((weights[word] != 0) & ((a == k) | (b == k)))
                values = weights[word, support]/7*((a[support] == k)*(1-fraction[support]) + (b[support] == k)*fraction[support])
                self.basis.append((support, values))
        zero = deepcopy(model)
        zero['base']['codebook'] = np.zeros((16, PERIOD), dtype=int).tolist()
        self.offset = decode_colored(zero)

    def render(self, book, gains=None):
        audio = self.offset.copy()
        for value, (indices, weights) in zip(np.asarray(book).ravel(), self.basis):
            audio[indices] += weights*value
        return audio

    def model(self, book, gains):
        model = deepcopy(self.template)
        model['base']['codebook'] = book.tolist()
        return model


class BookSearch(JointSearch):
    def __init__(self, model, objective, *, checkpoint=None, **kwargs):
        super().__init__(model, objective, cache_factory=ColoredSynthesis, **kwargs)
        self.config['search_kind'] = 'balanced-period-coefficients-v1'
        self.cache = BookSynthesis(model)
        audio = self.cache.render(model['base']['codebook'])
        if not np.allclose(audio, decode_colored(model), rtol=0, atol=1e-11):
            raise AssertionError('Book derivatives do not match decoder')
        # Retain initial exact audio/score from the superclass, so the hard floor
        # cannot be affected by the order used to sum the sparse derivatives.
        self.current = (np.array(model['base']['codebook'], dtype=int), self.current[1], self.current[2], self.current[3])
        self.best = deepcopy(self.current)
        if checkpoint is not None:
            self.restore(checkpoint)

    def step(self):
        cycle = self.proposals % self.config['restart_every']
        if cycle == 0:
            self.current = deepcopy(self.best)
        anchor = self.best if self.rng.random() < .3 else self.current
        book, gains, audio, score = anchor
        changed, candidate = book.copy(), audio.copy()
        word = self.rng.randrange(16)
        edits = {}
        for _ in range(2 if self.rng.random() < .2 else 1):
            first, second = self.rng.sample(range(PERIOD), 2)
            delta = self.rng.choice((-2, -1, 1, 2))
            edits[first] = edits.get(first, 0)+delta
            edits[second] = edits.get(second, 0)-delta
        self.proposals += 1
        if any(not -7 <= int(book[word, k])+delta <= 7 for k, delta in edits.items()):
            return
        for k, delta in edits.items():
            changed[word, k] += delta
            indices, weights = self.cache.basis[word*PERIOD+k]
            candidate[indices] += delta*weights
        if np.array_equal(changed, book):
            return
        value = self.score(candidate)
        self.evaluated += 1
        energy, before = self.energy(value), self.energy(score)
        temperature = .0015*(.2+.8*(1-cycle/self.config['restart_every']))
        if energy < before or self.rng.random() < math.exp(min(0., (before-energy)/temperature)):
            self.current = changed, gains, candidate, value
            self.accepted += 1
        if self.feasible(value) and energy < self.energy(self.best[3]):
            self.best = changed, gains, candidate, value
            self.improvements += 1
            self.history.append(dict(proposals=self.proposals, **value))

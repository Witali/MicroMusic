"""Deterministic analysis-by-synthesis using only the exact integer decoder.

No linear audio cache is used. Frame, phase and balanced codebook proposals
are fully rendered, including target rounding, saturation and the DC blocker.
The retained elite respects fixed STOI, spectrum, peak and data-size limits.
"""
import base64
from copy import deepcopy
import math
import random

import numpy as np
from pystoi import stoi

from fixed_period import decode_fixed, pack_fixed, unpack_fixed, validate


VERSION = 'fixed-speech-search-v2'


def _tuples(value):
    return tuple(_tuples(item) for item in value) if isinstance(value, list) else value


class FixedSearch:
    def __init__(self, model, objective, *, seed=23074, stoi_weight=8., stoi_floor=None,
                 spectral_ceiling=None, max_peak=.95, max_data_bytes=None,
                 restart_every=2000, dc_choices=(5, 6, 7), objective_kind='balanced', checkpoint=None):
        validate(model)
        if len(objective.reference) != model['samples']:
            raise ValueError('Reference/model duration mismatch')
        if stoi_weight <= 0 or restart_every < 2 or not 0 < max_peak < 1:
            raise ValueError('Invalid fixed search configuration')
        if objective_kind not in ('balanced', 'spectral'):
            raise ValueError('Objective must be balanced or spectral')
        if not dc_choices or any(value not in (0, 5, 6, 7) for value in dc_choices):
            raise ValueError('Invalid DC choices')
        if model.get('dc_block_shift', 0) not in dc_choices:
            raise ValueError('Initial DC setting must be included in dc_choices')
        self.objective = objective
        self.initial_model = deepcopy(model)
        initial_pcm = decode_fixed(model)
        initial = self.score(model, initial_pcm)
        self.config = dict(version=VERSION, objective=objective_kind, seed=seed, stoi_weight=float(stoi_weight),
                           stoi_floor=initial['stoi'] if stoi_floor is None else float(stoi_floor),
                           spectral_ceiling=initial['log_spectral_error']*1.1 if spectral_ceiling is None else float(spectral_ceiling),
                           max_peak=float(max_peak), max_data_bytes=len(pack_fixed(model)) if max_data_bytes is None else int(max_data_bytes),
                           restart_every=restart_every, dc_choices=list(dc_choices))
        self.initial = initial
        if not self.feasible(initial):
            raise ValueError('Initial model violates fixed search limits')
        self.current = (deepcopy(model), initial_pcm, initial)
        self.best = deepcopy(self.current)
        self.rng = random.Random(seed)
        self.proposals = self.evaluated = self.accepted = self.improvements = 0
        self.history = []
        if checkpoint is not None:
            self.restore(checkpoint)

    def score(self, model, pcm=None):
        pcm = decode_fixed(model) if pcm is None else pcm
        signed = pcm.astype(np.float64)-128
        audio = signed/128
        raw = decode_fixed(dict(model, dc_block_shift=0)) if model.get('dc_block_shift', 0) else pcm
        windows = [signed[start:start+64] for start in range(0, len(signed), 64)]
        return dict(**self.objective.spectrum(audio),
                    stoi=float(stoi(self.objective.reference, audio, self.objective.sr)),
                    peak=float(np.max(abs(audio))),
                    clips=int(np.sum((pcm == 0) | (pcm == 255))),
                    pre_dc_clips=int(np.sum((raw == 0) | (raw == 255))),
                    mean_pcm=float(np.mean(signed)),
                    max_abs_64_sample_mean=float(max(abs(np.mean(window)) for window in windows)),
                    data_bytes=len(pack_fixed(model)))

    def feasible(self, score):
        return (score['stoi'] >= self.config['stoi_floor']-1e-12 and
                score['log_spectral_error'] <= self.config['spectral_ceiling'] and
                score['peak'] <= self.config['max_peak'] and
                score['clips'] == score['pre_dc_clips'] == 0 and
                score['data_bytes'] <= self.config['max_data_bytes'])

    def energy(self, score):
        reward = self.config['stoi_weight']*(1-score['stoi']) if self.config['objective'] == 'balanced' else 0.
        return (score['loss']+reward+
                50*max(0., self.config['stoi_floor']-score['stoi'])+
                50*max(0., score['log_spectral_error']-self.config['spectral_ceiling'])+
                50*max(0., score['peak']-self.config['max_peak']))

    def propose(self, source):
        model = deepcopy(source)
        frames = model['frames']
        index = self.rng.randrange(len(frames))
        kind = self.rng.randrange(100)
        frame = frames[index]
        delta = self.rng.choice((-2, -1, 1, 2))
        if kind < 17:
            gain = (frame[1] >> 4) & 7
            gain = self.rng.randrange(8) if self.rng.random() < .2 else min(7, max(0, gain+delta))
            frame[1] = (frame[1] & 143) | gain << 4
        elif kind < 30:
            frame[1] = (frame[1] & 240) | self.rng.randrange(16)
        elif kind < 51:
            level, color = frame[2] & 15, frame[2] >> 4
            if self.rng.random() < .25:
                color = self.rng.randrange(4)
            else:
                level = min(15, max(0, level+delta))
            frame[2] = level | color << 4
        elif kind < 61 and len(frames) > 1:
            # Opposite pitch edits restore cumulative phase after a short region.
            other = min(len(frames)-1, index+self.rng.randint(1, 3))
            if other == index:
                other = index-1
            if 0 <= frame[0]+delta <= 255 and 0 <= frames[other][0]-delta <= 255:
                frame[0] += delta
                frames[other][0] -= delta
        elif kind < 65:
            model['initial_phase_u16'] = (model['initial_phase_u16']+self.rng.choice((-1, 1))*self.rng.choice((1, 4, 16, 32, 64, 128, 512))) & 65535
        elif kind < 89:
            # Preserve the DC sum of every trained waveform, including old sums.
            active = [value[1] & 15 for value in frames if value[1] & 128 and value[1] & 112]
            if active:
                word = model['codebook'][self.rng.choice(active)]
                first, second = self.rng.sample(range(32), 2)
                if -7 <= word[first]+delta <= 7 and -7 <= word[second]-delta <= 7:
                    word[first] += delta
                    word[second] -= delta
        elif kind < 92:
            frame[1] ^= 128
        elif kind < 98:
            for other in range(index, min(len(frames), index+self.rng.randint(2, 4))):
                level = min(15, max(0, (frames[other][2] & 15)+delta))
                frames[other][2] = (frames[other][2] & 48) | level
        else:
            model['dc_block_shift'] = self.rng.choice(self.config['dc_choices'])
        return model

    def step(self):
        cycle = self.proposals % self.config['restart_every']
        if cycle == 0:
            self.current = deepcopy(self.best)
        anchor = self.best if self.rng.random() < .35 else self.current
        model = self.propose(anchor[0])
        self.proposals += 1
        if model == anchor[0] or len(pack_fixed(model)) > self.config['max_data_bytes']:
            return
        pcm = decode_fixed(model)
        if np.array_equal(pcm, anchor[1]) or np.any((pcm == 0) | (pcm == 255)):
            return
        value = self.score(model, pcm)
        self.evaluated += 1
        if value['pre_dc_clips'] or value['peak'] > self.config['max_peak']:
            return
        energy, before = self.energy(value), self.energy(anchor[2])
        temperature = .0015*(.2+.8*(1-cycle/self.config['restart_every']))
        if energy < before or self.rng.random() < math.exp(min(0., (before-energy)/temperature)):
            self.current = model, pcm, value
            self.accepted += 1
        if self.feasible(value) and energy < self.energy(self.best[2]):
            self.best = model, pcm, value
            self.improvements += 1
            self.history.append(dict(proposals=self.proposals, **value))

    def export(self):
        model, pcm, value = self.best
        if (not self.feasible(value) or not np.array_equal(pcm, decode_fixed(model)) or
                model['noise_filters'] != self.initial_model['noise_filters']):
            raise AssertionError('Fixed search elite is invalid')
        restored = unpack_fixed(pack_fixed(model))
        if not np.array_equal(pcm, decode_fixed(restored)):
            raise AssertionError('Fixed payload roundtrip changed PCM')
        return deepcopy(model)

    def checkpoint(self):
        def state(value):
            model, pcm, score = value
            return dict(model=model, pcm_u8=base64.b64encode(pcm.tobytes()).decode(), score=score)
        return dict(config=self.config, initial=self.initial, current=state(self.current), best=state(self.best),
                    rng_state=self.rng.getstate(), proposals=self.proposals, evaluated=self.evaluated,
                    accepted=self.accepted, improvements=self.improvements, history=self.history)

    def restore(self, checkpoint):
        if checkpoint['config'] != self.config or checkpoint['initial'] != self.initial:
            raise ValueError('Fixed checkpoint configuration or initial model differs')
        def state(value):
            model = value['model']
            pcm = np.frombuffer(base64.b64decode(value['pcm_u8']), dtype=np.uint8).copy()
            if not np.array_equal(pcm, decode_fixed(model)) or value['score'] != self.score(model, pcm):
                raise ValueError('Fixed checkpoint PCM or score differs from exact decoder')
            return deepcopy(model), pcm, value['score']
        self.current, self.best = state(checkpoint['current']), state(checkpoint['best'])
        self.rng.setstate(_tuples(checkpoint['rng_state']))
        for field in ('proposals', 'evaluated', 'accepted', 'improvements', 'history'):
            setattr(self, field, deepcopy(checkpoint[field]))
        self.export()

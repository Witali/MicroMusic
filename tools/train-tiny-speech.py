#!/usr/bin/env python3
"""Automatically reduce a speech wave dictionary and retune exact integer PCM.

The merge stage renders every possible whole-word replacement through the
integer decoder. The refinement stage preserves the reduced dictionary and
the tiny decoder's feature set. No speech-specific frame edits are hard coded.
"""
import argparse
from copy import deepcopy
import importlib.metadata
import itertools
import json
from pathlib import Path
import sys

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0, str(CODEC))
from auto_encoder import SpectralObjective
from fixed_period import avr_features, decode_fixed, pack_avr_data, pack_fixed
from fixed_search import FixedSearch, decoder_constraints
from refine_period_helpers import atomic_json, digest, matched_audio


def active_words(model):
    return sorted({h & 15 for _, h, _ in model['frames'] if h & 128 and h & 112})


def canonicalize(model):
    """Densely number only audible waves; unused table entries stay zero."""
    result = deepcopy(model)
    words = active_words(result)
    mapping = {old:new for new,old in enumerate(words)}
    result['codebook'] = [result['codebook'][old] for old in words]
    result['codebook'] += [[0]*32 for _ in range(16-len(words))]
    for frame in result['frames']:
        header = frame[1]
        frame[1] = (header & 240) | (mapping[header & 15] if header & 128 and header & 112 else 0)
    return result


class TinySearch(FixedSearch):
    def __init__(self, model, objective, *, words, max_flash_data_bytes=None,
                 compression_level=None, target_flash_data_bytes=None, checkpoint=None, **kwargs):
        self.words = words
        self.max_flash_data_bytes = max_flash_data_bytes
        self.compression_level = compression_level
        self.target_flash_data_bytes = target_flash_data_bytes
        if compression_level is not None and not 0 <= compression_level <= 9:
            raise ValueError('Compression level must be 0..9')
        if target_flash_data_bytes is not None and target_flash_data_bytes < 1:
            raise ValueError('Target Flash data budget must be positive')
        super().__init__(model, objective, checkpoint=None, **kwargs)
        self.config.update(tiny_words=words, max_flash_data_bytes=max_flash_data_bytes)
        if compression_level is not None or target_flash_data_bytes is not None:
            self.config.update(compression_level=compression_level,
                               target_flash_data_bytes=target_flash_data_bytes)
        if checkpoint is not None:
            self.restore(checkpoint)

    def score(self, model, pcm=None):
        score = super().score(model, pcm)
        if (self.max_flash_data_bytes is not None or self.compression_level is not None or
                self.target_flash_data_bytes is not None):
            from tiny_period import pack_tiny
            score['tiny_flash_data_bytes'] = len(pack_tiny(model)['flash_data'])
        return score

    def energy(self, score):
        value = super().energy(score)
        if self.compression_level is None and self.target_flash_data_bytes is None:
            return value
        # Keep the exact speech/spectral objective and add a rate penalty.
        # With a target, stop rewarding size reduction once it is reached.
        level = 5 if self.compression_level is None else self.compression_level
        excess = score['tiny_flash_data_bytes']
        if self.target_flash_data_bytes is not None:
            excess = max(0, excess-self.target_flash_data_bytes)
        return value + excess*(.0005*level*level)

    def feasible(self, score):
        return (super().feasible(score) and (self.max_flash_data_bytes is None or
                                           score['tiny_flash_data_bytes'] <= self.max_flash_data_bytes))

    def compatible(self, model):
        return (super().compatible(model) and
                all(index < self.words for index in active_words(model)) and
                all(not any(word) for word in model['codebook'][self.words:]))

    def propose(self, source):
        if ((self.compression_level is not None or self.target_flash_data_bytes is not None) and
                self.rng.random() < .6):
            # Repeated parameters cost fewer bits. Evaluate every proposed
            # simplification by rendering it, including phase and DC state.
            proposal = deepcopy(source)
            frames = proposal['frames']
            start = self.rng.randrange(len(frames))
            stop = min(len(frames), start+self.rng.choice((2, 2, 3, 4, 6, 8)))
            field = self.rng.randrange(5)
            anchor = frames[self.rng.choice((start, stop-1))]
            if field == 0:
                # Preserve the phase increment across the region. Placing
                # the integer remainder at its end prevents cumulative drift.
                total = sum(f[0] for f in frames[start:stop])
                pitch = total//(stop-start)
                remainder = total-pitch*(stop-start)
                for offset, frame in enumerate(frames[start:stop]):
                    frame[0] = pitch + int(offset >= stop-start-remainder)
            else:
                masks = {1:112, 2:15, 3:127}
                if field in masks:
                    mask = masks[field]
                    value = anchor[1] & mask
                    for frame in frames[start:stop]:
                        frame[1] = (frame[1] & ~mask) | value
                else:
                    for frame in frames[start:stop]:
                        frame[2] = anchor[2]
            if self.config['voiced_only']:
                for frame in frames:
                    frame[1] |= 128
            for frame in frames:
                frame[1] = (frame[1] & 240) | ((frame[1] & 15) % self.words)
            return proposal
        proposal = super().propose(source)
        # FixedSearch can propose any four-bit index. Restrict it without
        # changing the shared decoder or the deterministic random stream.
        for frame in proposal['frames']:
            if frame[1] & 128 and frame[1] & 112:
                frame[1] = (frame[1] & 240) | ((frame[1] & 15) % self.words)
        return proposal


def merge_words(model, objective, target, *, weight=8., max_peak=.95,
                spectral_ceiling=.6, save=None):
    """Greedy exhaustive merges, chosen by exact output STOI and spectrum."""
    model = canonicalize(model)
    scorer = FixedSearch(model, objective, stoi_floor=0., spectral_ceiling=spectral_ceiling,
                         stoi_weight=weight, max_peak=max_peak, max_data_bytes=65535,
                         dc_choices=(model.get('dc_block_shift', 0),),
                         **decoder_constraints(model))
    history = []
    while len(active_words(model)) > target:
        words = active_words(model)
        best = None
        evaluated = 0
        for old in words:
            for replacement in words:
                if old == replacement:
                    continue
                candidate = deepcopy(model)
                for frame in candidate['frames']:
                    if frame[1] & 128 and frame[1] & 112 and frame[1] & 15 == old:
                        frame[1] = (frame[1] & 240) | replacement
                candidate = canonicalize(candidate)
                score = scorer.score(candidate)
                evaluated += 1
                if not scorer.feasible(score):
                    continue
                key = scorer.energy(score)
                if best is None or key < best[0]:
                    best = key, candidate, score, old, replacement
        if best is None:
            raise RuntimeError('No dictionary merge satisfies clipping/peak/spectrum limits')
        _, model, score, old, replacement = best
        report = dict(words=len(active_words(model)), removed_word=old, replacement_word=replacement,
                      evaluated=evaluated, avr_data_bytes=len(pack_avr_data(model, specialize=True)), **score)
        history.append(report)
        print(json.dumps(dict(stage='merge', **report)), flush=True)
        if save:
            save(model, report)
    return model, history


def remove_gain6(model, objective, *, weight=8., max_peak=.95, spectral_ceiling=.6):
    """Exhaustively replace rare 3/4 gains with either adjacent power of two."""
    indices = [i for i, (_, h, _) in enumerate(model['frames']) if (h >> 4) & 7 == 6]
    if len(indices) > 12:
        raise ValueError('Exhaustive gain6 removal supports at most 12 affected frames')
    scorer = FixedSearch(model, objective, stoi_floor=0., spectral_ceiling=spectral_ceiling,
                         stoi_weight=weight, max_peak=max_peak, max_data_bytes=65535,
                         dc_choices=(model.get('dc_block_shift', 0),),
                         **decoder_constraints(model))
    best = None
    for gains in itertools.product((5, 7), repeat=len(indices)):
        candidate = deepcopy(model)
        for index, gain in zip(indices, gains):
            candidate['frames'][index][1] = (candidate['frames'][index][1] & 143) | gain << 4
        score = scorer.score(candidate)
        if scorer.feasible(score) and (best is None or scorer.energy(score) < best[0]):
            best = scorer.energy(score), candidate, score
    if best is None:
        raise RuntimeError('No gain6 replacement satisfies the configured peak and spectrum limits')
    return best[1], dict(affected_frames=len(indices), evaluated=1 << len(indices), **best[2])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True, type=Path)
    parser.add_argument('--reference', required=True, type=Path)
    parser.add_argument('--clip', choices=('chego', 'otvechaesh', 'vinni'), default='chego')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--words', type=int, help='dictionary size; overrides the compression-level default')
    parser.add_argument('--compression-level', type=int, choices=range(10), metavar='0..9',
                        help='0 favors quality; 9 favors size; tunes dictionary size and byte penalty')
    parser.add_argument('--target-flash-data-bytes', type=int,
                        help='automatically simplify parameters toward this data budget (excludes decoder code)')
    parser.add_argument('--proposals', type=int, default=30000)
    parser.add_argument('--seed', type=int, default=23108)
    parser.add_argument('--weight', type=float, default=8.)
    parser.add_argument('--objective', choices=('balanced', 'spectral'), default='balanced')
    parser.add_argument('--stoi-floor', type=float)
    parser.add_argument('--spectral-ceiling', type=float, default=.6)
    parser.add_argument('--max-peak', type=float, default=.95)
    parser.add_argument('--max-data-bytes', type=int)
    parser.add_argument('--max-flash-data-bytes', type=int, help='hard limit for actual Flash data after the EEPROM split')
    parser.add_argument('--no-gain6', action='store_true', help='automatically remove and forbid the 3/4 gain mode')
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    if args.words is None:
        args.words = 8 if args.compression_level is None else (16,14,12,10,8,6,4,3,2,1)[args.compression_level]
    if args.target_flash_data_bytes is not None and args.target_flash_data_bytes < 1:
        parser.error('Target Flash data budget must be positive')
    if args.max_data_bytes is None and (args.compression_level is not None or args.target_flash_data_bytes is not None):
        # The portable container includes unused tables and is not the target
        # Flash layout. Actual Flash size drives this rate-control mode.
        args.max_data_bytes = 65535
    if not 1 <= args.words <= 16 or args.proposals < 0:
        parser.error('Expected 1..16 words and a nonnegative proposal count')
    clips = json.loads((ROOT/'ATtiny13A/Sound/audio-references.json').read_text(encoding='utf-8'))['clips']
    clip = next(value for value in clips if value['id'] == args.clip)
    if digest(args.reference.read_bytes()) != clip['sha256']:
        raise ValueError('Reference SHA-256 does not match canonical '+args.clip)
    reference, sr = sf.read(args.reference)
    objective = SpectralObjective(reference, sr)
    initial = json.loads(args.model.read_text(encoding='utf-8'))
    inputs = dict(reference_sha256=clip['sha256'], initial_model_sha256=digest(args.model.read_bytes()),
                  words=args.words, no_gain6=args.no_gain6)
    if args.compression_level is not None or args.target_flash_data_bytes is not None:
        inputs.update(compression_level=args.compression_level,
                      target_flash_data_bytes=args.target_flash_data_bytes)
    args.output.mkdir(parents=True, exist_ok=True)
    if args.resume:
        saved = json.loads((args.output/'checkpoint.json').read_text(encoding='utf-8'))
        if saved['inputs'] != inputs:
            raise ValueError('Checkpoint input hashes differ')
        model = json.loads((args.output/'merged-model.json').read_text(encoding='utf-8'))
        merges = saved['merges']
        gain_removal = saved.get('gain_removal')
    else:
        def save_merge(model, report):
            atomic_json(args.output/f"merged-{report['words']}-model.json", model)
            atomic_json(args.output/f"merged-{report['words']}-quality.json", report)
        model, merges = merge_words(initial, objective, args.words, weight=args.weight,
                                   max_peak=args.max_peak, spectral_ceiling=args.spectral_ceiling,
                                   save=save_merge)
        gain_removal = None
        if args.no_gain6:
            model, gain_removal = remove_gain6(model, objective, weight=args.weight,
                                              max_peak=args.max_peak, spectral_ceiling=args.spectral_ceiling)
            print(json.dumps(dict(stage='remove-gain6', **gain_removal)), flush=True)
        atomic_json(args.output/'merged-model.json', model)
        saved = None
    constraints = decoder_constraints(model)
    if args.no_gain6:
        constraints['allow_gain6'] = False
    search = TinySearch(model, objective, words=args.words, seed=args.seed, stoi_weight=args.weight,
                        objective_kind=args.objective,
                        stoi_floor=args.stoi_floor, spectral_ceiling=args.spectral_ceiling,
                        max_peak=args.max_peak, max_data_bytes=args.max_data_bytes,
                        max_flash_data_bytes=args.max_flash_data_bytes,
                        compression_level=args.compression_level,
                        target_flash_data_bytes=args.target_flash_data_bytes,
                        dc_choices=(model.get('dc_block_shift', 0),), **constraints,
                        checkpoint=saved['search'] if saved else None)
    runtime = {name:importlib.metadata.version(name) for name in ('numpy', 'scipy', 'pystoi', 'soundfile', 'numba')}
    runtime['python'] = sys.version.split()[0]
    sources = [Path(__file__), ROOT/'tools/refine_period_helpers.py']
    sources += [CODEC/name for name in ('fixed_search.py', 'fixed_period.py', 'dc_blocker.py', 'tiny_period.py',
                                       'compact_period.py', 'colored_period.py', 'period_wave.py', 'auto_encoder.py')]
    fingerprints = {str(path.relative_to(ROOT)).replace('\\', '/'):
                    digest(path.read_text(encoding='utf-8').encode()) for path in sources}

    def save(status):
        elite = search.export()
        payload = pack_fixed(elite)
        score = search.score(elite)
        report = dict(schema='tiny-speech-training-v1', clip_id=args.clip, inputs=inputs,
                      runtime=runtime, words=args.words, features=avr_features(elite),
                      config=search.config, merged_initial=search.initial, final=score,
                      proposals=search.proposals, evaluated=search.evaluated, accepted=search.accepted,
                      improvements=search.improvements, history=search.history, merges=merges,
                      gain_removal=gain_removal, source_sha256_normalized_lf=fingerprints,
                      avr_data_bytes=len(pack_avr_data(elite, specialize=True)),
                      portable_data_bytes=len(payload), payload_sha256=digest(payload),
                      avr_assembled=False, hardware_verified=False, status=status)
        if args.target_flash_data_bytes is not None:
            report['target_flash_data_bytes'] = args.target_flash_data_bytes
            report['target_size_met'] = score['tiny_flash_data_bytes'] <= args.target_flash_data_bytes
        atomic_json(args.output/'retuned-model.json', elite)
        atomic_json(args.output/'quality.json', report)
        atomic_json(args.output/'checkpoint.json', dict(inputs=inputs, merges=merges,
                                                       gain_removal=gain_removal, search=search.checkpoint()))
        (args.output/'expected.raw').write_bytes(decode_fixed(elite).tobytes())
        print(json.dumps(dict(stage=status, proposals=search.proposals, improvements=search.improvements,
                              avr_data_bytes=report['avr_data_bytes'], **score)), flush=True)

    try:
        while search.proposals < args.proposals:
            search.step()
            if search.proposals % 2000 == 0:
                save('searching')
    except KeyboardInterrupt:
        save('interrupted')
        return
    save('complete')
    audio = lambda value:(decode_fixed(value).astype(np.float64)-128)/128
    matched_audio(args.output, dict(Original=reference, Before=audio(initial), Tiny=audio(search.export())), objective,
                  ('Original', 'Before', 'Original', 'Tiny'))
    if (args.target_flash_data_bytes is not None and
            search.score(search.export())['tiny_flash_data_bytes'] > args.target_flash_data_bytes):
        parser.exit(2, 'Target Flash data budget was not reached; retained model and report are research candidates.\n')


if __name__ == '__main__':
    main()

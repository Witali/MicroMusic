#!/usr/bin/env python3
"""Refine a complete period/noise teacher before any tiny-target projection.

This experiment preserves every learned wave and noise filter. Payload counts
exclude decoder code. A teacher is a PC sound reference, never a 1 KB fit.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import soundfile as sf
from scipy.signal import stft, sosfilt
from pystoi import stoi

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0, str(CODEC))
from auto_encoder import SpectralObjective
from colored_period import ColoredSynthesis, decode_colored, pack_colored, unpack_colored
from joint_period import JointSearch
from period_book_search import BookSearch
from refine_period_helpers import atomic_json, matched_audio
from spectrogram_objective import SpectrogramObjective


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def diagnostics(reference, audio, objective):
    """Time-resolved band mismatch after a single global RMS match.

    No per-band/per-frame normalization can hide excessive narrow harmonics or
    missing consonants. Power floors are fixed relative to reference power.
    """
    ref = sosfilt(objective.hp, reference)
    out = sosfilt(objective.hp, audio)
    out *= np.sqrt(np.mean(ref*ref))/(np.sqrt(np.mean(out*out))+1e-20)
    f, _, target = stft(ref, fs=7500, nperseg=256, noverlap=192)
    measured = stft(out, fs=7500, nperseg=256, noverlap=192)[2]
    target, measured = abs(target)**2, abs(measured)**2
    active = target.sum(axis=0) > target.sum(axis=0).max()*.001
    bands = []
    for low, high in ((70,300),(300,600),(600,1200),(1200,2000),(2000,3000),(3000,3751)):
        mask = (f >= low) & (f < high)
        r, x = target[mask].sum(axis=0), measured[mask].sum(axis=0)
        floor = max(float(r.max())*1e-4, 1e-12)
        error_db = 10*np.log10((x+floor)/(r+floor))
        bands.append(dict(low_hz=low, high_hz=min(high,3750),
                          mean_error_db=float(error_db[active].mean()),
                          mean_absolute_error_db=float(abs(error_db[active]).mean()),
                          energy_ratio_db=float(10*np.log10((x.sum()+1e-20)/(r.sum()+1e-20)))))
    # Spectral flatness is an objective description, not a naturalness score.
    mask = (f >= 300) & (f <= 3500)
    floor = max(float(target.max())*1e-7,1e-12)
    def flat(power):
        power = power[mask][:,active]+floor
        return float(np.mean(np.exp(np.mean(np.log(power),axis=0))/np.mean(power,axis=0)))
    return dict(**objective.spectrum(audio), stoi=float(stoi(reference,audio,7500)),
                estoi=float(stoi(reference,audio,7500,extended=True)),
                bands=bands, reference_flatness=flat(target), output_flatness=flat(measured))


class TeacherObjective(SpectralObjective):
    def __init__(self, reference, sr, objective_kind):
        super().__init__(reference,sr)
        self.detail = SpectrogramObjective(reference,sr)
        self.objective_kind = objective_kind

    def spectrum(self, candidate):
        if self.objective_kind == 'legacy':
            return super().spectrum(candidate)
        result = self.detail.evaluate(candidate)
        # JointSearch's generic ceiling field measures the fine-ridge error in
        # this experiment. Both complete objective definitions are recorded.
        return dict(loss=result['spectrogram_loss'],
                    log_spectral_error=result['fine_log_error'],
                    relative_spectral_error=result['envelope_error'])


def run(reference_path, model_path, baseline_path, output, proposals=2000, weight=2., seed=23170,
        objective_kind='legacy'):
    reference, sr = sf.read(reference_path,dtype='float64')
    baseline, baseline_sr = sf.read(baseline_path,dtype='float64')
    model = json.loads(model_path.read_text(encoding='utf-8'))
    if sr != 7500 or baseline_sr != sr or baseline.shape != reference.shape:
        raise ValueError('Reference and baseline must be equal mono 7500 Hz streams')
    if model['base']['samples'] != len(reference):
        raise ValueError('Teacher duration differs from complete input')
    objective = TeacherObjective(reference,sr,objective_kind)
    plain_objective = SpectralObjective(reference,sr)
    output.mkdir(parents=True,exist_ok=True)
    initial = decode_colored(model)
    report = dict(schema='spectral-period-teacher-v1', samples=len(reference),
                  sample_rate=sr, reference_sha256=digest(reference_path),
                  input_model_sha256=digest(model_path), baseline_sha256=digest(baseline_path),
                  proposals=proposals, weight=weight, seed=seed,
                  objective_kind=objective_kind,
                  avr_assembled=False, hardware_verified=False, fits_tiny=False,
                  data_excludes_decoder=True,
                  baseline=diagnostics(reference,baseline,plain_objective),
                  initial=diagnostics(reference,initial,plain_objective), stages=[])
    counts = (proposals//2, proposals-proposals//2)
    for stage, cls, count in zip(('frames','waves'),(JointSearch,BookSearch),counts):
        kwargs = dict(cache_factory=ColoredSynthesis) if stage == 'frames' else {}
        search = cls(model, objective, seed=seed, stoi_weight=weight, **kwargs)
        for _ in range(count):
            search.step()
        model = search.export()
        report['stages'].append(dict(stage=stage,proposals=count,initial=search.initial,
                                     final=search.score(decode_colored(model)),
                                     improvements=search.improvements,config=search.config))
        print(json.dumps(report['stages'][-1]),flush=True)
    packed = pack_colored(model)
    audio = decode_colored(unpack_colored(packed))
    if not np.array_equal(audio,decode_colored(model)):
        raise AssertionError('Independent packed teacher changed output')
    report.update(final=diagnostics(reference,audio,plain_objective), data_bytes=len(packed),
                  spectrogram_baseline=objective.detail.evaluate(baseline),
                  spectrogram_initial=objective.detail.evaluate(initial),
                  spectrogram_final=objective.detail.evaluate(audio),
                  payload_sha256=hashlib.sha256(packed).hexdigest(),
                  source_sha256_normalized_lf={path.relative_to(ROOT).as_posix():
                      hashlib.sha256(path.read_text(encoding='utf-8').encode()).hexdigest()
                      for path in (Path(__file__), CODEC/'spectrogram_objective.py',
                                   CODEC/'period_book_search.py',CODEC/'colored_period.py',
                                   CODEC/'joint_period.py',CODEC/'period_wave.py')})
    atomic_json(output/'model.json',model)
    atomic_json(output/'quality.json',report)
    (output/'speech.pc').write_bytes(packed)
    sf.write(output/'decoded.wav',audio,sr,subtype='FLOAT')
    matched_audio(output,dict(Original=reference,Baseline=baseline,Teacher=audio),objective,
                  ('Original','Baseline','Teacher'))
    print(json.dumps(dict(final=report['final'],data_bytes=len(packed))),flush=True)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--model',type=Path,required=True)
    p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--proposals',type=int,default=2000)
    p.add_argument('--weight',type=float,default=2.)
    p.add_argument('--seed',type=int,default=23170)
    p.add_argument('--objective',choices=('legacy','spectrogram'),default='legacy')
    a = p.parse_args()
    if a.proposals < 0 or a.weight <= 0:
        p.error('Proposal count must be nonnegative and weight positive')
    run(a.reference,a.model,a.baseline,a.output,a.proposals,a.weight,a.seed,a.objective)


if __name__ == '__main__':
    main()

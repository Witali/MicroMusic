#!/usr/bin/env python3
"""Reproduce a full period/colored-noise voice experiment for an arbitrary WAV.

This PC experiment retains the complete learned period/noise model. Data bytes
exclude executable decoder code; no ATtiny13 fit or naturalness score is claimed.
"""
import argparse
import hashlib
import importlib.metadata
from pathlib import Path
import sys

import numpy as np
import soundfile as sf
from pystoi import stoi

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0,str(CODEC))
from auto_encoder import SpectralObjective
from period_wave import encode_model, decode_model
from period_residual import fit_residual
from colored_period import (learn_colored_model, decode_colored, pack_colored,
                            unpack_colored, ColoredSynthesis)
from joint_period import JointSearch
from period_book_search import BookSearch
from refine_period_helpers import atomic_json, matched_audio


def digest(data):
    return hashlib.sha256(data).hexdigest()


def run(reference_path, output, *, starts=8, residual_proposals=500,
        frame_proposals=2000, book_proposals=2000, baseline_path=None):
    reference,sr = sf.read(reference_path, dtype='float64')
    if sr != 7500 or reference.ndim != 1 or len(reference)%64 or len(reference)>65535:
        raise ValueError('Expected a mono 7500 Hz WAV with complete 64-sample blocks and <=65535 samples')
    objective = SpectralObjective(reference,sr)
    output.mkdir(parents=True,exist_ok=True)
    base,analysis = encode_model(reference,starts=starts)
    residual,residual_report = fit_residual(base,objective,proposals=residual_proposals)
    model = learn_colored_model(residual,reference)
    initial = decode_colored(model)
    report = dict(schema='new-period-voice-experiment-v1', samples=len(reference), sample_rate=sr,
                  reference_sha256=digest(reference_path.read_bytes()), reference_file=reference_path.name,
                  starts=starts, base_seed=23065, filter_seed=23069, search_seed=23123,
                  entire_input_preserved=True, avr_assembled=False, hardware_verified=False,
                  data_excludes_decoder=True, fits_tiny=False, residual=residual_report,
                  initial=dict(**objective.spectrum(initial),stoi=float(stoi(reference,initial,sr))))
    atomic_json(output/'initial-model.json',model)
    for stage,cls,count,kwargs in (
        ('frame',JointSearch,frame_proposals,dict(cache_factory=ColoredSynthesis)),
        ('book',BookSearch,book_proposals,{})):
        search = cls(model,objective,stoi_weight=8.,seed=23123,**kwargs)
        for _ in range(count):
            search.step()
        model = search.export()
        score = search.score(decode_colored(model))
        report[stage] = dict(initial=search.initial,final=score,proposals=search.proposals,
                             evaluated=search.evaluated,accepted=search.accepted,
                             improvements=search.improvements,config=search.config)
        atomic_json(output/(stage+'-model.json'),model)
        atomic_json(output/(stage+'-checkpoint.json'),search.checkpoint())
        print(dict(stage=stage,**score),flush=True)
    payload = pack_colored(model)
    audio = decode_colored(unpack_colored(payload))
    if not np.array_equal(audio,decode_colored(model)):
        raise AssertionError('Packed colored model changed decoded audio')
    (output/'speech.pc').write_bytes(payload)
    report.update(data_bytes=len(payload),payload_sha256=digest(payload),
                  pcm_f64le_sha256=digest(audio.astype('<f8').tobytes()),
                  final=dict(**objective.spectrum(audio),stoi=float(stoi(reference,audio,sr)),
                             estoi=float(stoi(reference,audio,sr,extended=True))),
                  pitch=dict(voiced_frames=int(np.sum(analysis['f0']>0)),frames=len(analysis['f0'])))
    clips = dict(Original=reference,Initial=initial,Colored=audio)
    order = ['Original','Initial','Original','Colored']
    if baseline_path:
        baseline,baseline_sr = sf.read(baseline_path,dtype='float64')
        if baseline_sr != sr or baseline.shape != reference.shape:
            raise ValueError('Baseline WAV duration/channel/sample-rate mismatch')
        clips['Baseline'] = baseline
        order = ['Original','Baseline','Original','Colored']
        report['baseline'] = dict(sha256=digest(baseline_path.read_bytes()),
                                  **objective.spectrum(baseline),stoi=float(stoi(reference,baseline,sr)),
                                  estoi=float(stoi(reference,baseline,sr,extended=True)))
    matched_audio(output,clips,objective,order)
    sf.write(output/'decoded.wav',audio,sr,subtype='FLOAT')
    sources = [Path(__file__),ROOT/'tools/refine_period_helpers.py']
    sources += [CODEC/name for name in ('period_wave.py','period_residual.py','colored_period.py',
                                       'joint_period.py','period_book_search.py','auto_encoder.py')]
    report['source_sha256_normalized_lf'] = {str(path.relative_to(ROOT)).replace('\\','/'):
        digest(path.read_text(encoding='utf-8').encode()) for path in sources}
    report['runtime'] = {name:importlib.metadata.version(name) for name in ('numpy','scipy','pystoi','soundfile')}
    report['runtime']['python'] = sys.version.split()[0]
    atomic_json(output/'quality.json',report)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--baseline',type=Path)
    p.add_argument('--starts',type=int,default=8)
    p.add_argument('--residual-proposals',type=int,default=500)
    p.add_argument('--frame-proposals',type=int,default=2000)
    p.add_argument('--book-proposals',type=int,default=2000)
    a = p.parse_args()
    if a.starts<1 or min(a.residual_proposals,a.frame_proposals,a.book_proposals)<0:
        p.error('Starts must be positive and proposal counts nonnegative')
    report = run(a.reference.resolve(),a.output.resolve(),starts=a.starts,
                 residual_proposals=a.residual_proposals,frame_proposals=a.frame_proposals,
                 book_proposals=a.book_proposals,baseline_path=a.baseline.resolve() if a.baseline else None)
    print(dict(data_bytes=report['data_bytes'],final=report['final']),flush=True)


if __name__=='__main__':
    main()

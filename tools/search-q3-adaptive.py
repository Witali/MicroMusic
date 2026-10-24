"""Joint excitation/filter exploration with a strict final quality selection.

Intermediate states may trade quality within explicit bounds. Only endpoints
meeting every original matching guard can replace the retained starting model.
"""
import argparse
from copy import deepcopy
import importlib.util
import math
from pathlib import Path
import random
import sys
import time
import numpy as np
import soundfile as sf

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('adaptive_joint_refiner',ROOT/'tools/refine-q3-adaptive.py')
fit=importlib.util.module_from_spec(spec);sys.modules[spec.name]=fit;spec.loader.exec_module(fit)
probe=fit.probe


def guarded(score,baseline):
    if any(score[k]<baseline[k] for k in ('stoi','estoi')):return False
    if score['spectrogram_loss']>baseline['spectrogram_loss'] or abs(score['raw_mean'])>abs(baseline['raw_mean']):return False
    if score['partial_violation_power']>baseline['partial_violation_power']:return False
    return all(score['harmonic_metrics'][k]<=baseline['harmonic_metrics'][k]
        for k in ('frequency_error_cents','frequency_trajectory_error','level_error_db',
            'harmonic_track_loss','missing_reference_energy'))


def mutate(state,rng,width):
    draw=rng.random()
    if draw<.12:
        f=state.frames.copy();index=rng.randrange(1,len(f));half=rng.choice((2,4))
        f[index,half:half+2]=f[index-1,half:half+2]
        return probe.search.State(f,state.durations.copy(),state.book.copy(),False,1)
    if draw<.28:
        f,b=state.frames.copy(),state.book.copy()
        used=np.flatnonzero((f[:,0]>0)&((f[:,1]&15)>0))
        if len(used):
            index=int(rng.choice(used));mode=int(f[index,1])>>4
            col=rng.randrange(width);other=rng.randrange(width);delta=rng.choice((-1,1))
            if col!=other and -7<=int(b[mode,col])+delta<=7 and -7<=int(b[mode,other])-delta<=7:
                b[mode,col]+=delta;b[mode,other]-=delta
            if rng.random()<.5:
                active=(f[:,1]>>4)==mode;gains=(f[active,1]&15).astype(int)+rng.choice((-1,1))
                f[active,1]=(mode<<4)|np.clip(gains,0,15).astype(np.uint8)
        return probe.search.State(f,state.durations.copy(),b,False,1)
    candidate=probe.mutate(state,rng,width)
    if draw>.7:candidate=probe.mutate(candidate,rng,width)
    return candidate


def run(reference_path,model_path,output,*,proposals=5000,width=8,seed=24112):
    if proposals<1 or width not in (4,8,16):raise ValueError('Expected positive finite budget and valid pulse width')
    started=time.perf_counter();reference,sr=sf.read(reference_path,dtype='float64')
    if sr!=7500 or reference.ndim!=1:raise ValueError('Expected complete mono7500 reference')
    f,d,b,_=probe.builder.load_model(model_path)
    objective=fit.Objective(reference);initial=probe.search.State(f,d,b,False,1)
    initial.score=objective.evaluate(initial)
    if initial.score is None:raise ValueError('Starting model fails arithmetic/memory guards')
    baseline=initial.score;best=current=exploratory=initial;archive=[initial];rng=random.Random(seed)
    loose=deepcopy(baseline)
    loose['stoi']-=.008;loose['estoi']-=.015;loose['spectrogram_loss']+=.008
    loose['raw_mean']=abs(loose['raw_mean'])+.01;loose['partial_violation_power']+=.04
    for k,allowance in [('frequency_error_cents',10.),('frequency_trajectory_error',.2),
            ('level_error_db',1.),('harmonic_track_loss',.15),('missing_reference_energy',.04)]:
        loose['harmonic_metrics'][k]+=allowance
    objective.limits=loose
    seen={fit.key(initial)};valid=accepted=strict=0;history=[]
    for index in range(proposals):
        if index%1000==0:current=rng.choice(archive)
        anchor=(best if rng.random()<.2 else min(archive,key=lambda s:objective.energy(s.score))
            if rng.random()<.35 else current)
        trial=mutate(anchor,rng,width)
        layout=fit.select(trial.frames,trial.durations,trial.book)
        trial.frames,trial.book=layout['frames'],layout['book']
        identity=fit.key(trial)
        if identity in seen:continue
        seen.add(identity);trial.score=objective.evaluate(trial)
        if trial.score is not None:
            valid+=1
            if objective.energy(trial.score)<objective.energy(exploratory.score):exploratory=trial
            if guarded(trial.score,baseline):
                strict+=1
                if objective.energy(trial.score)<objective.energy(best.score)-1e-12:
                    best=trial;history.append(dict(proposal=index+1,score=best.score))
            archive.append(trial);archive.sort(key=lambda s:objective.energy(s.score));archive=archive[:16]
            temperature=.003*.03**((index%1000)/999)
            delta=objective.energy(trial.score)-objective.energy(current.score)
            if delta<=0 or rng.random()<math.exp(-min(700,delta/temperature)):
                current=trial;accepted+=1
        if (index+1)%500==0:
            record=dict(proposals=index+1,valid=valid,accepted=accepted,strict_candidates=strict,
                selected_stoi=best.score['stoi'],selected_spectrum=best.score['spectrogram_loss'],
                exploratory_stoi=exploratory.score['stoi'],exploratory_spectrum=exploratory.score['spectrogram_loss'],
                elapsed_seconds=time.perf_counter()-started)
            probe.save(output/'progress.json',record);print(probe.json.dumps(record),flush=True)
    results={}
    for name,state in [('before',initial),('after',best),('exploratory_best',exploratory)]:
        objective.floor_budget=state.score['maximum_stream_bytes']
        results[name]=probe.export(output/name,state,objective,width,probe.sha(reference_path))
    report=dict(schema='q3-adaptive-joint-v1',proposals=proposals,width=width,seed=seed,valid=valid,
        accepted=accepted,strict_candidates=strict,finalists=results,history=history,
        soft_intermediate_limits=loose,quality_rejections=dict(objective.rejected),arithmetic_rejections=objective.invalid,
        elapsed_seconds=time.perf_counter()-started,input_model_sha256=probe.sha(model_path),reference_sha256=probe.sha(reference_path),
        policy='Intermediate matching tradeoffs are allowed only inside recorded limits; after is baseline or a full-clip endpoint satisfying every original STOI/eSTOI/spectrum/DC/harmonic/5dB-power guard; no block splicing',
        source_sha256_normalized_lf={p.relative_to(ROOT).as_posix():probe.hashlib.sha256(p.read_text(encoding='utf-8').encode()).hexdigest()
            for p in (Path(__file__),ROOT/'tools/refine-q3-adaptive.py',ROOT/'ATtiny13A/Sound/codec/q3_adaptive.py')})
    probe.save(output/'report.json',report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('reference','model','output'):p.add_argument('--'+name,required=True,type=Path)
    p.add_argument('--proposals',type=int,default=5000);p.add_argument('--width',type=int,choices=(4,8,16),default=8)
    p.add_argument('--seed',type=int,default=24112)
    a=p.parse_args();run(a.reference,a.model,a.output,proposals=a.proposals,width=a.width,seed=a.seed)

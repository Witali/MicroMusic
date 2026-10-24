"""Test a shared spectral tail while keeping two precise controls per frame.

This is an exact integer PC experiment, without an AVR decoder or Flash-fit
claim. The retained three-section data format is packed and read back exactly.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import numpy as np
import soundfile as sf

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
import q4_voice_patterns as codec
spec=importlib.util.spec_from_file_location('full_voice_patterns',ROOT/'tools/probe-q4-voice-patterns.py')
study=importlib.util.module_from_spec(spec);spec.loader.exec_module(study)


def distance_table(target,tails,modes,active):
    wanted=study.features(target);distance=np.empty((len(target),len(tails)))
    for row,head in enumerate(target[:,:2]):
        candidates=np.column_stack((np.tile(head,(len(tails),1)),tails))
        distance[row]=np.mean((study.features(candidates)-wanted[row])**2,axis=1)
        distance[row]+=4.*active[row]*(modes!=modes[row])
    return distance


def medoids(distance,weights,count):
    chosen=[int(np.argmax(weights))]
    while len(chosen)<count:
        cost=distance[:,chosen].min(axis=1)*weights;cost[chosen]=-1
        chosen.append(int(np.argmax(cost)))
    for _ in range(15):
        labels=np.argmin(distance[:,chosen],axis=1);new=[]
        for n,old in enumerate(chosen):
            members=np.flatnonzero(labels==n)
            if not len(members):new.append(old);continue
            cost=(distance[np.ix_(members,members)]*weights[members,None]).sum(axis=0)
            new.append(int(members[np.argmin(cost)]))
        if new==chosen:break
        chosen=new
    return np.asarray(chosen),np.argmin(distance[:,chosen],axis=1).astype(np.uint8)


def run(reference_path,control_path,output,trials=1500):
    if trials<0:raise ValueError('Evaluation budget must be nonnegative')
    start=time.perf_counter();model=json.loads(control_path.read_text(encoding='utf-8'))
    if model['schema']!='q4-per-frame-control-v1':raise ValueError('Expected tagged Q4 PC control')
    reference,sr=sf.read(reference_path,dtype='float64')
    if sr!=7500 or reference.ndim!=1:raise ValueError('Expected unchanged mono7500 original')
    reference_hash=hashlib.sha256(reference_path.read_bytes()).hexdigest()
    if reference_hash!=model['reference_sha256']:raise ValueError('Original hash mismatch')
    p=np.asarray(model['pitches'],np.uint8);g=np.asarray(model['gains'],np.uint8)
    d=np.asarray(model['durations'],np.uint16);h=np.asarray(model['fractions'],np.uint8)
    k=np.asarray(model['coefficients'],np.int8);m=np.asarray(model['modes'],np.uint8)
    waves=np.asarray(model['pulsebook'],np.int8);heads=k[:,:2].copy()
    if int(d.sum())!=len(reference):raise ValueError('Expected complete original duration')
    tails=np.clip(np.rint(k[:,2:]/2)*2,-14,14).astype(np.int8)
    distance=distance_table(k,tails,m,((p>0)&(g>0)).astype(float))
    bounds=np.r_[0,np.cumsum(d)]
    weights=np.asarray([np.sum(reference[a:b]**2) for a,b in zip(bounds[:-1],bounds[1:])])
    weights=np.maximum(weights,weights.max()*.001)
    chosen,labels=medoids(distance,weights,16);tails=tails[chosen].copy();modes=m[chosen].copy()
    objective=study.Objective(reference,(p,g,d,h),waves);ids=np.arange(len(p),dtype=np.uint16)
    def expand(hh,tt,ll):return np.column_stack((hh,tt[ll])),modes[ll]
    def evaluate(hh,tt,ll):
        full,mm=expand(hh,tt,ll);return objective.evaluate(full,mm,ids)
    initial=evaluate(heads,tails,labels);gain_seed=1.
    if initial is None:
        original_gain=g.copy()
        for scale in (.875,.75,.5):
            g[:]=np.rint(original_gain*scale).astype(np.uint8)
            initial=evaluate(heads,tails,labels)
            if initial is not None:gain_seed=scale;break
    current=initial;accepted=dict(labels=0,heads=0,tails=0,gains=0)
    if current is not None:
        # Try every pattern: envelope distance initializes, exact PCM selects.
        for row in range(len(p)):
            for label in range(16):
                if label==labels[row]:continue
                candidate=labels.copy();candidate[row]=label
                score=evaluate(heads,tails,candidate)
                if score is not None and objective.energy(score)<objective.energy(current):
                    labels,current=candidate,score;accepted['labels']+=1
        for row in range(len(p)):
            for column in range(2):
                for delta in (-1,1):
                    value=int(heads[row,column])+delta
                    if not -15<=value<=15:continue
                    candidate=heads.copy();candidate[row,column]=value
                    score=evaluate(candidate,tails,labels)
                    if score is not None and objective.energy(score)<objective.energy(current):
                        heads,current=candidate,score;accepted['heads']+=1
        for index in range(trials):
            row=(index//12)%16;column=(index//2)%6;delta=-2 if index%2==0 else 2
            value=int(tails[row,column])+delta
            if not -14<=value<=14:continue
            candidate=tails.copy();candidate[row,column]=value
            score=evaluate(heads,candidate,labels)
            if score is not None and objective.energy(score)<objective.energy(current):
                tails,current=candidate,score;accepted['tails']+=1
        for row in range(len(p)):
            for delta in (-1,1):
                value=int(g[row])+delta
                if not 0<=value<=15:continue
                old=int(g[row]);g[row]=value;score=evaluate(heads,tails,labels)
                if score is not None and objective.energy(score)<objective.energy(current):
                    current=score;accepted['gains']+=1
                else:g[row]=old
    table,plane,stream=codec.pack_selective(p,g,labels,d,h,heads,tails,modes,waves)
    decoded=codec.unpack_selective(table,plane,stream)
    for before,after in zip((p,g,labels,d,h,heads,tails,modes),decoded):np.testing.assert_array_equal(before,after)
    full,mm=expand(heads,tails,labels);final=objective.detail(full,mm,ids)
    study.save(output/'model.json',dict(schema='q4-selective-patterns-v1',sample_rate=7500,
        pitches=p.tolist(),gains=g.tolist(),indices=labels.tolist(),durations=d.tolist(),fractions=h.tolist(),
        heads=heads.tolist(),tails=tails.tolist(),modes=modes.tolist(),pulsebook=waves.tolist(),
        reference_sha256=reference_hash,avr_verified=False,hardware_tested=False))
    pcm,counts=codec.render(p,g,ids,d,h,full,mm,waves);signed=pcm.astype(np.int16)-128
    report=dict(schema='q4-selective-pattern-study-v1',initial=initial,final=final,
        table_bytes=len(table),precision_bytes=len(plane),stream_bytes=len(stream),
        data_bytes=len(table)+len(plane)+len(stream),accepted=accepted,gain_seed_scale=gain_seed,
        raw_guard_diagnostics=dict(wrap_counts=counts.tolist(),peak=int(abs(signed).max()),
            maximum_step=int(abs(np.diff(signed)).max())),
        reference_sha256=reference_hash,control_sha256=hashlib.sha256(control_path.read_bytes()).hexdigest(),
        trials=trials,exact_evaluations=objective.evaluated,elapsed_seconds=time.perf_counter()-start,
        source_sha256_normalized_lf={x.relative_to(ROOT).as_posix():hashlib.sha256(x.read_text(encoding='utf-8').encode()).hexdigest()
            for x in (Path(__file__),ROOT/'tools/probe-q4-voice-patterns.py',ROOT/'ATtiny13A/Sound/codec/q4_voice_patterns.py')},
        avr_verified=False,policy='Exact packed PC study; excludes decoder, EOF and waveform storage; no Flash-fit claim')
    study.save(output/'report.json',report);print(json.dumps(report));return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('reference','control','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--trials',type=int,default=1500)
    a=parser.parse_args();run(a.reference,a.control,a.output,a.trials)

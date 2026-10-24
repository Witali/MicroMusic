"""Measure spectral dictionaries and Q4 precision against a complete original.

This is a PC format study. Table/stream sizes are exact; complete AVR code,
timing and Flash fit require the separate assembler qualification step.
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
from hq4_speech_search import deterministic_estoi
from spectrogram_objective import SpectrogramObjective
from harmonic_tracks import HarmonicTrackObjective
from pystoi import stoi


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')


def features(patterns):
    response=codec.envelope_features(np.asarray(patterns,np.int16))
    mag=abs(np.fft.rfft(response,axis=1))[:,5:240]
    value=np.log(np.maximum(mag,1e-5))
    return value-value.mean(axis=1,keepdims=True)


def cluster(patterns,modes,weights,count,active):
    """Weighted spectral medoids, with active waveform mismatch penalty."""
    z=features(patterns);distance=np.mean((z[:,None,:]-z[None,:,:])**2,axis=2)
    distance+=4.*active[:,None]*(modes[:,None]!=modes[None,:])
    chosen=[int(np.argmax(weights))]
    while len(chosen)<count:
        cost=distance[:,chosen].min(axis=1)*weights
        cost[chosen]=-1
        chosen.append(int(np.argmax(cost)))
    for _ in range(15):
        assignment=np.argmin(distance[:,chosen],axis=1);new=[]
        for label,old in enumerate(chosen):
            members=np.flatnonzero(assignment==label)
            if not len(members):new.append(old);continue
            cost=(distance[np.ix_(members,members)]*weights[members,None]).sum(axis=0)
            new.append(int(members[np.argmin(cost)]))
        if new==chosen:break
        chosen=new
    assignment=np.argmin(distance[:,chosen],axis=1).astype(np.uint8)
    return patterns[chosen].copy(),modes[chosen].copy(),assignment


def reorder(patterns,modes,indices,pitches,durations,halves):
    cheap=(pitches<=63)&(durations!=192)&(halves==0)
    order=sorted(range(len(patterns)),key=lambda i:(-int(np.sum(cheap&(indices==i))),-int(np.sum(indices==i)),i))
    mapping=np.empty(len(order),np.uint8);mapping[order]=np.arange(len(order),dtype=np.uint8)
    return patterns[order],modes[order],mapping[indices]


class Objective:
    def __init__(self,reference,controls,waves):
        self.reference=reference;self.controls=controls;self.waves=waves
        self.spectral=SpectrogramObjective(reference);self.evaluated=0

    def evaluate(self,patterns,modes,indices):
        self.evaluated+=1
        p,g,d,h=self.controls
        pcm,counts=codec.render(p,g,indices,d,h,patterns,modes,self.waves)
        signed=pcm.astype(np.int16)-128
        if np.any(counts) or abs(signed).max()>115 or np.any(abs(np.diff(signed))>=48):return None
        audio=signed.astype(float)/128
        return dict(stoi=float(stoi(self.reference,audio,7500)),**self.spectral.evaluate(audio),
            peak_signed=int(abs(signed).max()),raw_mean=float(audio.mean()),wrap_counts=counts.tolist())

    def energy(self,score):return score['spectrogram_loss']+6*max(0.,.9-score['stoi'])

    def detail(self,patterns,modes,indices):
        score=self.evaluate(patterns,modes,indices)
        if score is None:return dict(guards_pass=False)
        p,g,d,h=self.controls;pcm,_=codec.render(p,g,indices,d,h,patterns,modes,self.waves)
        audio=(pcm.astype(float)-128)/128
        score.update(guards_pass=True,estoi=deterministic_estoi(self.reference,audio,7500),
            harmonic_metrics=HarmonicTrackObjective(self.reference).evaluate(audio),
            pcm_sha256=hashlib.sha256(pcm.tobytes()).hexdigest(),avr_verified=False,hardware_tested=False)
        return score


def run(reference_path,model_path,output,counts=(16,32),polish=1600,ceiling=0):
    if not counts or any(not 1<=n<=32 for n in counts) or len(set(counts))!=len(counts):
        raise ValueError('Expected distinct pattern counts in 1..32')
    if polish<0 or ceiling<0:raise ValueError('Evaluation budgets must be nonnegative')
    started=time.perf_counter();reference,sr=sf.read(reference_path,dtype='float64')
    if sr!=7500 or reference.ndim!=1:raise ValueError('Expected unchanged mono7500 original')
    model=json.loads(model_path.read_text(encoding='utf-8'))
    if model['schema']!='q3-half-pitch-probe-v1':raise ValueError('Expected explicitly tagged half-pitch reference')
    f=np.asarray(model['frames'],np.uint8);d=np.asarray(model['durations'],np.uint16)
    halves=np.asarray(model['fractions'],np.uint8);waves=np.asarray(model['pulsebook'],np.int8)
    p,g,modes=f[:,0].copy(),f[:,1]&15,f[:,1]>>4
    phase_spec=importlib.util.spec_from_file_location('pattern_half_reference',ROOT/'tools/build-q3-half-pitch-probe.py')
    phase=importlib.util.module_from_spec(phase_spec);phase_spec.loader.exec_module(phase)
    phase.pack(f,d,waves,halves)
    if int(d.sum())!=len(reference):raise ValueError('Frame durations must cover the complete original')
    patterns=np.empty((len(f),8),np.int8)
    patterns[:,::2]=((f[:,2:]&15).astype(np.int16)-8)*2
    patterns[:,1::2]=((f[:,2:]>>4).astype(np.int16)-8)*2
    indices=np.arange(len(f),dtype=np.uint16)
    objective=Objective(reference,(p,g,d,halves),waves)
    output.mkdir(parents=True,exist_ok=True);old=phase.oracle(output)
    before,bc=old(f,d,waves,halves);now,nc=codec.render(p,g,indices,d,halves,patterns,modes,waves)
    np.testing.assert_array_equal(before,now);np.testing.assert_array_equal(bc,nc)
    baseline=objective.detail(patterns,modes,indices)
    ideal=patterns.copy();ideal_score=baseline;accepted=0
    for index in range(min(ceiling,len(ideal)*16)):
        row=index//16;column=(index//2)%8;delta=-1 if index%2==0 else 1
        trial=ideal.copy();target=int(trial[row,column])+delta
        if not -15<=target<=15:continue
        trial[row,column]=target;score=objective.evaluate(trial,modes,indices)
        if score is not None and objective.energy(score)<objective.energy(ideal_score):
            ideal,ideal_score=trial,score;accepted+=1
    ideal_detail=objective.detail(ideal,modes,indices)
    save(output/'per-frame-control.json',dict(schema='q4-per-frame-control-v1',sample_rate=7500,
        pitches=p.tolist(),gains=g.tolist(),durations=d.tolist(),fractions=halves.tolist(),
        coefficients=ideal.tolist(),modes=modes.tolist(),pulsebook=waves.tolist(),
        reference_sha256=hashlib.sha256(reference_path.read_bytes()).hexdigest(),
        avr_verified=False,serialized_format=False))
    bounds=np.r_[0,np.cumsum(d)];weights=np.array([np.sum(reference[a:b]**2) for a,b in zip(bounds[:-1],bounds[1:])])
    weights=np.maximum(weights,weights.max()*.001)
    active=((p>0)&(g>0)).astype(float)
    result={}
    for count in counts:
        patterns,pmodes,labels=cluster(ideal,modes,weights,count,active)
        initial=objective.detail(patterns,pmodes,labels);current=objective.evaluate(patterns,pmodes,labels)
        accepted=0
        if current is not None:
            for index in range(polish):
                row=(index//16)%len(patterns);column=(index//2)%8;delta=-1 if index%2==0 else 1
                target=int(patterns[row,column])+delta
                if not -15<=target<=15:continue
                trial=patterns.copy();trial[row,column]=target;score=objective.evaluate(trial,pmodes,labels)
                if score is not None and objective.energy(score)<objective.energy(current):
                    patterns,current=trial,score;accepted+=1
        patterns,pmodes,labels=reorder(patterns,pmodes,labels,p,d,halves)
        codec.validate(p,g,labels,d,halves,patterns,pmodes,waves)
        table=codec.pack_patterns(patterns,pmodes);payload=codec.pack_stream(p,g,labels,d,halves)
        final=objective.detail(patterns,pmodes,labels)
        value=dict(schema=codec.SCHEMA,sample_rate=7500,pitches=p.tolist(),gains=g.tolist(),indices=labels.tolist(),
            durations=d.tolist(),fractions=halves.tolist(),patterns=patterns.tolist(),modes=pmodes.tolist(),pulsebook=waves.tolist(),
            reference_sha256=hashlib.sha256(reference_path.read_bytes()).hexdigest())
        save(output/str(count)/'model.json',value)
        summary=dict(initial=initial,final=final,patterns=count,pattern_bytes=len(table),stream_bytes=len(payload),
            data_bytes=len(table)+len(payload),accepted=accepted,avr_verified=False)
        save(output/str(count)/'report.json',summary);result[str(count)]=summary
        print(json.dumps(dict(patterns=count,pattern_bytes=len(table),stream_bytes=len(payload),quality=final)),flush=True)
    report=dict(schema='q4-voice-pattern-study-v1',baseline=baseline,q4_per_frame_control=ideal_detail,
        budgets=dict(per_frame_coordinate_trials=ceiling,dictionary_coordinate_trials=polish,pattern_counts=list(counts)),
        results=result,elapsed_seconds=time.perf_counter()-started,exact_evaluations=objective.evaluated,
        reference_sha256=hashlib.sha256(reference_path.read_bytes()).hexdigest(),model_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),
        source_sha256_normalized_lf={x.relative_to(ROOT).as_posix():hashlib.sha256(x.read_text(encoding='utf-8').encode()).hexdigest()
            for x in (Path(__file__),ROOT/'ATtiny13A/Sound/codec/q4_voice_patterns.py')},
        policy='Complete original, exact integer output guards and existing STOI/spectrum objective; dictionary features only initialize; table/stream sizes exclude unimplemented AVR decoder')
    save(output/'report.json',report);return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('reference','model','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--patterns',type=int,nargs='+',default=[16,32]);parser.add_argument('--polish',type=int,default=1600)
    parser.add_argument('--ceiling',type=int,default=0)
    a=parser.parse_args();run(a.reference,a.model,a.output,a.patterns,a.polish,a.ceiling)

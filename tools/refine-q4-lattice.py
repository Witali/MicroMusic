"""Joint exact-output fit of coefficient, excitation and gain precision.

This PC teacher keeps the old pulse timing and permits finer Q4 reflections,
half-unit wave taps and half-unit gains. It deliberately does not claim that
the resulting data plus a word-state AVR decoder fit 1024 bytes.
"""
import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np
import soundfile as sf

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
import q4_phase_wave as codec
from spectrogram_objective import SpectrogramObjective
from harmonic_tracks import HarmonicTrackObjective
from hq4_speech_search import deterministic_estoi
from pystoi import stoi

SCHEMA='q4-lattice-fit-v1'


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')


@dataclass
class State:
    pitches:np.ndarray
    gains_q1:np.ndarray
    durations:np.ndarray
    coefficients:np.ndarray
    modes:np.ndarray
    waves_q1:np.ndarray
    halves:np.ndarray

    def copy(self):return State(*(x.copy() for x in self.__dict__.values()))
    def fields(self):return {k:v.tolist() for k,v in self.__dict__.items()}


def load(path):
    model=json.loads(path.read_text(encoding='utf-8'))
    if model['schema']==SCHEMA:
        return State(*(np.asarray(model[name],np.int16) for name in State.__annotations__))
    if model['schema']=='q4-per-frame-control-v1':
        return State(np.asarray(model['pitches'],np.int16),np.asarray(model['gains'],np.int16)*2,
            np.asarray(model['durations'],np.int16),np.asarray(model['coefficients'],np.int16),
            np.asarray(model['modes'],np.int16),np.asarray(model['pulsebook'],np.int16)*2,
            np.asarray(model['fractions'],np.int16))
    raise ValueError('Expected explicitly tagged Q4 per-frame control or joint-fit model')


def validate(s):
    n=len(s.pitches)
    if (not n or s.pitches.shape!=(n,) or any(x.shape!=(n,) for x in
            (s.gains_q1,s.durations,s.modes,s.halves)) or s.coefficients.shape!=(n,8)
            or s.waves_q1.shape!=(8,16) or np.any(s.pitches<0) or np.any(s.pitches>126)
            or np.any(s.gains_q1<0) or np.any(s.gains_q1>30) or np.any(s.coefficients < -15)
            or np.any(s.coefficients>15) or np.any(s.modes<0) or np.any(s.modes>7)
            or np.any(s.waves_q1 < -7) or np.any(s.waves_q1>7)
            or not np.all(np.isin(s.halves,[0,1])) or np.any((s.pitches==0)&(s.halves!=0))
            or not np.all(np.isin(s.durations,[64,128,192,256]))):raise ValueError('Invalid joint-fit fields')


def render(s,bits,nearest):
    rows,excitation=codec.legacy_excitation(s.pitches,s.gains_q1,s.durations,s.modes,s.waves_q1,s.halves)
    excitation[s.pitches[rows]==0]*=2 # noise has a Q1 gain but no Q1 waveform tap
    return codec.filter_signal(excitation,rows,s.coefficients,state_bits=bits,nearest=nearest,fraction_bits=2)


def energy(score):return score['spectrogram_loss']+6*max(0.,.93-score['stoi'])


def actions(s):
    for row in range(len(s.pitches)):
        for column in range(8):
            for delta in (-1,1):yield ('coefficient',row,column,delta)
        for delta in (-1,1):yield ('gain',row,0,delta)
        if s.pitches[row]:
            for delta in (-2,-1,1,2):yield ('pitch',row,0,delta)
        for mode in np.unique(s.modes[(s.pitches>0)&(s.gains_q1>0)]):
            if mode!=s.modes[row]:yield ('mode',row,0,int(mode))
    for mode in np.unique(s.modes[(s.pitches>0)&(s.gains_q1>0)]):
        for tap in range(16):
            for delta in (-1,1):yield ('wave',int(mode),tap,delta)
    for row in range(len(s.pitches)-1):
        for delta in (-64,64):yield ('boundary',row,0,delta)
    unused=[i for i in range(8) if i not in s.modes[(s.pitches>0)&(s.gains_q1>0)]]
    if unused:
        for row in np.flatnonzero((s.pitches>0)&(s.gains_q1>0)):
            for tap in range(4):
                for delta in (-1,1):yield ('split',int(row),tap,delta)


def apply(s,action):
    kind,row,column,value=action;c=s.copy()
    if kind=='coefficient':
        target=int(c.coefficients[row,column])+value
        if not -15<=target<=15:return None
        c.coefficients[row,column]=target
    elif kind=='gain':
        target=int(c.gains_q1[row])+value
        if not 0<=target<=30:return None
        c.gains_q1[row]=target
    elif kind=='pitch':
        target=int(c.pitches[row])*2+int(c.halves[row])+value
        if not 2<=target<=252:return None
        c.pitches[row]=target//2;c.halves[row]=target%2
    elif kind=='mode':c.modes[row]=value
    elif kind=='wave':
        target=int(c.waves_q1[row,column])+value
        if not -7<=target<=7:return None
        c.waves_q1[row,column]=target
    elif kind=='boundary':
        first=int(c.durations[row])+value;second=int(c.durations[row+1])-value
        if first not in (64,128,192,256) or second not in (64,128,192,256):return None
        c.durations[row]=first;c.durations[row+1]=second
    elif kind=='split':
        unused=[i for i in range(8) if i not in c.modes[(c.pitches>0)&(c.gains_q1>0)]]
        if not unused:return None
        target=int(c.waves_q1[c.modes[row],column])+value
        if not -7<=target<=7:return None
        new=unused[0];c.waves_q1[new]=c.waves_q1[c.modes[row]]
        c.waves_q1[new,column]=target;c.modes[row]=new
    else:raise ValueError('Unknown joint-fit action')
    return c


def run(reference_path,model_path,output,evaluations=12000,bits=4,nearest=False):
    if evaluations<0 or bits not in (0,1,2,3,4,6,8):raise ValueError('Invalid budget or state precision')
    started=time.perf_counter();s=load(model_path);validate(s)
    reference,sr=sf.read(reference_path,dtype='float64')
    if sr!=7500 or reference.ndim!=1 or len(reference)!=int(s.durations.sum()):raise ValueError('Expected complete mono7500 original')
    spectral=SpectrogramObjective(reference);evaluated=0;accepted=[];history=[]
    def score(candidate,detail=False):
        pcm,counts=render(candidate,bits,nearest);raw=pcm.astype(np.int16)-128
        if np.any(counts) or abs(raw).max()>115 or np.any(abs(np.diff(raw))>=48):return None
        y=raw.astype(float)/128
        q=dict(stoi=float(stoi(reference,y,7500)),**spectral.evaluate(y),raw_mean=float(y.mean()),
            peak=int(abs(raw).max()),maximum_step=int(abs(np.diff(raw)).max()),wrap_counts=counts.tolist(),
            pcm_sha256=hashlib.sha256(pcm.tobytes()).hexdigest())
        if detail:q.update(estoi=deterministic_estoi(reference,y,7500),harmonic_metrics=HarmonicTrackObjective(reference).evaluate(y))
        return q
    initial=score(s,True)
    if initial is None:raise ValueError('Initial model fails integer guards')
    current=initial;best_stoi=(initial['stoi'],s.copy(),initial)
    def export(state):
        return dict(schema=SCHEMA,sample_rate=7500,state_bits=bits,nearest=nearest,
            **state.fields(),reference_sha256=hashlib.sha256(reference_path.read_bytes()).hexdigest(),
            avr_implemented=False,serialized_format=False,hardware_tested=False)
    output.mkdir(parents=True,exist_ok=True);save(output/'initial-model.json',export(s))
    print(json.dumps(dict(evaluated=0,score=initial)),flush=True)
    epoch=0
    while evaluated<evaluations:
        epoch_accepted=0
        candidates=list(actions(s))
        if epoch%2:candidates.reverse()
        for action in candidates:
            if evaluated>=evaluations:break
            trial=apply(s,action)
            if trial is None:continue
            evaluated+=1;q=score(trial)
            if q is not None and energy(q)<energy(current)-1e-12:
                s,current=trial,q;epoch_accepted+=1;accepted.append(dict(evaluation=evaluated,action=list(action),score=q))
                if q['stoi']>best_stoi[0] and q['spectrogram_loss']<=.4848481735668308 and abs(q['raw_mean'])<=.07764022651760058:
                    best_stoi=(q['stoi'],s.copy(),q)
            if evaluated%250==0:
                progress=dict(evaluated=evaluated,accepted=len(accepted),score=current,best_stoi=best_stoi[0],elapsed_seconds=time.perf_counter()-started)
                save(output/'progress.json',progress);save(output/'checkpoint.json',export(s))
                print(json.dumps(progress),flush=True)
        history.append(dict(epoch=epoch,accepted=epoch_accepted,evaluated=evaluated));epoch+=1
        if not epoch_accepted:break
    final=score(s,True);best_detail=score(best_stoi[1],True)
    save(output/'model.json',export(s));save(output/'best-intelligibility-model.json',export(best_stoi[1]))
    pcm,_=render(s,bits,nearest);sf.write(output/'decoded.wav',(pcm.astype(float)-128)/128,7500,subtype='PCM_16')
    report=dict(schema='q4-lattice-fit-study-v1',initial=initial,final=final,best_intelligibility=best_detail,
        evaluated=evaluated,accepted=len(accepted),history=accepted,epochs=history,state_bits=bits,nearest=nearest,
        reference_sha256=hashlib.sha256(reference_path.read_bytes()).hexdigest(),
        seed_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),elapsed_seconds=time.perf_counter()-started,
        source_sha256_normalized_lf={x.relative_to(ROOT).as_posix():hashlib.sha256(x.read_text(encoding='utf-8').encode()).hexdigest()
            for x in (Path(__file__),ROOT/'ATtiny13A/Sound/codec/q4_phase_wave.py')},
        avr_implemented=False,serialized_format=False,hardware_tested=False,
        policy='PC teacher only; exact pulse/half-pitch timing; no signal alignment or trimming; no total Flash-fit claim')
    save(output/'report.json',report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('reference','model','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--evaluations',type=int,default=12000);p.add_argument('--state-bits',type=int,default=4)
    p.add_argument('--nearest',action='store_true')
    a=p.parse_args();run(a.reference,a.model,a.output,a.evaluations,a.state_bits,a.nearest)

"""Fit complete periodic voice shapes before imposing a tiny data budget.

All reported scores are from complete integer output. Training uses a floating
inverse lattice only to propose shapes; it cannot establish output quality.
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
import q4_phase_wave as codec
from hq4_speech_search import deterministic_estoi
from spectrogram_objective import SpectrogramObjective
from harmonic_tracks import HarmonicTrackObjective
from pystoi import stoi


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')


def source_coefficients(reference,durations,order=8):
    """Windowed autocorrelation LPC initialization, independently of old fit."""
    emphasized=reference.copy();emphasized[1:]-=.5*reference[:-1]
    edges=np.r_[0,np.cumsum(durations)];rows=[]
    for begin,end in zip(edges[:-1],edges[1:]):
        center=int((begin+end)//2);positions=np.arange(center-200,center+200)
        block=emphasized[np.clip(positions,0,len(reference)-1)]*np.hanning(400)
        r=np.asarray([np.dot(block[:len(block)-lag],block[lag:]) for lag in range(order+1)])
        r[0]*=1.0001;error=max(r[0],1e-12);a=np.ones(1);ks=[]
        for stage in range(1,order+1):
            coefficient=-(r[stage]+np.dot(a[1:],r[stage-1:0:-1]))/error
            coefficient=float(np.clip(coefficient,-.9375,.9375));ks.append(coefficient)
            a=np.r_[a,0.]+coefficient*np.r_[0.,a[::-1]];error=max(error*(1.-coefficient**2),1e-12)
        rows.append(np.clip(np.rint(np.asarray(ks)*16),-15,15))
    return np.asarray(rows,np.int8)


def evaluate(reference,spectral,values,detail=False,state_bits=0,nearest=False):
    pcm,counts=codec.render(*values,state_bits=state_bits,nearest=nearest)
    raw=pcm.astype(np.int16)-128;audio=raw.astype(float)/128
    result=dict(stoi=float(stoi(reference,audio,7500)),**spectral.evaluate(audio),
        raw_mean=float(audio.mean()),peak=int(abs(raw).max()),maximum_step=int(abs(np.diff(raw)).max()),
        wrap_counts=counts.tolist(),guards_pass=bool(not np.any(counts) and abs(raw).max()<=115
            and not np.any(abs(np.diff(raw))>=48)),pcm_sha256=hashlib.sha256(pcm.tobytes()).hexdigest())
    if detail:result.update(estoi=deterministic_estoi(reference,audio,7500),
        harmonic_metrics=HarmonicTrackObjective(reference).evaluate(audio))
    return result


def energy(score):return score['spectrogram_loss']+6*max(0.,.93-score['stoi'])


def phase_seed(reference,durations):
    from period_wave import track_pitch,continuous_phase,align_phase
    centers,f0,quality=track_pitch(reference)
    target=align_phase(reference,continuous_phase(f0,centers,len(reference)),f0,centers)
    edges=np.r_[0,np.cumsum(durations).astype(int)-1]
    steps=np.zeros(len(durations),np.uint16);offsets=np.zeros(len(durations),np.uint16)
    for row,(left,right) in enumerate(zip(edges[:-1],edges[1:])):
        offsets[row]=int(round(target[left]*65536))%65536
        center=(left+right)*.5;voice=int(np.argmin(abs(centers-center)))
        if f0[voice]>0:
            step=(target[right]-target[left])*65536/max(1,right-left)
            steps[row]=max(1,min(32767,int(round(step))))
    return steps,offsets


def run(reference_path,model_path,output,epochs=5,counts=(2,4),scales=(.5,1.),state_bits=(0,4),source_phase=False):
    if epochs<1 or any(n not in (1,2,4,8) for n in counts) or any(x<=0 for x in scales) or any(x not in (0,4,8) for x in state_bits):
        raise ValueError('Positive epochs/scales and 1/2/4/8 forms required')
    start=time.perf_counter();reference,sr=sf.read(reference_path,dtype='float64')
    if sr!=7500 or reference.ndim!=1:raise ValueError('Expected unchanged mono7500 original')
    model=json.loads(model_path.read_text(encoding='utf-8'))
    if model['schema']!='q3-half-pitch-probe-v1':raise ValueError('Expected half-pitch seed')
    f=np.asarray(model['frames'],np.uint8);durations=np.asarray(model['durations'],np.uint16)
    half=np.asarray(model['fractions'],np.uint8)
    if int(durations.sum())!=len(reference):raise ValueError('Expected complete original duration')
    spec=importlib.util.spec_from_file_location('phase_wave_half_seed',ROOT/'tools/build-q3-half-pitch-probe.py')
    phase=importlib.util.module_from_spec(spec);spec.loader.exec_module(phase)
    phase.pack(f,durations,np.asarray(model['pulsebook'],np.int8),half)
    steps=np.zeros(len(f),np.uint16);voiced=f[:,0]>0
    steps[voiced]=np.rint(65536/(f[voiced,0].astype(float)+half[voiced]*.5)).astype(np.uint16)
    initial_offsets=np.zeros(len(f),np.uint16)
    if source_phase:steps,initial_offsets=phase_seed(reference,durations)
    old_k=np.empty((len(f),8),np.int8)
    old_k[:,::2]=((f[:,2:]&15).astype(np.int16)-8)*2
    old_k[:,1::2]=((f[:,2:]>>4).astype(np.int16)-8)*2
    spectral=SpectrogramObjective(reference);records=[];best=None
    output.mkdir(parents=True,exist_ok=True)
    for initialization,coefficients in (('previous',old_k),('source-lpc',source_coefficients(reference,durations))):
        for count in counts:
            for policy in ('reset','continuous','aligned'):
                for scale in scales:
                    for bits in state_bits:
                        for nearest in (False,True):
                            gains=(f[:,1]&15).copy();modes=((f[:,1]>>4)%count).copy()
                            offsets=initial_offsets.copy();resets=np.full(len(f),int(policy!='continuous'),np.uint8)
                            history=[];local=None
                            for epoch in range(epochs):
                                rows,phases=codec.trace(steps,durations,offsets,resets)
                                target=codec.inverse(reference,coefficients,rows,128.*scale)
                                for row in np.flatnonzero((steps==0)&((f[:,1]&15)>0)):
                                    level=np.sqrt(np.mean(target[rows==row]**2))
                                    gains[row]=max(1,min(15,int(round(level))))
                                matrix,rhs=codec.normal_equations(target,rows,phases,steps,gains,modes,count)
                                raw=np.linalg.solve(matrix+np.eye(len(matrix))*.01,rhs).reshape(count,32)
                                raw-=raw.mean(axis=1,keepdims=True)
                                waves=np.clip(np.rint(raw),-7,7).astype(np.int8)
                                values=(steps,gains,durations,coefficients,modes,waves,offsets,resets)
                                codec.validate(*values);score=evaluate(reference,spectral,values,state_bits=bits,nearest=nearest)
                                history.append(dict(epoch=epoch,**score))
                                if score['guards_pass'] and (local is None or energy(score)<local[0]):
                                    local=(energy(score),score,tuple(x.copy() for x in values))
                                gains,modes,offsets=codec.assign(target,rows,phases,steps,gains,modes,waves,offsets,policy=='aligned')
                            record=dict(initialization=initialization,forms=count,phase_policy=policy,state_bits=bits,nearest=nearest,
                                target_scale=scale,history=history,best=local[1] if local else None)
                            records.append(record)
                            print(json.dumps({k:v for k,v in record.items() if k!='history'}),flush=True)
                            if local is not None and (best is None or local[0]<best[0]):best=(*local,record)
    report=dict(schema='q4-phase-wave-probe-v1',sample_rate=7500,samples=len(reference),epochs=epochs,source_phase=source_phase,
        reference_sha256=hashlib.sha256(reference_path.read_bytes()).hexdigest(),
        seed_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),candidates=records,
        avr_implemented=False,serialized_format=False,hardware_tested=False,
        source_sha256_normalized_lf={x.relative_to(ROOT).as_posix():hashlib.sha256(x.read_text(encoding='utf-8').encode()).hexdigest()
            for x in (Path(__file__),ROOT/'ATtiny13A/Sound/codec/q4_phase_wave.py',ROOT/'ATtiny13A/Sound/codec/q4_voice_patterns.py',ROOT/'ATtiny13A/Sound/codec/period_wave.py')})
    if best:
        _,score,values,record=best
        score=evaluate(reference,spectral,values,True,state_bits=record['state_bits'],nearest=record['nearest']);report['best']=score
        names=('steps','gains','durations','coefficients','modes','waves','offsets','resets')
        saved=dict(schema=codec.SCHEMA,sample_rate=7500,state_bits=record['state_bits'],nearest=record['nearest'],reference_sha256=report['reference_sha256'],
            **{key:value.tolist() for key,value in zip(names,values)})
        save(output/'model.json',saved)
        report['best_config']={key:record[key] for key in ('initialization','forms','phase_policy','target_scale','state_bits','nearest')}
        pcm,_=codec.render(*values,state_bits=record['state_bits'],nearest=record['nearest'])
        sf.write(output/'decoded.wav',(pcm.astype(float)-128)/128,7500,subtype='PCM_16')
    report['elapsed_seconds']=time.perf_counter()-start;save(output/'report.json',report);return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('reference','model','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--epochs',type=int,default=5);parser.add_argument('--forms',type=int,nargs='+',default=[2,4])
    parser.add_argument('--scales',type=float,nargs='+',default=[.5,1.])
    parser.add_argument('--state-bits',type=int,nargs='+',default=[0,4])
    parser.add_argument('--source-phase',action='store_true')
    a=parser.parse_args();run(a.reference,a.model,a.output,a.epochs,a.forms,a.scales,a.state_bits,a.source_phase)

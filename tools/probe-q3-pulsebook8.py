"""Bounded joint fitting of eight excitation forms and the full speech stream."""
import argparse
from copy import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import random
import sys
import time
import numpy as np
import soundfile as sf
from scipy.signal import sosfilt

ROOT=Path(__file__).resolve().parents[1];CODEC=ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0,str(CODEC))
import q3_pulsebook8 as codec
from hq4_speech_search import deterministic_estoi
from harmonic_tracks import HarmonicTrackObjective
from partial_bounds import check_partial_bounds


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);sys.modules[name]=result;spec.loader.exec_module(result)
    return result


builder=module('pulsebook8_fitting_builder',ROOT/'tools/build-q3-pulsebook8.py')
search=module('private_pulsebook8_objective',ROOT/'tools/probe-q3-pulsebook.py')
search.render,search.validate,search.pack_stream=codec.render,codec.validate,codec.pack_stream


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')


def mutate(state,rng,width):
    f,d,b=state.frames.copy(),state.durations.copy(),state.book.copy()
    kind=rng.randrange(100)
    active=np.flatnonzero((f[:,0]>0)&((f[:,1]&15)>0)).tolist()
    if kind<45 and active:
        index=rng.choice(active);old=int(f[index,1])>>4
        row=rng.randrange(8)
        if row>=4 and not np.any((f[:,1]>>4)==row):b[row]=b[old]
        for _ in range(rng.randint(1,3)):
            col=rng.randrange(width)
            b[row,col]=max(-7,min(7,int(b[row,col])+rng.choice((-2,-1,1,2))))
        f[index,1]=(int(f[index,1])&15)|(row<<4)
        if rng.random()<.3:
            f[index,1]=(row<<4)|max(0,min(15,(int(f[index,1])&15)+rng.choice((-1,1))))
    elif kind<65 and active:
        index=rng.choice(active);row=rng.randrange(8)
        for at in range(index,min(len(f),index+rng.randint(1,3))):
            if f[at,0] and f[at,1]&15:f[at,1]=(int(f[at,1])&15)|(row<<4)
    elif kind<80:
        index=rng.randrange(len(f))
        if rng.random()<.55:
            gain=max(0,min(15,(int(f[index,1])&15)+rng.choice((-1,1))))
            f[index,1]=(int(f[index,1])&112)|gain
        else:
            target=int(f[index,0])+rng.choice((-2,-1,1,2))
            if 1<=target<=126:f[index,0]=target
    elif kind<94:
        index=rng.randrange(len(f));column=rng.randrange(2,6);shift=rng.choice((0,4))
        value=((int(f[index,column])>>shift)&15)+rng.choice((-1,1))
        if 1<=value<=15:
            first,last=index,index+1
            if rng.random()<.7:
                half=2 if column<4 else 4;original=f[index,half:half+2].copy()
                while first and np.array_equal(f[first-1,half:half+2],original):first-=1
                while last<len(f) and np.array_equal(f[last,half:half+2],original):last+=1
            f[first:last,column]=(f[first:last,column]&(255^(15<<shift)))|(value<<shift)
    elif kind<97 and len(f)>1:
        index=rng.randrange(len(f)-1);delta=rng.choice((-64,64))
        if 64<=int(d[index])+delta<=256 and 64<=int(d[index+1])-delta<=256:
            d[index],d[index+1]=int(d[index])+delta,int(d[index+1])-delta
    else:
        row,col=rng.randrange(8),rng.randrange(width)
        b[row,col]=max(-7,min(7,int(b[row,col])+rng.choice((-1,1))))
    return search.State(codec.canonicalize_selectors(f,b),d,b,False,1)


def extra_metrics(state,objective):
    pcm,_=codec.render(state.frames,state.durations,state.book)
    audio=(pcm.astype(float)-128)/128
    result=dict(state.score,estoi=deterministic_estoi(objective.reference,audio,7500))
    tracks=HarmonicTrackObjective(objective.reference);detail=tracks.details(audio)
    result['harmonic_metrics']=detail['metrics']
    result['matched_strict_5db_bounds']=check_partial_bounds(detail,duration_seconds=len(audio)/7500)
    raw=copy(tracks);raw.matched=lambda value:sosfilt(raw.hp,np.asarray(value,dtype=float))
    detail=raw.details(audio)
    result['raw_strict_5db_bounds']=check_partial_bounds(detail,duration_seconds=len(audio)/7500)
    return result


def export(path,state,objective,width,reference_sha):
    payload=codec.validate(state.frames,state.durations,state.book,len(objective.reference),objective.floor_budget)
    pcm,counts=codec.render(state.frames,state.durations,state.book)
    quality=extra_metrics(state,objective)
    modes=state.frames[:,1]>>4;active=(state.frames[:,0]>0)&((state.frames[:,1]&15)>0)
    quality.update(pcm_sha256=hashlib.sha256(pcm.tobytes()).hexdigest(),
        stream_sha256=hashlib.sha256(payload).hexdigest(),active_extra_forms=np.unique(modes[active&(modes>=4)]).tolist(),
        form_frame_counts={str(int(m)):int(np.count_nonzero(active&(modes==m))) for m in range(8)},
        avr_verified=False,hardware_tested=False)
    save(path/'model.json',dict(schema=codec.SCHEMA,sample_rate=7500,samples=len(pcm),tilt_shift=1,nearest=False,
        pulsebook=state.book.tolist(),frames=state.frames.tolist(),durations=state.durations.tolist(),
        width=width,reference_sha256=reference_sha,stream_budget=objective.floor_budget))
    save(path/'quality.json',quality)
    (path/'speech.hq8').write_bytes(payload);(path/'expected.raw').write_bytes(pcm.tobytes())
    sf.write(path/'decoded.wav',(pcm.astype(float)-128)/128,7500,subtype='FLOAT')
    return quality


def run(reference_path,model_path,core_path,output,*,proposals=6000,seed=24108):
    started=time.perf_counter();reference,sr=sf.read(reference_path,dtype='float64')
    if sr!=7500 or reference.ndim!=1:raise ValueError('Expected complete mono 7500-Hz original')
    evidence=json.loads(core_path.read_text());width=evidence['width'];budget=evidence['maximum_stream_bytes']
    if (evidence['status']!='verified' or evidence['forms']!=8 or evidence['gain_levels']!=16
            or not evidence['verification']['pass'] or evidence['firmware_sha256']!=sha(core_path.parent/'firmware.bin')
            or evidence['packing']!='nibble' or evidence['flash_bytes']>1024):
        raise ValueError('Search requires an actual verified eight-form nibble core')
    f,d,b,input_payload=builder.load_model(model_path)
    original_pcm,original_counts=codec.render(f,d,b)
    f=codec.canonicalize_selectors(f,b)
    recoded_pcm,recoded_counts=codec.render(f,d,b)
    np.testing.assert_array_equal(original_pcm,recoded_pcm)
    np.testing.assert_array_equal(original_counts,recoded_counts)
    codec.encode_book(b,width,'nibble')
    objective=search.Objective(reference,floor_budget=budget,rounded_budget=budget)
    baseline=search.State(f,d,b,False,1);baseline.score=objective.evaluate(baseline)
    if baseline.score is None:raise ValueError('Baseline fails full-duration guards')
    baseline_estoi=deterministic_estoi(reference,(codec.render(f,d,b)[0].astype(float)-128)/128,7500)
    current=baseline;archive=[baseline];rng=random.Random(seed);evaluated=accepted=0;history=[]
    for index in range(proposals):
        elite=min(archive,key=lambda s:objective.energy(s.score))
        if index%1500==0:current=rng.choice(archive)
        anchor=elite if rng.random()<.55 else rng.choice(archive) if rng.random()<.25 else current
        trial=mutate(anchor,rng,width);trial.score=objective.evaluate(trial)
        if trial.score is not None:
            evaluated+=1;archive=search.pareto_add(archive,trial)
            temperature=.004*.05**((index%1500)/1499)
            delta=objective.energy(trial.score)-objective.energy(current.score)
            if delta<=0 or rng.random()<math.exp(-min(700,delta/temperature)):
                current=trial;accepted+=1
        if (index+1)%500==0:
            elite=min(archive,key=lambda s:objective.energy(s.score))
            record=dict(proposals=index+1,evaluated=evaluated,accepted=accepted,score=elite.score,
                elapsed_seconds=time.perf_counter()-started)
            history.append(record);save(output/'progress.json',record);print(json.dumps(record),flush=True)
    candidates=[]
    for state in archive:
        if state.score['stoi']>=baseline.score['stoi'] and state.score['spectrogram_loss']<=baseline.score['spectrogram_loss']:
            pcm,_=codec.render(state.frames,state.durations,state.book)
            if deterministic_estoi(reference,(pcm.astype(float)-128)/128,7500)>=baseline_estoi:
                candidates.append(state)
    guarded=min(candidates,key=lambda s:objective.energy(s.score)) if candidates else baseline
    finalists=dict(baseline=baseline,balanced=min(archive,key=lambda s:objective.energy(s.score)),
        best_stoi=max(archive,key=lambda s:s.score['stoi']),best_spectrum=min(archive,key=lambda s:s.score['spectrogram_loss']),guarded=guarded)
    results={name:export(output/name,state,objective,width,sha(reference_path)) for name,state in finalists.items()}
    report=dict(schema='q3-pulsebook8-search-v1',width=width,proposals=proposals,seed=seed,evaluated=evaluated,
        accepted=accepted,reference_sha256=sha(reference_path),core_report_sha256=sha(core_path),stream_budget=budget,
        input_model_sha256=sha(model_path),input_stream_bytes=len(input_payload),
        canonical_input_stream_bytes=len(codec.pack_stream(f,d)),
        baseline_estoi=baseline_estoi,finalists=results,guard_rejections=objective.invalid,history=history,
        target_met=any(s.score['target_met'] for s in archive),elapsed_seconds=time.perf_counter()-started,
        policy='Exact whole-clip STOI/spectrum; no wraps, peak >115 or steps >=48; guarded export also preserves eSTOI',
        source_sha256_normalized_lf={str(path.relative_to(ROOT)):hashlib.sha256(path.read_text(encoding='utf-8').encode()).hexdigest()
            for path in (Path(__file__),ROOT/'tools/probe-q3-pulsebook.py',CODEC/'q3_pulsebook8.py',CODEC/'spectrogram_objective.py')})
    save(output/'report.json',report);return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('reference','model','core-report','output'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--proposals',type=int,default=6000);p.add_argument('--seed',type=int,default=24108)
    a=p.parse_args();run(a.reference,a.model,a.core_report,a.output,proposals=a.proposals,seed=a.seed)


if __name__=='__main__':main()

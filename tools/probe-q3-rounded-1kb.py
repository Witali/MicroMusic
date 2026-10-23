"""Fit the rounded Q3 decoder under a complete Flash/EEPROM budget.

The previous decoder is always retained unless a newly assembled candidate
passes its frozen intelligibility, spectral and tracked-component guards.
"""
import argparse
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
from hq4_core import pack_stream
from hq4_q3 import render as old_render
from hq4_q3_rounded import render
from hq4_speech_search import proposal


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    result=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--model',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--proposals',type=int,default=2000)
    p.add_argument('--seed',type=int,default=23273)
    p.add_argument('--resume-model',type=Path,help='Rounded research model; incumbent guards remain frozen')
    p.add_argument('--stream-budget',type=int,default=601)
    p.add_argument('--eeprom',action='store_true')
    p.add_argument('--build',action='store_true')
    p.add_argument('--avr-bin',type=Path)
    p.add_argument('--node',default='node')
    a=p.parse_args()
    limit=637 if a.eeprom else 601
    if a.proposals<0 or not 8<=a.stream_budget<=limit:
        p.error('Invalid bounded search or stream budget')
    reference,sr=sf.read(a.reference,dtype='float64')
    model=json.loads(a.model.read_text(encoding='utf-8'))
    if sr!=7500 or reference.ndim!=1 or model.get('schema')!='hq4-q3-v1' or model.get('tilt_shift')!=1:
        p.error('Expected full 7500Hz reference and a frozen Q3/T1 model')
    frames=np.asarray(model['frames'],np.uint8)
    durations=np.asarray(model['durations'],np.uint16)
    helper=module('rounded_tracks_objective','tools/probe-hq4-q3-tracks.py')
    helper.render=old_render
    old_objective=helper.Objective(reference,1,603,10)
    baseline=old_objective.evaluate(frames,durations)
    if baseline is None:
        p.error('Incumbent fails source/size/arithmetic checks')
    helper.render=render
    objective=helper.Objective(reference,1,a.stream_budget,10)
    rate=module('rounded_rate_helper','tools/probe-hq4-natural-timbre.py')
    initial=rate.fit_rate(frames,durations,a.stream_budget)
    seeds=[]
    if a.resume_model:
        resume=json.loads(a.resume_model.read_text(encoding='utf-8'))
        if resume.get('schema')!='hq4-q3-rounded-v1' or resume.get('tilt_shift')!=1:
            p.error('Resume requires the explicitly rounded Q3/T1 schema')
        rf,rd=np.asarray(resume['frames'],np.uint8),np.asarray(resume['durations'],np.uint16)
        resumed=objective.evaluate(rf,rd)
        if resumed is None:
            p.error('Resume fails physical arithmetic, duration or byte guards')
        seeds.append((rf,rd,resumed))
    for scale in (.75,.875,1.,1.125):
        f=initial.copy()
        f[:,1]=(f[:,1]&48)|np.minimum(15,np.rint((f[:,1]&15)*scale)).astype(np.uint8)
        score=objective.evaluate(f,durations)
        if score is not None:
            seeds.append((f,durations.copy(),score))
    if not seeds:
        raise ValueError('No physically valid rounded seed')
    energy=lambda score:helper.working_energy(score,baseline)
    best=min(seeds,key=lambda item:energy(item[2]))
    current=best
    eligible=[item for item in seeds if helper.feasible(item[2],baseline)]
    accepted=min(eligible,key=lambda item:item[2]['difference_loss']) if eligible else None
    history=[]
    rng=random.Random(a.seed)
    evaluated=0
    start=time.perf_counter()
    for step in range(a.proposals):
        anchor=best if rng.random()<.65 else current
        f,d=proposal(anchor[0],anchor[1],rng)
        if rng.random()<.12 and len(f)>1:
            i=rng.randrange(1,len(f));half=slice(2,4) if rng.randrange(2) else slice(4,6)
            f[i,half]=f[i-1,half]
        score=objective.evaluate(f,d)
        if score is not None:
            evaluated+=1
            candidate=(f.copy(),d.copy(),score.copy())
            if energy(score)<energy(best[2]):
                best=candidate
            if helper.feasible(score,baseline) and (accepted is None or score['difference_loss']<accepted[2]['difference_loss']):
                accepted=candidate
                history.append(dict(proposal=step+1,**score))
            delta=energy(score)-energy(current[2])
            temperature=.004*(.1**((step%1000)/999))
            if delta<0 or rng.random()<math.exp(max(-700.,min(0.,-delta/temperature))):
                current=candidate
        if (step+1)%500==0:
            print(json.dumps(dict(proposal=step+1,evaluated=evaluated,elapsed=time.perf_counter()-start,
                best=best[2],qualified=accepted[2] if accepted else None)),flush=True)
    selected=accepted if accepted is not None else best
    f,d,score=selected
    payload=pack_stream(f,d)
    pcm=render(f,d,1)[0]
    a.output.mkdir(parents=True,exist_ok=True)
    new_model=dict(schema='hq4-q3-rounded-v1',sample_rate=sr,samples=len(reference),tilt_shift=1,
        eeprom_prefix_bytes=64 if a.eeprom else 0,frames=f.tolist(),durations=d.tolist())
    report=dict(schema='q3-rounded-1kb-probe-v1',reference_sha256=sha(a.reference.read_bytes()),
        input_model_sha256=sha(a.model.read_bytes()),baseline=baseline,final=score,initial=[s[2] for s in seeds],
        proposals=a.proposals,seed=a.seed,evaluated=evaluated,stream_budget=a.stream_budget,
        stream_bytes=len(payload),stream_sha256=sha(payload),pcm_sha256=sha(pcm.tobytes()),
        candidate_accepted=accepted is not None,selected_profile='q3-rounded' if accepted else 'incumbent-q3',
        rejected_candidate_retained_for_research=accepted is None,history=history,avr_assembled=False,
        hardware_tested=False,human_listening_verified=False,elapsed_seconds=time.perf_counter()-start)
    if a.resume_model:
        report['resume_model_sha256']=sha(a.resume_model.read_bytes())
    paths=[Path(__file__),ROOT/'ATtiny13A/Sound/codec/hq4_q3_rounded.py',
        ROOT/'ATtiny13A/Sound/codec/hq4_q3.py',ROOT/'tools/probe-hq4-q3-tracks.py']
    report['sources_sha256_normalized_lf']={path.relative_to(ROOT).as_posix():sha(path.read_bytes().replace(b'\r\n',b'\n')) for path in paths}
    for name,value in (('model.json',new_model),('quality.json',report)):
        (a.output/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8',newline='\n')
    (a.output/'speech.hq').write_bytes(payload)
    (a.output/'expected.raw').write_bytes(pcm.tobytes())
    sf.write(a.output/'decoded.wav',(pcm.astype(float)-128)/128,sr,subtype='FLOAT')
    if a.build:
        if a.eeprom:
            builder=module('rounded_ee_builder','tools/build-q3-rounded-eeprom.py')
            built=builder.build(a.output/'speech.hq',a.output/'avr',a.avr_bin,a.node)
        else:
            builder=module('rounded_flash_builder','tools/build-hq4-oneshot.py')
            builder.TEMPLATE=ROOT/'ATtiny13A/Sound/codec/q3-rounded/hq4-t1.S'
            builder.decode=lambda f,d,keep_phase=0:render(f,d,1)[0]
            built=builder.build('q3-rounded',a.output/'avr',a.avr_bin,a.node,
                stream=a.output/'speech.hq',expected_samples=len(reference))
        if built['status']!='verified' or built['flashBytes']>1024:
            raise ValueError('Complete rounded image failed 1KB/PCM/cycle qualification')
        report.update(avr_assembled=True,build_report='avr/build.json')
    (a.output/'quality.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(dict(candidate_accepted=report['candidate_accepted'],stream_bytes=len(payload),final=score)),flush=True)


if __name__=='__main__':
    main()

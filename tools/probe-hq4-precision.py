"""Retune HQ4 for nearest Q4 product rounding; PC experiment until assembled."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import sys

import numpy as np
from pystoi import stoi
from scipy.signal import sosfilt
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
from auto_encoder import SpectralObjective
from hq4_core import unpack_stream, pack_stream
from hq4_precision import decode_precision
from hq4_speech_search import proposal, deterministic_estoi
from new_hq4_encoder import reuse_coefficients


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference', required=True, type=Path)
    p.add_argument('--stream', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--proposals', type=int, default=6000)
    p.add_argument('--seed', type=int, default=23143)
    a = p.parse_args()
    reference,sr = sf.read(a.reference)
    if sr != 7500 or reference.ndim != 1 or not np.all(np.isfinite(reference)):
        p.error('Reference must be finite mono audio at 7500 Hz')
    if a.proposals < 0:
        p.error('Proposal count must be nonnegative')
    objective=SpectralObjective(reference,sr)
    f,d=unpack_stream(a.stream.read_bytes())
    if int(d.sum()) != len(reference):
        p.error('Complete reference and stream durations must agree')
    rng=random.Random(a.seed)
    def evaluate(f,d):
        payload=pack_stream(f,d)
        if len(payload)>613 or int(d.sum())!=len(reference):
            return None
        pcm=decode_precision(f,d,True)
        audio=(pcm.astype(float)-128)/128
        peak=int(np.max(abs(pcm.astype(int)-128)))
        steps=int(np.sum(abs(np.diff(pcm.astype(int)))>=48))
        if peak>115:
            return None
        spec=objective.spectrum(audio)
        st=float(stoi(reference,audio,sr))
        return dict(**spec,stoi=st,peak=peak,steps=steps,mean_pcm=float((pcm.astype(int)-128).mean()),
                    stream_bytes=len(payload),energy=8*(1-st)+spec['loss']+.02*steps)
    initial=[]
    for threshold in (0,.25,.5,1,2,4,8):
        frame=reuse_coefficients(f,threshold)
        for gain in (.65,.8,1.):
            trial=frame.copy()
            trial[:,1]=(trial[:,1]&48)|np.minimum(15,np.rint((trial[:,1]&15)*gain).astype(np.uint8))
            score=evaluate(trial,d)
            if score is not None:
                initial.append((trial,d.copy(),score))
    if not initial:
        raise ValueError('No initial 613-byte rounded candidate')
    current=min(initial,key=lambda item:item[2]['energy'])
    best=min((item for item in initial if not item[2]['steps']),key=lambda item:item[2]['energy'],default=None)
    history=[]
    for i in range(a.proposals):
        anchor=best if best and rng.random()<.65 else current
        nf,nd=proposal(anchor[0],anchor[1],rng)
        score=evaluate(nf,nd)
        if score is None:
            continue
        if score['steps']==0 and (best is None or score['energy']<best[2]['energy']):
            best=(nf.copy(),nd.copy(),score.copy())
            history.append(dict(proposal=i+1,**score))
        temp=.025*(.1**((i%1500)/1499))
        delta=score['energy']-current[2]['energy']
        if delta<0 or rng.random()<np.exp(-min(700.,max(0.,delta/temp))):
            current=(nf,nd,score)
        if (i+1)%1500==0 and best:
            current=best
            print(json.dumps(dict(proposal=i+1,**best[2])),flush=True)
    if best is None:
        raise ValueError('No click-free rounded candidate found')
    f,d,score=best
    pcm=decode_precision(f,d,True)
    score['estoi']=deterministic_estoi(reference,(pcm.astype(float)-128)/128,sr)
    a.output.mkdir(parents=True,exist_ok=True)
    model=dict(schema='hq4-rounded-v1',sample_rate=sr,samples=len(reference),
               frames=f.tolist(),durations=d.tolist(),rounding='nearest, ties to positive infinity')
    sources=[Path(__file__),ROOT/'ATtiny13A/Sound/codec/hq4_precision.py',
             ROOT/'ATtiny13A/Sound/codec/new_hq4_encoder.py',ROOT/'ATtiny13A/Sound/codec/hq4_speech_search.py']
    sha=lambda data:hashlib.sha256(data).hexdigest()
    report=dict(reference_sha256=sha(a.reference.read_bytes()),input_stream_sha256=sha(a.stream.read_bytes()),
                seed=a.seed,proposals=a.proposals,avr_assembled=False,final=score,
                sources_sha256_normalized_lf={path.relative_to(ROOT).as_posix():sha(path.read_text(encoding='utf-8').encode()) for path in sources},
                history=history)
    for name,value in [('model.json',model),('quality.json',report)]:
        (a.output/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8',newline='\n')
    (a.output/'speech.hq').write_bytes(pack_stream(f,d))
    (a.output/'expected.raw').write_bytes(pcm.tobytes())
    old=decode_precision(*unpack_stream(a.stream.read_bytes()),False)
    signals=[reference,(old.astype(float)-128)/128,(pcm.astype(float)-128)/128]
    signals=[sosfilt(objective.hp,x) for x in signals]
    signals=[x*objective.rms/(np.sqrt(np.mean(x*x))+1e-10) for x in signals]
    scale=.85/max(float(np.max(abs(x))) for x in signals)
    for name,x in zip(('original','before','after'),signals):
        sf.write(a.output/(name+'.wav'),x*scale,sr,subtype='PCM_16')
    sf.write(a.output/'comparison.wav',np.concatenate([part for j in (0,1,0,2) for part in (signals[j]*scale,np.zeros(2250))]),sr,subtype='PCM_16')
    print(json.dumps(score),flush=True)


if __name__=='__main__':
    main()

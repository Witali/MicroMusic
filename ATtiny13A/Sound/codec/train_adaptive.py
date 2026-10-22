#!/usr/bin/env python3
"""Train adaptive LPC-8 frame slew against original recordings and LPX3 teacher.
Select spectral keys (under an EXACT Flash cap), independently optimize per-frame
fast/slow interpolation and quantized LPC coefficients by analysis-by-synthesis.
Tight stop criteria protect source intelligibility while minimizing clicks.
"""
from pathlib import Path
import argparse, json, time
import numpy as np
import soundfile as sf
from model_adaptive import render
from package_adaptive import pack
from perceptual import Evaluator,load_wav
ROOT=Path(__file__).resolve().parent
DECODER_SIZE=842
FLASH_LIMIT=1024
PROFILE=(4,8)

def score(m):
    return 3*m['stoi']-0.42*m['mel_original']-0.23*m['mel_lpc2']-0.0010*m['clicks_48']

def run(clip,budget=700,seed=560,profile=PROFILE):
    start=time.monotonic();folder=ROOT/clip; src=ROOT/'datasets'/clip
    z=np.load(folder/'trained_parameters.npz')
    K=np.array(z['K'],dtype=np.int64);P=np.array(z['P'],dtype=np.int64);E=np.array(z['E'],dtype=np.int64)
    mask=np.array(z['mask'],dtype=np.uint8)
    frames=len(P);n=frames*256
    bits=np.full(frames,1 if profile[0]==4 else 0,dtype=np.uint8)
    bits[E==0]=0
    ev=Evaluator(load_wav(src/'original.wav'),load_wav(src/'lpx3_voice.wav'))
    def evaluate(fast=bits):
        y=render(K,P,E,mask,fast,n,*profile)
        m=ev.metrics(y)
        return m,score(m)
    before_pcm=np.fromfile(folder/'emu_pwm_u8.raw','u1').astype(np.int16)-128
    prev=ev.metrics(before_pcm)
    prev_score=score(prev)
    curr,best=evaluate()
    assert np.all(before_pcm==render(K,P,E,mask,bits,n,*profile)), 'Starting firmware must be bit exact'
    edits=[]
    # First: exact Flash budget, dropping the least acoustically important key.
    max_speech=FLASH_LIMIT-DECODER_SIZE-1
    speech,_=pack(K,P,E,mask,bits)
    if len(speech)>max_speech:
        while len(speech)>max_speech:
            trial=[]
            candidates=np.flatnonzero(mask)
            for i in candidates[1:]:
                mask[i]=0
                test,b=evaluate()
                trial.append((b,int(i)))
                mask[i]=1
            if not trial:raise RuntimeError('No more spectral keyframes to remove')
            b,i=max(trial)
            mask[i]=0;curr,best=evaluate();edits.append(('omit-key',i))
            speech,_=pack(K,P,E,mask,bits)
    # Then use spare Flash for additional keyframes if they increase quality.
    while len(speech)+4<=max_speech:
        trial=[]
        for i in np.flatnonzero((E>0)&(mask==0)):
            mask[i]=1
            test,b=evaluate()
            trial.append((b,int(i)))
            mask[i]=0
        if not trial:break
        val,i=max(trial)
        if val<best+1e-5:break
        mask[i]=1;curr,best=evaluate();edits.append(('add-key',i))
        speech,_=pack(K,P,E,mask,bits)
    chosen_k=int(np.sum(mask))
    after_keys=curr.copy()
    def flags_pass():
        nonlocal curr,best
        changes=0
        for i in np.flatnonzero(E>0):
            bits[i]^=1
            trial,val=evaluate()
            if (val>best+0.000002 and trial['stoi']>=prev['stoi']-0.008
                and trial['clicks_60']<=max(4,prev['clicks_60']+2)):
                best, curr=val,trial;changes+=1;edits.append(('rate',int(i)))
            else:bits[i]^=1
        return changes
    for _ in range(3):
        if not flags_pass():break
    after_flags=curr.copy()
    rng=np.random.default_rng(seed)
    available=np.flatnonzero(E>0)
    key_idx=np.flatnonzero(mask)
    accepted=0
    for it in range(budget):
        typ=int(rng.integers(10))
        if typ<7:
            i=int(rng.choice(key_idx));j=int(rng.integers(8))
            old=int(K[i,j]);value=int(np.clip(old+int(rng.choice([-2,-1,1,2])),-7,7))
            if value==old:continue
            K[i,j]=value
        elif typ<9:
            i=int(rng.choice(available));j=-1
            old=int(E[i]);value=int(np.clip(old+int(rng.choice([-2,-1,1,2])),1,15))
            if value==old:continue
            E[i]=value
        else:
            i=int(rng.choice(available));j=-1
            old=int(P[i]);value=int(np.clip(old+int(rng.choice([-2,-1,1,2])),0,31))
            if value==old:continue
            P[i]=value
        trial,val=evaluate()
        if (val>best+0.000001 and trial['stoi']>=prev['stoi']-0.005
            and trial['clicks_60']<=max(4,prev['clicks_60']+2)):
            best,curr=val,trial;accepted+=1
            edits.append(('coefficient' if typ<7 else ('gain' if typ<9 else 'pitch'),i,j,old,value))
        else:
            if typ<7:K[i,j]=old
            elif typ<9:E[i]=old
            else:P[i]=old
        if (it+1)%250==0:
            print(clip,'trial',it+1,'accepted',accepted,'STOI',round(curr['stoi'],4),'mel',round(curr['mel_original'],4),'clicks',curr['clicks_48'],'sec',round(time.monotonic()-start,1),flush=True)
    for _ in range(3):
        if not flags_pass():break
    output=ROOT/'adaptive_results'/clip
    output.mkdir(parents=True,exist_ok=True)
    packed,events=pack(K,P,E,mask,bits)
    assert len(packed)<=max_speech
    (output/'voice_tinylpc.bin').write_bytes(packed)
    np.savez(output/'trained_parameters.npz',K=K,P=P,E=E,mask=mask,fast=bits)
    wav=render(K,P,E,mask,bits,n,*profile)
    sf.write(output/'adaptive_model.wav', wav.astype(np.float64)/128,7500,subtype='PCM_16')
    final,final_score=evaluate()
    report={'clip':clip,'profile_fast_samples':profile[0],'profile_slow_samples':profile[1],
            'flash_decoder_bytes':DECODER_SIZE,'flash_limit':FLASH_LIMIT,
            'frames':frames,'keyframes':chosen_k,'short_updates':int(np.sum((E>0)&(mask==0))),
            'fast_frames':int(np.sum((E>0)&(bits==1))),'slow_frames':int(np.sum((E>0)&(bits==0))),
            'speech_bytes':len(packed),'estimated_flash':DECODER_SIZE+len(packed)+1,
            'baseline_previous_AVR':prev,'baseline_score':prev_score,
            'after_keyframe_selection':after_keys,'after_speed_optimization':after_flags,
            'new_adaptive':final,'optimized_score':final_score,'param_accepts':accepted,'proposals':budget,
            'edits':edits,'seconds':round(time.monotonic()-start,1)}
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print('END',clip,'flash',report['estimated_flash'],'bytes','STOI',round(final['stoi'],5),'prev',round(prev['stoi'],5),'mel',round(final['mel_original'],4),'prev',round(prev['mel_original'],4),'fast',report['fast_frames'],'slow',report['slow_frames'],flush=True)
    return report

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--clip',required=True,choices=['xtuj-ntt','ne-otv'])
    ap.add_argument('--budget',type=int,default=700)
    args=ap.parse_args()
    run(args.clip,args.budget)

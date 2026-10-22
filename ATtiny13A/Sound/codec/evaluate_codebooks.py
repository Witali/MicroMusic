#!/usr/bin/env python3
"""Numerical trial of LPC coefficient-pattern dictionaries. Doesn't alter firmware.
For each phrase, reconstruct exactly as TinyLPC AVR would after dictionary substitution.
Shows whether storing 8 or 16 formant patterns can preserve quality.
"""
from pathlib import Path
import json,sys,numpy as np
from scipy.cluster.vq import kmeans2
from model_lite import render
from perceptual import Evaluator,load_wav
R=Path(__file__).resolve().parent

def fit_pools(z,pattern_count,seed=2026):
    K=np.asarray(z['K'],dtype='int64');E=np.asarray(z['E'],dtype='int64');active=np.where(E>0)[0]
    pool=K[active].astype(float)
    # Fit a single reusable learned formant dictionary for this phrase.
    best=None
    for trial in range(5):
        c,labels=kmeans2(pool,pattern_count,minit='points',iter=80,seed=seed+trial)
        c=np.clip(np.rint(c),-7,7).astype('int64')
        dist=np.sum((pool[:,None,:]-c[None,:,:])**2,axis=-1)
        label=np.argmin(dist,axis=1)
        loss=float(np.mean(np.sum((pool-c[label])**2,axis=1)))
        if best is None or loss<best[0]:best=(loss,c,label)
    out=K.copy();out[active]=best[1][best[2]]
    return out,best[0]

def main():
    output={}
    for name in ('xtuj-ntt','ne-otv'):
        folder=R/name
        z=np.load(folder/'refine/optimized_parameters.npz')
        K,P,E=(z[n].astype('int64') for n in ('K','P','E'))
        ev=Evaluator(load_wav(folder/'original.wav'),load_wav(folder/'teacher_8000.wav'))
        orig=ev.metrics(render(K,P,E,len(P)*256))
        info=[]
        for m in [4,8,12,16]:
            fit,l=fit_pools(z,m)
            pcm=render(fit,P,E,len(P)*256)
            met=ev.metrics(pcm)
            silence=len(E)-np.count_nonzero(E)
            estimated_speech_bytes=4*m+2*np.count_nonzero(E)+silence
            info.append({'patterns':m,'encoded_bytes_without_decoder':int(estimated_speech_bytes),
                'dictionary_MSE':l,'stoi':met['stoi'],'stoi_delta':met['stoi']-orig['stoi'],
                'spectral':met['mel_original'],'spectral_delta':met['mel_original']-orig['mel_original']})
        output[name]={'baseline':orig,'trials':info,'baseline_bytes':(folder/'firmware/voice_tinylpc.bin').stat().st_size}
        print(name,json.dumps(info,ensure_ascii=False,indent=2),flush=True)
    (R/'codebook_trial_report.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':main()

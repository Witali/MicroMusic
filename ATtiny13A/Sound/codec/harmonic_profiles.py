#!/usr/bin/env python3
"""TinyLPC hybrid excitation experiment; 2-bit harmonic timbre ID per frame (host-only).

The 8-bit synthesis lattice remains unchanged. The 4 profiles control the glottal
excitation spectrum, while each frame keeps its original seven LPC coefficients.
Not a firmware: direct evaluation of profiles and quantized samples before AVR port.
"""
from pathlib import Path
import numpy as np
from harmonic_bank_experiments import make_bank,render,K,P,E,L,record,ROOT,FS
import soundfile as sf

b, names = make_bank()
# profile 0: exact v4 [5,3,0,-2]; 1-3: broadband pulse + 4/8/12-peak harmonic spectra.
patterns=np.zeros((4,255,255), dtype=np.float64)
for p in range(2,255):
   for i, coeff in enumerate([5,3,0,-2]):patterns[0,p,i]=coeff
ids=[12,26,32] # 4-flat, 8-1/n, 12-1/n
for profile,bankid in enumerate(ids,start=1):
    patterns[profile]=.7*patterns[0]+.3*.65*b[bankid]

def synth(sel, smooth=0):
    # Blend 0 => excitation equal to prepacked patterns (4x 255 x 255)
    return render(K,P,E,patterns,L,np.asarray(sel,dtype=np.int64),1.,0.,smooth)

def score(y, for_search=True):
    a,mel,clicks,maxstep=record(y)
    return mel + max(0.,.785-a)*1.6 + clicks*.0025, (a,mel,clicks,maxstep)

if __name__=='__main__':
    N=len(P)
    for level in range(4):
        sel=np.full(N,level,dtype=np.int64)
        s,info=score(synth(sel))
        print('profile',level,'score',round(s,5),'stoi',round(info[0],4),'mel',round(info[1],4),'jumps>=60',info[2],flush=True)
    sel=np.zeros(N,dtype=np.int64)
    sel0=sel.copy()
    cur=score(synth(sel));print('initial',cur,flush=True)
    rng=np.random.default_rng(5)
    for epoch in range(2):
        ids=list(range(N));rng.shuffle(ids)
        changes=0
        for j in ids:
            if P[j]==0 or E[j]<=1:continue
            old=sel[j]; bestval=cur[0];best=old;beststat=cur[1]
            for k in range(4):
                if k==old:continue
                sel[j]=k
                yy=synth(sel)
                v,stat=score(yy)
                # tiny penalty for codebook switching frame-to-frame (optional)
                if v<bestval-0.00003:
                    bestval=v;best=k;beststat=stat
            sel[j]=best
            if best!=old:
                changes+=1
                cur=(bestval,beststat)
        print('epoch',epoch,'changes',changes,'profile counts',np.bincount(sel,minlength=4),'score',cur,flush=True)
    y=synth(sel);baseline=synth(sel0)
    print('final',score(y), 'base',score(baseline),flush=True)
    np.savez(ROOT/'harmonic_profiles_2bit.npz',profile=sel,profile_base=sel0,bank=patterns,description=np.array(['Original glottal','4 harmonics + chirp','8 harmonics + chirp','12 harmonics + chirp']))
    sf.write(ROOT/'TinyLPC_harmonic_profiles.wav',y/128,FS)
    source,sr=sf.read(ROOT/'source_original_7500.wav');source=source[:L]
    pad=np.zeros(int(.18*FS))
    targets=[source,baseline/128,y/128]
    audio=[]
    for a in targets:
      a=a[:L];audio.extend([a,pad])
    sf.write(ROOT/'harmonic_profiles_A_B.wav',np.concatenate(audio),FS)
    (ROOT/'harmonic_profiles_results.txt').write_text('\n'.join(['ORIGINAL | v4 | 2-bit harmonic profiles',str(score(baseline)),str(score(y)),str(list(np.bincount(sel,minlength=4)))])+'\n')

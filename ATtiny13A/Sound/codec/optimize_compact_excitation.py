#!/usr/bin/env python3
"""Optimize K and gain for four-tap broad harmonic excitation [2,3,2,-1].
All parameters and generated voices fit the original 435-byte TinyLPC stream.
This program optimizes an AVR-exact 8-bit model; independent instruction-level
emulator validation is needed after modifying the assembly.
"""
from pathlib import Path
import numpy as np
from test_variants import synth_chirp
from spectral_objective import evaluate,x
from model_exact import synth_exact
N=87;L=256*N
ROOT=Path(__file__).resolve().parent
z=np.load(ROOT/'best_parameters.npz');K=z['K'].astype(np.int64).copy();P=z['P'].astype(np.int64).copy();E=z['E'].astype(np.int64).copy()
chirp=np.array([2,3,2,-1],dtype=np.int64)


def calc(K,P,E):
    y=synth_chirp(K,P,E,L,chirp,0)
    met=evaluate(y[:len(x)]/128,True)
    jump=int(np.sum(np.abs(np.diff(y))>=60))
    val=2*met['stoi']-.8*met['spectral_mel_distance']-.16*met['loudness_envelope_error']-.0007*jump
    return val,met,jump

score,met,jumps=calc(K,P,E);print('initial',round(score,5),met,'jumps>=60',jumps,flush=True)
rng=np.random.default_rng(19)
for ep in range(2):
    changed=0;calls=0
    for fi in rng.permutation(N):
        if E[fi]==0: continue
        # Adjust gain first. For quiet frames no need to change all coefficients.
        old=int(E[fi]);best=old;bestscore=score
        for v in np.unique(np.clip([old-2,old-1,old+1,old+2,round(old*.75)],0,15)):
            E[fi]=v; vscore,_,_=calc(K,P,E); calls+=1
            if vscore>bestscore+1e-5: bestscore=vscore;best=v
        E[fi]=best
        if best!=old: changed+=1;score=bestscore
        if E[fi]<=1: continue
        for j in rng.permutation(7):
            old=int(K[fi,j]);best=old;bestscore=score
            for v in np.unique(np.clip([old-2,old-1,old+1,old+2],-7,7)):
                K[fi,j]=v;vscore,_,_=calc(K,P,E); calls+=1
                if vscore>bestscore+1e-5:bestscore=vscore;best=v
            K[fi,j]=best
            if best!=old:changed+=1;score=bestscore
    _,met,jumps=calc(K,P,E)
    print('epoch',ep,'calls',calls,'changed',changed,'score',round(score,5),'STOI',round(met['stoi'],4),'mel',round(met['spectral_mel_distance'],4),'jumps',jumps,flush=True)
    np.savez(ROOT/f'compact_excitation_ep{ep}.npz',K=K,P=P,E=E)

import numpy as np
from numba import njit
@njit
def s8(v):return ((v+128)&255)-128
@njit
def mul_q4(x,k):
    a=s8(x)
    if k<0:a=s8(-a)
    return ((a*abs(k))>>4)&255
@njit
def decode(frames,durations,keep_phase=0):
    n=int(np.sum(durations))
    out=np.empty(n,np.uint8)
    state=np.zeros(8,np.int32);k=np.zeros(8,np.int32)
    seed=0xa7;period=0;gain=0;phase=1;mode=0
    fi=0;next_t=int(durations[0])-1
    for t in range(n):
        if t==0 or t==next_t:
            if t!=0:
                fi+=1
                if fi>=len(frames):fi=0
                next_t+=int(durations[fi])
            period=int(frames[fi,0]);gain=int(frames[fi,1])&15
            mode=(int(frames[fi,1])>>4)&3
            if not keep_phase:phase=period
            for j in range(4):
                data=int(frames[fi,2+j])
                k[j*2]=(data&15)-8
                k[j*2+1]=(data>>4)-8
        ex=0
        if period:
            phase=(phase-1)&255
            if phase==0:
                phase=period
                ex=(2*gain)&255
            else:
                lag=period-phase
                if lag==1:ex=(gain*(3-(mode&1)))&255
                elif lag==2:ex=(gain*(2-(mode>>1)))&255
                elif lag==3:ex=(-gain)&255
        else:
            low=seed&1
            seed=seed>>1
            if low:seed=seed^0xb8
            ex=((-gain if (seed&1) else gain))&255
        for j in range(7,-1,-1):
            old=state[j];coef=k[j]
            ex=(ex-mul_q4(old,coef))&255
            if j<7:state[j+1]=(old+mul_q4(ex,coef))&255
        state[0]=ex
        out[t]=(ex+128)&255
    return out

"""PC-only original HQ4 experiment: optional frame-wise periodic/noise mix.

This duplicates the exact signed eight-bit reference lattice, including its
frame-boundary convention. Noise enters the excitation before the lattice.
It is not an AVR implementation and does not change the public HQ4 format.
"""
import numpy as np
from numba import njit
from model import mul_q4

VERSION = 'hq4-mixed-excitation-v1'


def pack_mix(codes):
    values = np.asarray(codes)
    if values.ndim != 1 or values.dtype.kind not in 'ui' or np.any(values>3) or np.any(values<0):
        raise ValueError('Expected a one-dimensional integer mix map with codes0..3')
    result = bytearray((len(values)+3)//4)
    for i, value in enumerate(values):
        result[i//4] |= int(value)<<((i%4)*2)
    return bytes(result)


def unpack_mix(payload, frames):
    if frames<0 or len(payload)!=(frames+3)//4:
        raise ValueError('Mix payload length differs from frame count')
    values = np.asarray([(payload[i//4]>>((i%4)*2))&3 for i in range(frames)],dtype=np.uint8)
    if pack_mix(values)!=bytes(payload):
        raise ValueError('Mix payload contains nonzero unused bits')
    return values


@njit(cache=True)
def _decode(frames,durations,codes,enabled,keep_phase):
    n=int(np.sum(durations))
    out=np.empty(n,np.uint8)
    state=np.zeros(8,np.int32);k=np.zeros(8,np.int32)
    seed=0xa7;period=0;gain=0;phase=1;mode=0;noise_gain=0
    fi=0;next_t=int(durations[0])-1
    for t in range(n):
        if t==0 or t==next_t:
            if t!=0:
                fi+=1
                if fi>=len(frames):fi=0
                next_t+=int(durations[fi])
            period=int(frames[fi,0]);gain=int(frames[fi,1])&15
            mode=(int(frames[fi,1])>>4)&3
            code=int(codes[fi]) if enabled else 0
            noise_gain=(gain>>(3-code)) if code else 0
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
            if noise_gain:
                low=seed&1
                seed=seed>>1
                if low:seed=seed^0xb8
                ex=(ex+(-noise_gain if (seed&1) else noise_gain))&255
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


def decode(frames,durations,codes,*,enabled=True,keep_phase=0):
    f,d,m=np.asarray(frames),np.asarray(durations),np.asarray(codes)
    if (f.ndim!=2 or f.shape[1]!=6 or not len(f) or f.dtype.kind not in 'ui'
            or np.any(f<0) or np.any(f>255) or np.any(f[:,0]>126) or np.any(f[:,1]>63)):
        raise ValueError('Expected valid integer HQ4 frames')
    if (d.ndim!=1 or len(d)!=len(f) or d.dtype.kind not in 'ui'
            or any(int(v) not in (64,128,192,256) for v in d)):
        raise ValueError('Expected one valid HQ4 duration per frame')
    if m.ndim!=1 or len(m)!=len(f):
        raise ValueError('Expected one mix code per HQ4 frame')
    pack_mix(m)
    return _decode(f,d,m,bool(enabled),int(bool(keep_phase)))

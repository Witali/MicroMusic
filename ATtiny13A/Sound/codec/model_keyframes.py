"""Bit-exact 8-bit excitation/lattice model for ATtiny13A keyframe student.
Every frame has pitch and energy; 8 LPC coefficients transmitted only at selected keyframes.
Current 4-bit lattice coefficients and energy change by at most 1 step per 16/8 output samples.
"""
import numpy as np
from numba import njit

@njit(cache=True)
def render(K, P, E, key, n_samples, k_step=16, gain_step=8):
    st=np.zeros(8,dtype=np.int64)
    cur=np.zeros(8,dtype=np.int64)
    tar=np.zeros(8,dtype=np.int64)
    out=np.empty(n_samples,dtype=np.int16)
    lfsr=0xa7; phase=1; period=0; target=0; gain=0; desired_gain=0
    n=len(P)
    for t in range(n_samples):
        fi=((t+1)//256)%n
        rem=(t+1)&255
        if t==0 or rem==0:
            new_period=int(P[fi]); target=new_period
            desired_gain=int(E[fi])
            if key[fi] and E[fi]>0:
                for k in range(8):tar[k]=int(K[fi,k])
            if desired_gain==0:
                gain=0
                for k in range(8):st[k]=0
            if ((new_period-period+4)&255)>=9: period=new_period
        if (rem&7)==0:
            if period<target:period+=1
            elif period>target:period-=1
        if (rem&(gain_step-1))==0:
            if gain<desired_gain:gain+=1
            elif gain>desired_gain:gain-=1
        if (rem&(k_step-1))==0:
            for k in range(8):
                if cur[k]<tar[k]:cur[k]+=1
                elif cur[k]>tar[k]:cur[k]-=1
        if period:
            phase=(phase-1)&255
            if phase==0:
                phase=period; exc=2*gain
            else:
                dt=(period-phase)&255
                if dt==1:exc=3*gain
                elif dt==2:exc=2*gain
                elif dt==3:exc=-gain
                else:exc=0
        else:
            lfsr=(lfsr>>1)^(0xb8 if (lfsr&1) else 0)
            exc=-gain if (lfsr&1) else gain
        v=exc
        for k in range(7,-1,-1):
            prod=(int(cur[k])*st[k])>>4
            v=((v-prod+128)&255)-128
            if k<7:
                prod2=(int(cur[k])*v)>>4
                st[k+1]=((st[k]+prod2+128)&255)-128
        st[0]=v;out[t]=v
    return out


def packed_size(E,key):
    # All frames: pitch+gain 2 bytes; keyframes add 4 coefficient bytes.
    # Long full-silence RLE saves more; each run can be written 1 byte.
    n=len(E); s=0;i=0
    while i<n:
        if E[i]==0:
            j=i+1
            while j<n and E[j]==0 and j-i<30:j+=1
            s+=1;i=j
        else:
            s+=6 if key[i] else 2
            i+=1
    return s

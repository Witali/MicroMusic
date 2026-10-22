"""Bit-exact ATtiny13A 8-stage lattice with per-frame fast/slow slew speeds.
Frame header bit6 chooses the smoothing interval; bit7 continues to mean short frame.
The last stage and state update use AVR 8-bit wraparound arithmetic.
"""
import numpy as np
from numba import njit

@njit(cache=True)
def render(K, P, E, key, fast, n_samples, fast_step=2, slow_step=8):
    st=np.zeros(8,dtype=np.int64)
    cur=np.zeros(8,dtype=np.int64)
    tar=np.zeros(8,dtype=np.int64)
    out=np.empty(n_samples,dtype=np.int16)
    lfsr=0xa7;phase=1;period=0;target=0;gain=0;desired_gain=0;mask=slow_step-1
    n=len(P)
    for t in range(n_samples):
        fi=((t+1)//256)%n
        rem=(t+1)&255
        if t==0 or rem==0:
            new_period=int(P[fi]);target=new_period
            desired_gain=int(E[fi])
            if desired_gain>0:
                mask=(fast_step if fast[fi] else slow_step)-1
            if key[fi] and E[fi]>0:
                for k in range(8):tar[k]=int(K[fi,k])
            if desired_gain==0:
                gain=0
                for k in range(8):st[k]=0
            if ((new_period-period+4)&255)>=9:period=new_period
        if (rem&7)==0:
            if period<target:period+=1
            elif period>target:period-=1
        if (rem & mask)==0:
            for k in range(8):
                if cur[k]<tar[k]:cur[k]+=1
                elif cur[k]>tar[k]:cur[k]-=1
            if gain<desired_gain:gain+=1
            elif gain>desired_gain:gain-=1
        if period:
            phase=(phase-1)&255
            if phase==0:
                phase=period;exc=2*gain
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

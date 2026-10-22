"""Byte-exact DSP model for firmware/tinylpc.S (pitch_glide variant).
All updates use signed 8-bit wraparound; filter MAC uses signed >>4.
The independent JavaScript instruction emulator is used for final validation.
"""
import numpy as np
from numba import njit

@njit(cache=True)
def render(K, P, E, samples):
    frames=len(P)
    out=np.empty(samples,dtype=np.int16)
    st=np.zeros(7,dtype=np.int64)
    lfsr=0xa7
    phase=1
    period=0
    target=0
    gain=0
    for t in range(samples):
        fi=((t+1)//256)%frames
        rem=(t+1)&255
        if t==0 or rem==0:
            newperiod=int(P[fi]);gain=int(E[fi]);target=newperiod
            if gain==0:
                for k in range(7):st[k]=0
            # unsigned AVR if ((new - old + 4)&255)<9 -> glide
            if ((newperiod-period+4)&255)>=9:
                period=newperiod
        if (rem&7)==0:
            if period<target:period+=1
            elif period>target:period-=1
        if period:
            phase=(phase-1)&255
            if phase==0:
                phase=period
                exc=2*gain
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
        for k in range(6,-1,-1):
            prod=(int(K[fi,k])*st[k])>>4
            v=((v-prod+128)&255)-128
            if k<6:
                v2=(int(K[fi,k])*v)>>4
                st[k+1]=((st[k]+v2+128)&255)-128
        st[0]=v
        out[t]=v
    return out

def reference_selftest(folder):
    from pathlib import Path
    p=Path(folder)
    z=np.load(p/'references'/'base_parameters.npz')
    n=len(z['P'])*256
    model=render(z['K'].astype('int64'),z['P'].astype('int64'),z['E'].astype('int64'),n).astype('int16')
    actual=np.fromfile(p/'references'/'lite_baseline_u8.raw',dtype='u1').astype('int16')-128
    diff=np.flatnonzero(model!=actual)
    print(f'AVR model self-check: {len(actual)-len(diff)}/{len(actual)} samples agree; first differences {diff[:12].tolist()}')
    return int(len(diff))

if __name__=='__main__':
    from pathlib import Path
    print('mismatch count',reference_selftest(Path(__file__).parent))

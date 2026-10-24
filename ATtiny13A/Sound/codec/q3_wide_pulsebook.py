"""PC-only precision diagnostic: Q3 filter with fractional internal states.

No AVR code size or timing is claimed. The output is still a single PWM byte;
internal arithmetic is audited against a signed16-bit implementation limit.
"""
import numpy as np
from numba import njit


@njit(cache=True)
def render(frames,durations,book,fractional_bits=4,nearest=True,extended_pole=False):
    out=np.empty(int(durations.sum()),np.uint8)
    states=np.zeros(8,np.int32);k=np.zeros(8,np.int32)
    counts=np.zeros(4,np.int64)  # product16, lattice16, tilt16, PWM overflow
    maximum=np.zeros(3,np.int64)  # product, lattice, deemphasis state magnitudes
    seed,phase,fi,next_t=0xa7,1,0,int(durations[0])-1
    period=gain=mode=previous=0
    for t in range(len(out)):
        if t==0 or t==next_t:
            if t:
                fi+=1
                if fi==len(frames):fi=0
                next_t+=int(durations[fi])
            period=np.int64(frames[fi,0]);gain=np.int64(frames[fi,1])&15;mode=np.int64(frames[fi,1]>>4)
            phase=period
            for j in range(4):
                v=int(frames[fi,2+j]);k[2*j]=(v&15)-8;k[2*j+1]=(v>>4)-8
        ex=0
        if period:
            phase=(phase-1)&255
            if not phase:
                phase=period;ex=int(book[mode,0])*gain
            else:
                lag=period-phase
                if lag<16:ex=int(book[mode,lag])*gain
        else:
            low=seed&1;seed>>=1
            if low:seed^=0xb8
            ex=-gain if seed&1 else gain
        ex<<=fractional_bits
        for j in range(7,-1,-1):
            old,c=states[j],k[j]
            if extended_pole and c==-8:
                delta=-old+((old+(8 if nearest else 0))>>4)
            else:
                product=old*c
                maximum[0]=max(maximum[0],abs(product));counts[0]+=int(product< -32768 or product>32767)
                delta=(product+(4 if nearest else 0))>>3
            ex-=delta
            maximum[1]=max(maximum[1],abs(ex));counts[1]+=int(ex< -32768 or ex>32767)
            if j<7:
                if extended_pole and c==-8:
                    delta=-ex+((ex+(8 if nearest else 0))>>4)
                else:
                    product=ex*c
                    maximum[0]=max(maximum[0],abs(product));counts[0]+=int(product< -32768 or product>32767)
                    delta=(product+(4 if nearest else 0))>>3
                value=old+delta
                maximum[1]=max(maximum[1],abs(value));counts[1]+=int(value< -32768 or value>32767)
                states[j+1]=value
        states[0]=ex
        previous=ex+previous-(previous>>1)
        maximum[2]=max(maximum[2],abs(previous));counts[2]+=int(previous< -32768 or previous>32767)
        sample=(previous+((1<<(fractional_bits-1)) if fractional_bits else 0))>>fractional_bits
        counts[3]+=int(sample< -128 or sample>127)
        out[t]=(sample+128)&255
    return out,counts,maximum

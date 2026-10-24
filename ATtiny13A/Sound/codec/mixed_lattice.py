"""PC oracle with per-stage reflection precision and selectable lattice order.

The first two stages may use Q7 without forcing the other stages to do so.
Word wrap, coefficient-sign negation and rounding are explicit. No AVR size or
deadline is claimed by this portable specification.
"""
import numpy as np
from numba import njit

SCHEMA='mixed-lattice-v1'
PULSE_SCHEMA='mixed-lattice-pulse-v1'


@njit(cache=True)
def multiply(value,coefficient,bits,state_bits=6,nearest=True):
    limit=128 if state_bits==0 else 32768
    if coefficient<0:value=((-value+limit)&(2*limit-1))-limit
    product=value*abs(coefficient)
    if nearest:
        half=1<<(bits-1)
        result=(product+half)>>bits if product>=0 else -((-product+half)>>bits)
    else:result=product>>bits
    return ((result+limit)&(2*limit-1))-limit


def validate(coefficients,coefficient_bits,state_bits):
    k,b=map(np.asarray,(coefficients,coefficient_bits))
    if (k.dtype.kind not in 'iu' or b.dtype.kind not in 'iu' or k.ndim!=2
            or k.shape[1] not in (6,8,10) or b.shape!=(k.shape[1],)
            or not np.all(np.isin(b,[3,4,5,6,7])) or state_bits not in (0,4,6,8)):
        raise ValueError('Invalid stable mixed-precision lattice')
    limits=1<<b.astype(np.int64)
    if np.any(k<=-limits) or np.any(k>=limits):raise ValueError('Unstable reflection coefficient')
    return k,b


@njit(cache=True)
def filter_signal(excitation,rows,coefficients,coefficient_bits,state_bits=6,nearest=True,tilt_shift=1,fraction_bits=2):
    order=coefficients.shape[1];states=np.zeros(order,np.int32);output=np.empty(len(rows),np.uint8)
    counts=np.zeros(4,np.int64);previous=0;limit=128 if state_bits==0 else 32768
    for n in range(len(rows)):
        row=rows[n];ex=np.int64(excitation[n])
        if state_bits>=fraction_bits:ex<<=state_bits-fraction_bits
        else:ex>>=fraction_bits-state_bits
        for j in range(order-1,-1,-1):
            old=int(states[j]);k=int(coefficients[row,j]);bits=int(coefficient_bits[j])
            counts[2]+=int(old==-limit and k<0)
            raw=ex-multiply(old,k,bits,state_bits,nearest)
            counts[0]+=int(raw < -limit or raw>=limit);ex=((raw+limit)&(2*limit-1))-limit
            if j<order-1:
                counts[2]+=int(ex==-limit and k<0)
                raw=old+multiply(ex,k,bits,state_bits,nearest)
                counts[1]+=int(raw < -limit or raw>=limit);states[j+1]=((raw+limit)&(2*limit-1))-limit
        states[0]=ex;raw=ex+previous-(previous>>tilt_shift)
        counts[3]+=int(raw < -limit or raw>=limit);previous=((raw+limit)&(2*limit-1))-limit
        sample=previous>>state_bits;counts[3]+=int(sample < -128 or sample>127);output[n]=(sample+128)&255
    return output,counts

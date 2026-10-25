"""Drop-in exact LPX4 mode selector for offline encoding ONLY.

All expensive pitch-candidate and Rice-cost loops are JIT-compiled with Numba.
Input/output decisions are designed to match lpx4.select_chunk for lossless
encoding. No changes to L4HY data format or AVR decoder.
"""
import numpy as np
from numba import njit
from lpx4 import best_direct, select_chunk

@njit(cache=True)
def _pitch_scores(y, h):
    # h = last 145 signed excitation symbols. Historic candidate order is lag 18..145.
    scores = np.empty(128, dtype=np.int64)
    gains = np.zeros(128, dtype=np.int32)
    for lag in range(18, 146):
        dot = 0.0
        power = 0.0
        for j in range(len(y)):
            x = h[145-lag+j] if j < lag else y[j-lag]
            dot += float(x)*float(y[j])
            power += float(x)*float(x)
        g = int(np.rint(16.0*dot/(power+1.0e-8)))
        if g < 0: g = 0
        elif g > 31: g = 31
        gains[lag-18] = g
        if g <= 1:
            scores[lag-18] = np.int64(0x7fffffffffffffff)
            continue
        score = 0
        for j in range(len(y)):
            x = h[145-lag+j] if j < lag else y[j-lag]
            pred = (x*g+8)>>4
            delta = int(y[j])-pred
            score += delta*delta
        scores[lag-18] = score
    return scores,gains

@njit(cache=True)
def _evaluate_exact(y,h,lag_gain,b,direct_cost):
    best_cost = 5+direct_cost
    best_lag=-1
    best_gain=0
    best_k=0
    lo=-(1<<(b-1)) if b else 0
    hi=(1<<(b-1))-1 if b else 0
    for i in range(len(lag_gain)):
        lag=int(lag_gain[i,0]); gain=int(lag_gain[i,1]); n=len(y)
        # Equivalent of lpx4.dif_cost but one scan of delta symbols for all k.
        costs=np.zeros(7,dtype=np.int32)
        valid=np.ones(7,dtype=np.uint8)
        for j in range(n):
            x = h[145-lag+j] if j<lag else y[j-lag]
            pred = (gain*x+8)>>4
            if b==0:pred=0
            elif pred<lo:pred=lo
            elif pred>hi:pred=hi
            d=int(y[j])-pred
            z=2*d if d>=0 else -2*d-1
            for k in range(7):
                quotient=z>>k
                if quotient>8: valid[k]=0
                costs[k]+=quotient+1+k
        kbest=7
        costbest=n*8
        for k in range(7):
            if valid[k] and (costs[k]<costbest or (costs[k]==costbest and k<kbest)):
                costbest=costs[k];kbest=k
        total=17+costbest
        if total<best_cost:
            best_cost=total;best_lag=lag;best_gain=gain;best_k=kbest
    return best_cost,best_lag,best_gain,best_k


def select_chunk_fast(y,hist,b,min_snr=float('inf')):
    import math
    if not math.isinf(min_snr):
        return select_chunk(y,hist,b,min_snr)
    direct_cost,k=best_direct(y,b)
    if len(hist)<145 or b==0:
        return 5+direct_cost,('direct',k),list(y)
    h=np.asarray(hist[-145:],dtype=np.int32)
    target=np.asarray(y,dtype=np.int32)
    scores,gains=_pitch_scores(target,h)
    # Historical sort is by (score, lag, gain). Avoid tie-policy changes.
    ranks=sorted((int(scores[i]),i+18,int(gains[i]))
                 for i in range(128) if gains[i]>1)[:8]
    seen=set();params=[]
    for _,lag,gain in ranks:
        for delta in (-1,0,1):
            g=max(0,min(31,gain+delta))
            if (lag,g) not in seen:
                params.append((lag,g));seen.add((lag,g))
    if not params:return 5+direct_cost,('direct',k),list(y)
    cost,lag,g,k2=_evaluate_exact(target,h,np.asarray(params,dtype=np.int32),b,direct_cost)
    if lag<0:return 5+direct_cost,('direct',k),list(y)
    return int(cost),('exact',int(lag),int(g),int(k2)),list(y)

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


@njit(cache=True)
def _exhaustive(y,h,b,initial_cost,allow_sparse):
    """All 128 lags / 32 gains, exact Rice and exact sparse only."""
    best=initial_cost;typ=0;best_lag=0;best_gain=0;best_k=0
    lo=-(1<<(b-1));hi=(1<<(b-1))-1
    for lag in range(18,146):
        for gain in range(32):
            if gain==0 and lag!=18:continue
            costs=np.zeros(7,np.int32);valid=np.ones(7,np.uint8)
            pulses=0;sparse_ok=allow_sparse
            for j in range(len(y)):
                x=h[145-lag+j] if j<lag else y[j-lag]
                p=min(hi,max(lo,(gain*x+8)>>4))
                d=int(y[j])-p;z=2*d if d>=0 else -2*d-1
                if d:
                    pulses+=1
                    if d < -16 or d > 15 or pulses>10:sparse_ok=False
                for k in range(7):
                    quotient=z>>k
                    if quotient>8:valid[k]=0
                    costs[k]+=quotient+1+k
            for k in range(7):
                cost=17+costs[k]
                if valid[k] and cost<best:
                    best=cost;typ=1;best_lag=lag;best_gain=gain;best_k=k
            # Eight-bit literal exact residuals cannot beat raw <=6-bit q.
            cost=18+11*pulses
            if sparse_ok and cost<best:
                best=cost;typ=2;best_lag=lag;best_gain=gain;best_k=0
    return best,typ,best_lag,best_gain,best_k


def select_chunk_exhaustive(y,hist,b,allow_sparse=True):
    """Minimum bits within existing modes; sparse is always exactly lossless.

    Initial history is zero, as on the MCU. Ties retain direct first, then
    increasing lag/gain/k. This opt-in search does not change legacy output.
    """
    direct,k=best_direct(y,b)
    if not b:return 5+direct,('direct',k),list(y)
    padded=([0]*max(0,145-len(hist))+list(hist[-145:]))
    cost,typ,lag,gain,k2=_exhaustive(np.asarray(y,np.int32),np.asarray(padded,np.int32),b,5+direct,bool(allow_sparse))
    if not typ:return int(cost),('direct',k),list(y)
    if typ==1:return int(cost),('exact',int(lag),int(gain),int(k2)),list(y)
    from lpx4 import calc_pred
    history=list(hist);pulses=[]
    for j,val in enumerate(y):
        delta=int(val)-calc_pred(history,int(lag),int(gain),b)
        if delta:pulses.append((j,delta))
        history.append(int(val))
    return int(cost),('sparse',int(lag),int(gain),pulses),list(y)

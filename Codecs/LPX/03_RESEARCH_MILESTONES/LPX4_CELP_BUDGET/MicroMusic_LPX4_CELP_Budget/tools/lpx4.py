#!/usr/bin/env python3
"""LPX4 experimental hybrid: EXACT pitch Rice, direct Rice, sparse pitch pulses.
LSF10 frame coding is shared with LPX3 v7; 80-sample scales shared, 40-sample excitation subframes.
The costly search is performed ONLY in the offline Python encoder.
LSB-first packed stream, no mandatory alignments other than the file tail.

Patent/licensing of CELP variants is intentionally not addressed here. Research prototype.
"""
import struct, math, collections, argparse, json
from pathlib import Path
import numpy as np
from l3av_parse import unpack
from rice_v3 import BitWriter,BitReader,mapped
from rice_v4_reference import write_scale, read_scale,plane_cost,putplane,getplane
from rice_v7 import absolute_lsf10, HUFF3, HUFF3_DECODE

HEADER='<4sBBHIHHHH'
LAG_MIN=18; LAG_MAX=145
# 00 direct k=0 raw b-bit, k1..6 Rice, k7 Huff3
# 01 exact pitch-coded (7-bit lag,5-bit gain,3-bit k; 7=>8-bit signed literal)
# 10 pitch+sparse pulse corrections (7-bit lag,5-bit gain,4-bit count, 6+5 bits each)
# 11 invalid

def signed_from_z(z):return z>>1 if not z&1 else -((z+1)>>1)
def clamp(x,a,b):return min(max(x,a),b)
def calc_pred(qhistory,lag,gain,b):
    x=int(qhistory[-lag]);y=(gain*x+8)>>4
    if b==0:return 0
    return clamp(y,-(1<<(b-1)),(1<<(b-1))-1)

def code_cost(arr,b,k):
    if k==0:return len(arr)*b
    if k==7:return sum(len(HUFF3[x]) for x in arr) if b==3 else 999999
    z=[mapped(int(x)) for x in arr]
    return sum((a>>k)+1+k for a in z) if max((a>>k for a in z),default=0)<=8 else 999999

def best_direct(q,b):return min((code_cost(q,b,k),k) for k in range(8))
def dif_cost(ds,k):
    if k==7:return len(ds)*8
    z=[mapped(int(x)) for x in ds]
    if max((x>>k for x in z),default=0)>8:return 999999
    return sum((x>>k)+1+k for x in z)

def candidates(y,hist):
    """Find a small number of plausible (lag, gainQ4), no expensive search in AVR."""
    best=[]
    h=np.asarray(hist,dtype=np.int16);o=np.asarray(y,dtype=np.int16)
    for lag in range(18,146):
        # oracle for within-chunk values; exact-code mode can reconstruct them.
        source=np.concatenate((h,o))
        x=source[len(h)-lag:len(h)-lag+len(y)].astype(np.float64)
        if len(x)!=len(y):continue
        g=int(np.clip(np.round(16*np.dot(x,o)/(np.dot(x,x)+1e-8)),0,31))
        if g<=1:continue
        sc=np.sum((o-((x*g+8).astype(np.int32)>>4))**2)
        best.append((sc,lag,g))
    best.sort()
    opts=[];seen=set()
    for _,lag,g in best[:8]:
        for dg in (-1,0,1):
            z=clamp(g+dg,0,31)
            if (lag,z) not in seen:opts.append((lag,z));seen.add((lag,z))
    return opts

def reconstruct_sparse(y,hist,b,lag,gain,selection):
    predHist=list(hist);qlo,qhi=(-(1<<(b-1)),(1<<(b-1))-1) if b else (0,0)
    predicted=[]
    # First pass with lossless/oracle previous within-frame q to rank pulse locations
    oracleHist=list(hist)
    for x in y:
        predicted.append(calc_pred(oracleHist,lag,gain,b))
        oracleHist.append(int(x))
    err=np.asarray(y,dtype=np.int16)-np.asarray(predicted,dtype=np.int16)
    positions=sorted(sorted(range(len(y)),key=lambda j:abs(int(err[j])),reverse=True)[:selection])
    pulses=[];out=[]
    for i,desired in enumerate(y):
        p=calc_pred(predHist,lag,gain,b)
        if i in positions:
            z=clamp(int(desired)-p,-16,15)
            if z:
                p=clamp(p+z,qlo,qhi)
                pulses.append((i,z))
        out.append(p);predHist.append(p)
    return out,pulses

def select_chunk(y,hist,b,min_snr):
    """Return (description, q_reconstructed, bit cost); no output loss for min_snr=inf."""
    directCost,k=best_direct(y,b)
    best=(2+3+directCost,('direct',k),list(y))
    if len(hist)<145 or b==0:return best
    poss=candidates(y,hist)
    # Exact pitch mode: up to eight reversible Rice candidates, no sound changes.
    for lag,g in poss:
        curhist=list(hist)
        delta=[]
        for val in y:
            pred=calc_pred(curhist,lag,g,b)
            delta.append(int(val)-pred)
            curhist.append(int(val))
        cost,k2=min((dif_cost(delta,k2),k2) for k2 in range(8))
        total=2+7+5+3+cost
        if total<best[0]:best=(total,('exact',lag,g,k2),list(y))
    # Optional approximate CELP subframes: subframe gain/pitch + sparse innovations.
    if math.isinf(min_snr):return best
    power=sum(int(t)*int(t) for t in y)+1
    allow=power*(10**(-min_snr/10))
    for lag,g in poss[:14]:
        for count in (0,2,4,6,8,10):
            est,pulses=reconstruct_sparse(y,hist,b,lag,g,count)
            sse=sum((int(a)-int(t))**2 for a,t in zip(est,y))
            if sse>allow:continue
            total=2+7+5+4+len(pulses)*11
            if total<best[0]:best=(total,('sparse',lag,g,pulses),est)
    return best

def put_rice(w,vals,k):
    for val in vals:
        z=mapped(int(val));q=z>>k
        if q>8:raise ValueError('long unary')
        for _ in range(q):w.put(0,1)
        w.put(1,1)
        if k:w.put(z&((1<<k)-1),k)

def get_rice(r,k):
    hi=0
    while r.get(1)==0:
        hi+=1
        if hi>8:raise ValueError('Rice unary overflow')
    return signed_from_z((hi<<k)|(r.get(k) if k else 0))

def encode(doc,min_snr=float('inf'),allowed_sparse=None):
    if doc['raw'][:4]!=b'L3AV' or doc['raw'][5]!=3:raise ValueError('require 10-bit LSF LPX3 v1')
    header=bytearray(doc['raw'][:20]);header[0:4]=b'L4HY';header[4]=2
    w=BitWriter();oldscale=0;outQ=[];stats=collections.Counter();chunkReport=[]
    p=0
    for iframe,frame in enumerate(doc['frames']):
        tag,payload=frame[0],frame[1:]
        if tag==0:w.put(0,1)
        elif tag==5:
            w.put(1,1);w.put(0,1)
            for v in absolute_lsf10(payload):w.put(v&255,8);w.put(v>>8,2)
        elif tag==6:
            w.put(1,1);w.put(1,1)
            use_raw=80<=plane_cost(payload)
            w.put(int(use_raw),1)
            if use_raw:
                for v in payload:w.put(v,8)
            else:
                for v in payload:putplane(w,v)
        else:raise ValueError(f'frame tag {tag}')
        for block in doc['blocks'][2*iframe:2*iframe+2]:
            b=block['bits'];q=block['q']
            w.put(b,3)
            write_scale(w,oldscale,block['scale']);oldscale=block['scale']
            for start in range(0,len(q),40):
                y=q[start:start+40]
                numbits,mode,decoded=select_chunk(y,outQ,b,min_snr if (allowed_sparse is None or p in allowed_sparse) else float('inf'))
                if mode[0]=='direct':
                    w.put(0,2);k=mode[1];w.put(k,3)
                    if k==0:
                        for x in y:
                            if b:w.put(x+(1<<(b-1)),b)
                    elif k==7:
                        for x in y:
                            for bit in HUFF3[x]:w.put(int(bit),1)
                    else:put_rice(w,y,k)
                elif mode[0]=='exact':
                    _,lag,g,k=mode
                    w.put(1,2);w.put(lag-LAG_MIN,7);w.put(g,5);w.put(k,3)
                    wh=list(outQ)
                    ds=[]
                    for x in y:
                        ds.append(int(x)-calc_pred(wh,lag,g,b));wh.append(int(x))
                    if k==7:
                        for x in ds:w.put(x&255,8)
                    else:put_rice(w,ds,k)
                elif mode[0]=='sparse':
                    _,lag,g,pulses=mode
                    w.put(2,2);w.put(lag-LAG_MIN,7);w.put(g,5);w.put(len(pulses),4)
                    for ix,v in pulses:
                        w.put(ix,6);w.put(mapped(v),5)
                else:raise AssertionError(mode)
                stats[mode[0]]+=1
                original_q=np.array(y,dtype=np.int16);decoded_q=np.array(decoded,dtype=np.int16)
                sse=int(np.sum((original_q-decoded_q)**2));power=int(np.sum(original_q**2))
                stats['q_sse']+=sse;stats['q_power']+=power;stats['samples']+=len(y)
                chunkReport.append({'position':p,'mode':mode[0],'bits':numbits,'count':len(y),'pulses':len(mode[3]) if mode[0]=='sparse' else 0,'errorSSE':sse,'power':power})
                outQ.extend(int(v) for v in decoded);p+=len(y)
    w.aligned();stream=bytes(header)+w.get();stats['frames']=len(doc['frames']);stats['bytes']=len(stream)
    return stream,dict(stats),chunkReport,outQ

def decode(data):
    if len(data)<20:raise ValueError('short header')
    magic,ver,fl,rate,n,pre,bright,f,b=struct.unpack_from(HEADER,data)
    if (magic,ver,fl,rate,f,b)!=(b'L4HY',2,3,8000,160,80):raise ValueError('bad LPX4 header')
    r=BitReader(data,20);qout=[];frames=[];blocks=[];scale=0;pos=0
    while pos<n:
        if r.get(1)==0:frame=b'\x00'
        elif r.get(1)==0:
            v=[r.get(8)|(r.get(2)<<8) for _ in range(10)]
            frame=b'\x05'+sum(x<<(10*i) for i,x in enumerate(v)).to_bytes(13,'little')
        else:
            raw=r.get(1)
            frame=b'\x06'+bytes([r.get(8) for _ in range(10)] if raw else [getplane(r) for _ in range(10)])
        frames.append(frame)
        for sub80 in range(2):
            if pos>=n:break
            bw=r.get(3)
            if bw not in (0,2,3,4,5,6):raise ValueError('bad source bits')
            scale=read_scale(r,scale)
            bl=[]
            count=min(80,n-pos)
            for partial in range(0,count,40):
                nsamp=min(40,count-partial);typ=r.get(2);q=[]
                if typ==0:
                    k=r.get(3)
                    for _ in range(nsamp):
                        if k==0:val=r.get(bw)-(1<<(bw-1)) if bw else 0
                        elif k==7:
                            if bw!=3:raise ValueError('Huff mode with wrong width')
                            s=''
                            while s not in HUFF3_DECODE:
                                s+=str(r.get(1))
                                if len(s)>5:raise ValueError('Huff overflow')
                            val=HUFF3_DECODE[s]
                        else:val=get_rice(r,k)
                        q.append(val);qout.append(val)
                elif typ in (1,2):
                    lag=r.get(7)+LAG_MIN;g=r.get(5)
                    if lag>LAG_MAX:raise ValueError('bad pitch lag')
                    if typ==1:k=r.get(3)
                    else:
                        pulses=[];pc=r.get(4)
                        for _ in range(pc):
                            ix=r.get(6);z=r.get(5)
                            if ix>=nsamp or (pulses and ix<=pulses[-1][0]):raise ValueError('invalid pulse position')
                            pulses.append((ix,signed_from_z(z)))
                    for j in range(nsamp):
                        pred=calc_pred(qout,lag,g,bw)
                        if typ==1:
                            if k==7:
                                z=r.get(8);delta=z-256 if z&128 else z
                            else:delta=get_rice(r,k)
                        else:
                            delta=pulses.pop(0)[1] if pulses and pulses[0][0]==j else 0
                        if typ==1:val=pred+delta
                        else:val=clamp(pred+delta,-(1<<(bw-1)) if bw else 0,(1<<(bw-1))-1 if bw else 0)
                        q.append(val);qout.append(val)
                else:raise ValueError('reserved subframe type')
                for val in q:
                    if bw and not (-(1<<(bw-1))<=val<(1<<(bw-1))):raise ValueError('invalid q')
                    if not bw and val:raise ValueError('zero width nonzero')
                bl.extend(q)
            blocks.append({'bits':bw,'scale':scale,'q':bl});pos+=count
    if r.o!=len(data):raise ValueError(f'undecoded tail r.o={r.o} size={len(data)}')
    return frames,blocks,qout

def cli():
    ap=argparse.ArgumentParser();ap.add_argument('src');ap.add_argument('dest');ap.add_argument('--snr',type=float,default=float('inf'))
    ap.add_argument('--report');args=ap.parse_args()
    doc=unpack(Path(args.src).read_bytes());encoded,stats,chunks,q=encode(doc,args.snr)
    frames,blocks,qback=decode(encoded)
    assert q==qback
    for f1,f2 in zip(doc['frames'],frames):
        if f1[0]==5:
            assert absolute_lsf10(f1[1:])==absolute_lsf10(f2[1:])
        else:assert f1==f2
    assert [(x['bits'],x['scale']) for x in doc['blocks']]==[(x['bits'],x['scale']) for x in blocks]
    Path(args.dest).write_bytes(encoded)
    if args.report:Path(args.report).write_text(json.dumps({'stats':stats,'chunks':chunks},ensure_ascii=False,indent=2))
    print(json.dumps(stats,ensure_ascii=False))
if __name__=='__main__':cli()

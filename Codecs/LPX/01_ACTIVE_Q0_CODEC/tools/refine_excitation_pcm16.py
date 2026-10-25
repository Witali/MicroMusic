#!/usr/bin/env python3
"""Fixed-rate analysis-by-synthesis of LPX4 residual excitation.

Tests alternate *equal-length* codewords in existing L4HY v2 streams using
THE ORIGINAL C++ LPC decoder. Header, bitstream length, MCU code & read-bit
complexity are unchanged. The rate-constrained search is entirely offline.
"""
from __future__ import annotations
import argparse, hashlib, json, math, time
from dataclasses import dataclass
from pathlib import Path
import numpy as np
from lpx4 import BitReader, HUFF3, HUFF3_DECODE, signed_from_z, decode
from rice_v4_reference import read_scale
from refine_lsf_pcm16 import patch_bits
from batch_decoder import BatchSession
from tune_pcm16 import read_wav16,metrics


def mapped(v):return 2*v if v>=0 else -2*v-1

@dataclass
class Token:
    sample:int
    offset:int
    width:int
    code_type:str
    k:int
    b:int
    original:int
    current:int
    quotient:int=0
    def possible(self,max_diff=2):
        """[(new quantized residue, (offset,width,replacement bitfield))]."""
        old=self.current
        if self.code_type=='rice':
            z0=mapped(old);q=z0>>self.k
            lo=q<<self.k;hi=((q+1)<<self.k)-1
            candidates=range(lo,hi+1)
            vals=[signed_from_z(z) for z in candidates]
            return [(v,(self.offset,self.width,mapped(v)&((1<<self.k)-1)))
                    for v in vals if v!=old and abs(v-old)<=max_diff and -(1<<(self.b-1))<=v<(1<<(self.b-1))]
        if self.code_type=='raw':
            lo,hi=-(1<<(self.b-1)),(1<<(self.b-1))-1
            return [(v,(self.offset,self.width,v+(1<<(self.b-1))))
                    for v in range(max(lo,old-max_diff),min(hi,old+max_diff)+1) if v!=old]
        if self.code_type=='byte':
            return [(v,(self.offset,self.width,v&255))
                    for v in range(max(-128,old-max_diff),min(127,old+max_diff)+1) if v!=old]
        if self.code_type=='huff':
            ans=[]
            for v,s in HUFF3.items():
                if v==old or abs(v-old)>max_diff or len(s)!=self.width:continue
                encoded=sum((ord(bit)-48)<<i for i,bit in enumerate(s))
                ans.append((v,(self.offset,self.width,encoded)))
            return ans
        return []


def scan_tokens(blob):
    if blob[:6]!=b'L4HY\x02\x03':raise ValueError('Expected LPX4 L4HY v2')
    n=int.from_bytes(blob[8:12],'little');r=BitReader(blob,20);pos=0;scale=0
    tokens=[]
    def here():return r.o*8-r.n
    while pos<n:
        # LPC frame
        if r.get(1):
            if r.get(1)==0:
                for _ in range(10):r.get(8);r.get(2)
            else:
                raw=r.get(1)
                for _ in range(10):
                    if raw:r.get(8)
                    else:
                        from lpx4 import getplane
                        getplane(r)
        for _ in range(2):
            if pos>=n:break
            b=r.get(3);scale=read_scale(r,scale)
            count=min(80,n-pos)
            for start in range(0,count,40):
                chunk=min(40,count-start);typ=r.get(2)
                if typ==0:
                    k=r.get(3)
                    for i in range(chunk):
                        at=here()
                        if b==0:continue
                        if k==0:
                            v=r.get(b)-(1<<(b-1))
                            tokens.append(Token(pos+start+i,at,b,'raw',k,b,v,v))
                        elif k==7:
                            s=''
                            while s not in HUFF3_DECODE:
                                s+=str(r.get(1))
                                if len(s)>5:raise ValueError('Bad Huffman code')
                            v=HUFF3_DECODE[s]
                            tokens.append(Token(pos+start+i,at,len(s),'huff',k,b,v,v))
                        else:
                            q=0
                            while r.get(1)==0:
                                q+=1
                                if q>8:raise ValueError('Long unary')
                            rem_at=here();rem=r.get(k)
                            v=signed_from_z((q<<k)|rem)
                            tokens.append(Token(pos+start+i,rem_at,k,'rice',k,b,v,v,q))
                elif typ in (1,2):
                    r.get(7);r.get(5)
                    if typ==1:
                        k=r.get(3)
                        for i in range(chunk):
                            at=here()
                            if k==7:
                                u=r.get(8);v=u-256 if u>=128 else u
                                tokens.append(Token(pos+start+i,at,8,'byte',k,b,v,v))
                            else:
                                q=0
                                while r.get(1)==0:
                                    q+=1
                                    if q>8:raise ValueError('Long unary')
                                rem_at=here()
                                rem=r.get(k) if k else 0
                                v=signed_from_z((q<<k)|rem)
                                if k>0:
                                    tokens.append(Token(pos+start+i,rem_at,k,'rice',k,8,v,v,q))
                    else:
                        pulses=r.get(4)
                        for _ in range(pulses):r.get(6);r.get(5)
                else:raise ValueError('Invalid subframe')
            pos+=count
    assert r.o==len(blob),(r.o,len(blob))
    return tokens


def optimize(blob:bytes,ref:np.ndarray,batch:BatchSession,max_trials=2500,
             per_40=6,max_delta=2,passes=1,stoi_drop=0.0001,min_sse=0.005):
    t0=time.perf_counter()
    tokens=scan_tokens(blob)
    samples=len(ref)
    baseline=batch.decode_one_s16(blob,samples)
    if baseline is None:raise RuntimeError('Bad baseline C++ decode')
    bmet=metrics(ref,baseline)
    goal=bmet['stoi_pcm16']-stoi_drop
    err=(ref.astype(np.float64)-baseline.astype(np.float64))**2
    rank=[]
    for start in range(0,samples,40):
        # Pick positions with greatest local waveform error, optionally preceding
        # sample to let LPC impulse response account for delayed effect.
        high=np.argsort(err[start:start+40])[::-1][:max(per_40*2,10)]
        selected=set()
        for ix in high:
            for shift in (0,-1):
                ii=start+int(ix)+shift
                if start<=ii<min(samples,start+40):selected.add(ii)
                if len(selected)>=per_40:break
            if len(selected)>=per_40:break
        rank.extend(selected)
    tokmap={t.sample:t for t in tokens}
    ordered=[tokmap[i] for i in rank if i in tokmap]
    cur=blob;curpcm=baseline;cur_sse=float(np.sum((ref.astype(np.float64)-baseline.astype(np.float64))**2))
    accepted=[];trials=0;batches=0
    for pass_idx in range(passes):
        for tok in ordered:
            options=tok.possible(max_delta)
            if not options:continue
            remain=max_trials-trials
            if remain<=0:break
            options=options[:remain]
            blobs=[patch_bits(cur,*o[1]) for o in options]
            candidates=batch.decode_many_s16(blobs,samples)
            batches+=1;trials+=len(blobs)
            choices=[]
            for (value,patch),newblob,pcm in zip(options,blobs,candidates):
                if pcm is None:continue
                diff=ref.astype(np.float64)-pcm.astype(np.float64)
                sse=float(np.dot(diff,diff))
                if sse<cur_sse-min_sse:
                    choices.append((sse,value,newblob,pcm))
            for sse,value,newblob,pcm in sorted(choices,key=lambda x:x[0]):
                quality=metrics(ref,pcm)
                if quality['stoi_pcm16']+1e-12>=goal:
                    accepted.append(dict(pass_idx=pass_idx,sample=tok.sample,
                                         from_value=tok.current,to_value=value,
                                         sse_after=sse,stoi_after=quality['stoi_pcm16']))
                    cur=newblob;curpcm=pcm;cur_sse=sse;tok.current=value
                    break
        if trials>=max_trials:break
    new=metrics(ref,curpcm)
    assert len(cur)==len(blob)
    assert new['pcm16_snr_db']>=bmet['pcm16_snr_db']-1e-10
    assert new['stoi_pcm16']>=goal-1e-12
    return cur,curpcm,{'before':bmet,'after':new,'size_bytes':len(cur),
          'total_tokens':len(tokens),'optimized_tokens':len(ordered),
          'trials':trials,'batches':batches,'accepted':len(accepted),
          'changes':accepted,'time_seconds':time.perf_counter()-t0,
          'original_hash':hashlib.sha256(blob).hexdigest(),
          'new_hash':hashlib.sha256(cur).hexdigest(),
          'decoder_unchanged':True,'stream_length_unchanged':True}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('input',type=Path);ap.add_argument('reference_wav',type=Path);ap.add_argument('output',type=Path)
    ap.add_argument('--max-trials',type=int,default=2500)
    ap.add_argument('--per-40',type=int,default=6)
    ap.add_argument('--max-delta',type=int,default=2)
    ap.add_argument('--passes',type=int,default=1)
    ap.add_argument('--max-stoi-drop',type=float,default=0.0001)
    a=ap.parse_args()
    ref=read_wav16(a.reference_wav)
    with BatchSession('batch') as batch:
        b,pcm,report=optimize(a.input.read_bytes(),ref,batch,max_trials=a.max_trials,
                              per_40=a.per_40,max_delta=a.max_delta,passes=a.passes,
                              stoi_drop=a.max_stoi_drop)
    a.output.parent.mkdir(exist_ok=True,parents=True)
    a.output.write_bytes(b)
    a.output.with_suffix('.pcm16le').write_bytes(pcm.astype('<i2').tobytes())
    a.output.with_suffix('.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='changes'},ensure_ascii=False,indent=2))
if __name__=='__main__':main()

"""Encoder-only perceptually weighted native analysis-by-synthesis.

The original direct/Rice/pitch/sparse codewords keep their bit lengths.
W(z)=A(z/gamma1)/A(z/gamma2) weights error only on the host. Candidate
selection explicitly guards whole-clip STOI, waveform energy and peak error.
No human listening result or new MCU work is implied.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,time
import numpy as np
from numba import njit
from lpx4 import decode,BitReader,BitWriter,get_rice,HUFF3_DECODE,signed_from_z
from rice_v4_reference import read_scale,write_scale
from lossless_repack import copy_bits,layout
from refine_excitation_pcm16 import scan_tokens
from refine_lsf_pcm16 import patch_bits
from q0_model import coefficient_trace,decode_pcm16
from wav_to_lpx4 import quality


@njit(cache=True)
def weight_error(error,co,gamma1=.9,gamma2=.6):
    """Time-varying LPC weighting; state starts at zero, no block resets."""
    e=np.zeros(10,np.float64);w=np.zeros(10,np.float64);out=np.empty(len(error),np.float64)
    for n in range(len(error)):
        value=float(error[n]);g1=gamma1;g2=gamma2
        for k in range(10):
            a=co[n,k]/4096.;value+=a*(g1*e[k]-g2*w[k]);g1*=gamma1;g2*=gamma2
        for k in range(9,0,-1):e[k]=e[k-1];w[k]=w[k-1]
        e[0]=error[n];w[0]=value;out[n]=value
    return out


def expanded_v2(blob):
    """Expand only established compact24 headers, copying every payload bit.

    Do not choose new coding modes when preparing equal-width native search.
    Inverse packing must reproduce compact24 exactly, including sparse mode.
    """
    if blob[:6]==b'L4HY\x02\x03':return blob
    if blob[:6]!=b'L4HY\x03\x1b':raise ValueError('Expected existing v2 or compact24')
    frames,blocks,_=decode(blob);r=BitReader(blob,20);w=BitWriter();width=0;scale=0;old=(0,0,0,0)
    here=lambda:r.o*8-r.n
    for bi,block in enumerate(blocks):
        if bi%2==0:
            begin=here()
            if r.get(1):
                if not r.get(1):
                    for _ in range(10):r.get(8);r.get(2)
                else:
                    raw=r.get(1)
                    for _ in range(10):
                        if raw:r.get(8)
                        else:
                            from lpx4 import getplane
                            getplane(r)
            copy_bits(w,blob,begin,here())
        if r.get(1):width=r.get(3)
        w.put(width,3);previous=scale;scale=read_scale(r,scale);write_scale(w,previous,scale)
        for start in range(0,len(block['q']),40):
            n=min(40,len(block['q'])-start)
            if r.get(1):
                typ=r.get(2)
                if typ==0:mode=(typ,0,0,r.get(3))
                elif typ in (1,2):mode=(typ,r.get(7),r.get(5),r.get(3) if typ==1 else 0)
                else:raise ValueError('Invalid compact24 mode')
                old=mode
            else:mode=old
            typ,lag,gain,k=mode;w.put(typ,2)
            if typ:w.put(lag,7);w.put(gain,5)
            if typ!=2:w.put(k,3)
            else:
                count=r.get(4);w.put(count,4)
            begin=here()
            if typ==2:
                for _ in range(count):r.get(6);r.get(5)
            else:
                for _ in range(n):
                    if typ==0 and k==0:
                        if width:r.get(width)
                    elif typ==0 and k==7:
                        word=''
                        while word not in HUFF3_DECODE:word+=str(r.get(1))
                    elif typ==1 and k==7:r.get(8)
                    else:get_rice(r,k)
            copy_bits(w,blob,begin,here())
    w.aligned();header=bytearray(blob[:20]);header[:6]=b'L4HY\x02\x03';result=bytes(header)+w.get()
    from compact_format import pack
    if pack(result,24)[0]!=blob:raise AssertionError('Compact24 inverse does not preserve coding payload')
    return result


@dataclass
class SparseToken:
    sample:int
    offset:int
    current:int
    def possible(self,max_diff=2):
        return [(v,(self.offset,5,2*v if v>=0 else -2*v-1))
                for v in range(max(-16,self.current-max_diff),min(15,self.current+max_diff)+1)
                if v!=self.current]


def all_tokens(blob):
    result=scan_tokens(blob);_,blocks,_,spans=layout(blob)
    for bi,(block,span) in enumerate(zip(blocks,spans)):
        for ci,chunk in enumerate(span.chunks):
            if chunk.mode[0]!='sparse':continue
            r=BitReader(blob,chunk.payload//8)
            if chunk.payload%8:r.get(chunk.payload%8)
            for _ in range(chunk.mode[3]):
                position=r.get(6);at=r.o*8-r.n;v=signed_from_z(r.get(5))
                result.append(SparseToken(bi*80+ci*40+position,at,v))
    return result


def refine_perceptual(blob,reference,decoder,max_trials=256,beam=4,max_windows=8,gamma1=.9,gamma2=.6,
                      peak_growth=.10,max_ser_drop_db=3.,kind='speech'):
    ref=np.asarray(reference)
    if (ref.ndim!=1 or ref.dtype.kind not in 'iu' or not 1<=len(ref)<=64000 or
            np.any(ref < -32768) or np.any(ref >32767) or not 0<=max_trials<=10000 or
            beam not in (1,4,8) or not 1<=max_windows<=64 or not 0<gamma2<gamma1<1 or
            not 0<=peak_growth<=.25 or not 0<=max_ser_drop_db<=3 or kind not in ('speech','music')):
        raise ValueError('Invalid weighted native search settings')
    start=time.perf_counter();v2=expanded_v2(blob);frames,_,q=decode(v2)
    if len(q)!=len(ref):raise ValueError('Reference length mismatch')
    base=decoder.decode_one_s16(blob,len(ref));pcm=decoder.decode_one_s16(v2,len(ref))
    if base is None or not np.array_equal(base,pcm):raise AssertionError('Expanded native PCM mismatch')
    co=coefficient_trace(frames,len(ref));target=ref.astype(np.float64);before=quality(ref,base,kind)
    def measure(p):
        error=p.astype(np.float64)-target;weighted=weight_error(error,co,gamma1,gamma2)
        return float(np.dot(weighted,weighted)),float(np.dot(error,error)),int(np.max(np.abs(error))),weighted
    initial=measure(pcm);best=initial[0];cur=v2;trials=0;changes=[]
    peak_limit=max(initial[2]*(1+peak_growth),initial[2]+256)
    error_limit=initial[1]*10**(max_ser_drop_db/10)
    tokens=all_tokens(v2);windows=sorted(range(0,len(ref),40),key=lambda s:(-float(np.dot(initial[3][s:s+40],initial[3][s:s+40])),s))[:max_windows]
    for window in windows:
        if trials>=max_trials or not best:break
        eligible=[t for t in tokens if window<=t.sample<window+40]
        eligible=sorted(sorted(eligible,key=lambda t:(-initial[3][t.sample]**2,t.sample))[:3],key=lambda t:t.sample)
        states=[(cur,pcm,best)]
        for tok in eligible:
            proposals=[];seen={s[0] for s in states}
            for data,_,_ in states:
                for _,patch in tok.possible(2):
                    candidate=patch_bits(data,*patch)
                    if candidate not in seen:seen.add(candidate);proposals.append(candidate)
            proposals=proposals[:max_trials-trials]
            if not proposals:break
            outputs=decoder.decode_many_s16(proposals,len(ref));trials+=len(proposals)
            for data,p in zip(proposals,outputs):
                if p is None:continue
                score,sse,peak,_=measure(p)
                if score<best and sse<=error_limit+1e-9 and peak<=peak_limit:
                    states.append((data,p,score))
            states=sorted(states,key=lambda s:(s[2],s[0]))[:beam]
        for data,p,score in states:
            if score>=best:continue
            met=quality(ref,p,kind)
            if before['stoi'] is not None and met['stoi']<before['stoi']-1e-12:continue
            changes.append({'window_sample':window,'weighted_sse_before':best,'weighted_sse_after':score})
            cur,pcm,best=data,p,score;break
    from compact_format import pack
    if blob[4]==3:out=pack(cur,24)[0]
    else:out=cur
    if len(out)!=len(blob):raise AssertionError('Equal-width perceptual search changed file length')
    native=decoder.decode_one_s16(out,len(ref))
    if native is None or not np.array_equal(native,pcm) or not np.array_equal(native,decode_pcm16(out)):
        raise AssertionError('Weighted output/model/native mismatch')
    final=measure(native)
    return out,native,{'before':before,'after':quality(ref,native,kind),'gamma1':gamma1,'gamma2':gamma2,
        'weighted_sse_before':initial[0],'weighted_sse_after':final[0],'trials':trials,'changes':changes,
        'input_bytes':len(blob),'output_bytes':len(out),'max_error_before':initial[2],'max_error_after':final[2],
        'peak_limit':peak_limit,'sse_limit':error_limit,'max_ser_drop_db':max_ser_drop_db,
        'stream_sha256':hashlib.sha256(out).hexdigest(),'native_model_pcm_exact':True,
        'decoder_modified':False,'avr_cycles_measured':False,'seconds':time.perf_counter()-start}

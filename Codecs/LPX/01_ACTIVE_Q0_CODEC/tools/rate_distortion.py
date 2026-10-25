"""Encoder-only rate/distortion quantization for existing LPX Q0 syntax.

LSF frames, fixed-point synthesis, decoder tables and MCU code stay unchanged.
The sequential block choice uses actual existing v2 coding costs, including
Rice/pitch headers and scale deltas, instead of nominal source bit depth.
Final serialization decides actual bytes; compact24 is an optional existing
representation of the same PCM. No real-time claim follows from host costs.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from numba import njit
import soundfile as sf
from fast_lpx4 import _pitch_scores, _evaluate_exact
from lpx4 import decode, BitWriter, put_chunk, HUFF3
from rice_v4_reference import write_scale, plane_cost, putplane
from rice_v7 import absolute_lsf10
from q0_model import coefficient_trace, table, decode_pcm16
from wav_to_lpx4 import quantize_trial, quality
from batch_decoder import BatchSession
from output_paths import protect_outputs

HUFF_LENGTHS=np.asarray([len(HUFF3[i]) for i in range(-4,4)],np.int64)


@njit(cache=True)
def scale_bits(previous,value):
    delta=value-previous;z=2*delta if delta>=0 else -2*delta-1
    quotient=z>>4
    return quotient+5 if quotient<6 else 14


@njit(cache=True)
def chunk_mode(q,history,bits):
    """Exact length of the selected reversible direct/pitch code, not all modes."""
    best=len(q)*bits;kbest=0
    if bits:
        for k in range(1,7):
            cost=0;valid=True
            for value in q:
                z=2*value if value>=0 else -2*value-1
                quotient=z>>k
                if quotient>8:valid=False;break
                cost+=quotient+1+k
            if valid and cost<best:best=cost;kbest=k
        if bits==3:
            cost=0
            for value in q:cost+=HUFF_LENGTHS[value+4]
            if cost<best:best=cost;kbest=7
    if not bits:return 5,0,0,0,0
    scores,gains=_pitch_scores(q,history)
    # Keep the eight best correlations, breaking ties by increasing lag.
    chosen=np.zeros(128,np.uint8);params=np.empty((24,2),np.int32);count=0
    for _ in range(8):
        at=-1;score=np.int64(0x7fffffffffffffff)
        for i in range(128):
            if not chosen[i] and gains[i]>1 and scores[i]<score:at=i;score=scores[i]
        if at<0:break
        chosen[at]=1
        for d in range(-1,2):
            params[count,0]=at+18;params[count,1]=max(0,min(31,gains[at]+d));count+=1
    if count:
        cost,lag,gain,k=_evaluate_exact(q,history,params[:count],bits,best)
        if lag>=0:return cost,1,lag,gain,k
    return best+5,0,0,0,kbest


@njit(cache=True)
def advance_history(history,q):
    result=history.copy()
    for value in q:
        result[:-1]=result[1:];result[-1]=value
    return result


@njit(cache=True)
def block_bits(q,bits,scale,previous_scale,history):
    cost=3+scale_bits(previous_scale,scale);h=history.copy()
    for start in range(0,len(q),40):
        chunk=q[start:start+40]
        cost+=chunk_mode(chunk,h,bits)[0];h=advance_history(h,chunk)
    return cost


@njit(cache=True)
def residual_rms(pcm,co,pre):
    x=pcm.astype(np.float64)/2;xp=x.copy();result=np.empty((len(pcm)+79)//80,np.float64)
    for i in range(1,len(x)):xp[i]-=(pre*int(np.rint(x[i-1])))>>14
    for bi in range(len(result)):
        power=0.;start=bi*80;end=min(start+80,len(x))
        for j in range(start,end):
            v=xp[j]
            for k in range(10):
                if j>k:v+=(co[j,k]*int(np.rint(xp[j-k-1])))>>12
            power+=v*v
        result[bi]=max(1.,np.sqrt(power/(end-start)))
    return result


@njit(cache=True)
def alias_scale(index,previous,steps):
    best=index;cost=scale_bits(previous,index)
    for i in range(256):
        if steps[i]==steps[index]:
            n=scale_bits(previous,i)
            if n<cost or n==cost and i<best:cost=n;best=i
    return best


@njit(cache=True)
def quantize_rate(pcm,co,steps,pre,bright,lam,allow_zero=False):
    history=np.zeros(10,np.int64);deemph=clipped=0;qh=np.zeros(145,np.int64)
    all_q=np.empty(len(pcm),np.int64);scales=np.empty((len(pcm)+79)//80,np.int64)
    widths=np.empty(len(scales),np.int64);rms=residual_rms(pcm,co,pre)
    previous_scale=0;total_bits=0;total_loss=0.
    for bi in range(len(scales)):
        start=bi*80;end=min(len(pcm),start+80);target=pcm[start:end]
        energy=max((.025*32768)**2,np.mean(target.astype(np.float64)**2))
        best=float('inf');best_scale=best_width=0
        first=0 if allow_zero else 2
        for bits in range(first,7):
            if bits==1:continue
            seen=np.zeros(256,np.uint8)
            for multiplier in (.3,.5,.75,1.,1.3,1.85,2.9,5.,7.):
                if bits:
                    nominal=rms[bi]/((1<<(bits-1))-.5)
                    scale=min(255,max(0,int(np.rint(128+16*np.log2(max(1.,nominal*multiplier)/16.384)))))
                    scale=alias_scale(scale,previous_scale,steps)
                else:scale=previous_scale
                if seen[scale]:continue
                seen[scale]=1
                q,loss,_,_,_=quantize_trial(target,co[start:end],history,deemph,clipped,pre,bright,int(steps[scale]),bits)
                cost=block_bits(q,bits,scale,previous_scale,qh)
                objective=loss/energy+lam*cost
                if objective<best:
                    best=objective;best_scale=scale;best_width=bits
        q,loss,history,deemph,clipped=quantize_trial(target,co[start:end],history,deemph,clipped,pre,bright,int(steps[best_scale]),best_width)
        total_bits+=block_bits(q,best_width,best_scale,previous_scale,qh);total_loss+=loss
        all_q[start:end]=q;scales[bi]=best_scale;widths[bi]=best_width
        previous_scale=best_scale;qh=advance_history(qh,q)
    return all_q,scales,widths,total_bits,total_loss


def serialize(header,frames,q,scales,widths,compact_features=0):
    """Write exactly the coding policy used in block_bits, with zero initial q."""
    writer=BitWriter();previous_scale=0;qh=np.zeros(145,np.int64);history=[]
    for bi,(scale,bits) in enumerate(zip(scales,widths)):
        if bi%2==0:
            frame=frames[bi//2];tag=frame[0]
            if tag==0:writer.put(0,1)
            elif tag==5:
                writer.put(1,1);writer.put(0,1)
                for v in absolute_lsf10(frame[1:]):writer.put(v&255,8);writer.put(v>>8,2)
            elif tag==6:
                writer.put(1,1);writer.put(1,1);raw=80<=plane_cost(frame[1:]);writer.put(int(raw),1)
                for v in frame[1:]:
                    if raw:writer.put(v,8)
                    else:putplane(writer,v)
            else:raise ValueError('Unsupported Q0 LSF tag')
        writer.put(int(bits),3);write_scale(writer,previous_scale,int(scale));previous_scale=int(scale)
        block=q[bi*80:min(bi*80+80,len(q))]
        for start in range(0,len(block),40):
            chunk=block[start:start+40];_,typ,lag,gain,k=chunk_mode(chunk,qh,int(bits))
            mode=('direct',int(k)) if typ==0 else ('exact',int(lag),int(gain),int(k))
            put_chunk(writer,chunk.tolist(),history,int(bits),mode)
            qh=advance_history(qh,chunk);history.extend(map(int,chunk))
    payload_bits=writer.total;writer.aligned();head=bytearray(header[:20]);head[:6]=b'L4HY\x02\x03'
    blob=bytes(head)+writer.get()
    if compact_features:
        if compact_features!=24:raise ValueError('Only the established compact24 profile is supported')
        from compact_format import pack
        other,_=pack(blob,24)
        if len(other)<len(blob):blob=other
    return blob,payload_bits


def encode_rate(seed,reference,decoder,lam=0.,allow_zero=False,compact_features=0,kind='speech'):
    ref=np.asarray(reference)
    if (ref.ndim!=1 or ref.dtype.kind not in 'iu' or not 1<=len(ref)<=64000 or
            np.any(ref < -32768) or np.any(ref > 32767) or not np.isfinite(lam) or lam<0 or
            compact_features not in (0,24) or kind not in ('speech','music')):
        raise ValueError('Expected PCM16 reference, finite nonnegative lambda and an existing profile')
    frames,_,original=decode(seed)
    if len(original)!=len(ref):raise ValueError('Seed/reference sample count mismatch')
    started=time.perf_counter();ref=ref.astype(np.int64)
    co=coefficient_trace(frames,len(ref));steps=table('scale_table.inc')
    pre=int.from_bytes(seed[12:14],'little');bright=int.from_bytes(seed[14:16],'little')
    q,scales,widths,cost,loss=quantize_rate(ref,co,steps,pre,bright,float(lam),bool(allow_zero))
    blob,payload_bits=serialize(seed[:20],frames,q,scales,widths,compact_features)
    frame_bits=sum(1 if f[0]==0 else 102 if f[0]==5 else 3+min(80,plane_cost(f[1:])) for f in frames)
    if payload_bits!=frame_bits+cost:raise AssertionError('Selected v2 costs disagree with written bits')
    if len(blob)>65535:raise ValueError('Encoded segment exceeds the existing 16-bit API')
    pcm=decoder.decode_one_s16(blob,len(ref))
    if pcm is None or not np.array_equal(pcm,decode_pcm16(blob)):
        raise AssertionError('Independent model/native mismatch')
    error=ref-pcm.astype(np.int64)
    if float(np.dot(error,error))!=loss:raise AssertionError('Quantizer/native state mismatch')
    return blob,pcm,{'lambda':lam,'allow_zero':bool(allow_zero),'compact_features':compact_features,
        'v2_payload_bits':payload_bits,'local_cost_exact_for_selected_v2_codes':True,
        'audio_packet_bytes':len(blob)-20,'file_bytes':len(blob),'quality':quality(ref,pcm,kind),
        'native_model_pcm_exact':True,'stream_sha256':hashlib.sha256(blob).hexdigest(),
        'width_counts':{str(b):int(np.count_nonzero(widths==b)) for b in (0,2,3,4,5,6)},
        'seconds':time.perf_counter()-started,'decoder_modified':False,'avr_cycles_measured':False}


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('seed',type=Path);ap.add_argument('reference',type=Path);ap.add_argument('output',type=Path)
    ap.add_argument('--lambda',dest='lam',type=float,default=.003)
    ap.add_argument('--allow-zero',action='store_true');ap.add_argument('--compact-features',type=int,choices=(0,24),default=0)
    ap.add_argument('--kind',choices=('speech','music'),default='speech');a=ap.parse_args()
    protect_outputs([a.seed,a.reference],[a.output,a.output.with_suffix('.wav'),a.output.with_suffix('.json')])
    ref,rate=sf.read(a.reference,dtype='int16')
    if rate!=8000 or ref.ndim!=1:raise ValueError('Reference must be mono PCM16 8kHz')
    with BatchSession('batch',v3_features=a.compact_features) as decoder:
        blob,pcm,report=encode_rate(a.seed.read_bytes(),ref,decoder,a.lam,a.allow_zero,a.compact_features,a.kind)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(blob)
    sf.write(a.output.with_suffix('.wav'),pcm,8000,subtype='PCM_16')
    a.output.with_suffix('.json').write_bytes((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode())

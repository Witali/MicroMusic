"""Delayed rate/distortion decisions in existing direct/pitch/sparse modes.

Only the offline encoder searches. The original decoder still reconstructs
the same scalar q, scale, lag/gain and at most ten sparse innovations.
"""
from __future__ import annotations
import hashlib,time
import numpy as np
from numba import njit
from rate_distortion import chunk_mode,block_bits,scale_bits,advance_history,alias_scale,serialize,HUFF_LENGTHS
from fast_lpx4 import _pitch_scores
from q0_model import clamp,coefficient_trace,table,decode_pcm16
from wav_to_lpx4 import quantize_trial,quality
from lpx4 import decode
from level_policy import DEFAULT_LEVEL_FLOOR_DB, relative_energy_floor


@njit(cache=True)
def trellis(target,co,history,deemph,clip,pre,bright,step,bits,qhistory,mode,lam,energy,beam):
    """Keep rounding alternatives through a complete <=40-sample subframe."""
    n=len(target);typ,lag,gain,k=mode
    hs=np.zeros((beam,10),np.int64);hs[0]=history
    ds=np.zeros(beam,np.int64);ds[0]=deemph;cs=np.zeros(beam,np.int64);cs[0]=clip
    codes=np.zeros((beam,n),np.int64);scores=np.full(beam,np.inf);scores[0]=0.
    pulse_counts=np.zeros(beam,np.int64);rates=np.zeros(beam,np.int64);losses=np.zeros(beam)
    count=1;lo=-(1<<(bits-1)) if bits else 0;hi=(1<<(bits-1))-1 if bits else 0
    for j in range(n):
        maximum=beam*6
        nh=np.empty((maximum,10),np.int64);nd=np.empty(maximum,np.int64);nc=np.empty(maximum,np.int64)
        nq=np.empty((maximum,n),np.int64);ns=np.full(maximum,np.inf);npulses=np.empty(maximum,np.int64)
        nr=np.empty(maximum,np.int64);nl=np.empty(maximum);used=0
        for path in range(count):
            acc=0
            for t in range(10):acc+=(co[j,t]*hs[path,t])>>12
            preterm=(pre*ds[path])>>14;postterm=(bright*cs[path])>>14
            needed=target[j]/2+postterm-preterm+acc
            center=int(np.floor(needed/step+.5)) if bits else 0
            predicted=0
            if typ:
                x=qhistory[145-lag+j] if j<lag else codes[path,j-lag]
                predicted=min(hi,max(lo,(gain*x+8)>>4)) if bits else 0
            candidates=np.asarray([center,center-1,center+1,0,predicted,predicted+1],np.int64)
            seen=np.empty(6,np.int64);seen_count=0
            for value in candidates:
                q=min(hi,max(lo,value))
                duplicate=False
                for z in range(seen_count):
                    if seen[z]==q:duplicate=True;break
                if duplicate:continue
                seen[seen_count]=q;seen_count+=1
                delta=q-predicted if typ else q;increment=0;pc=pulse_counts[path]
                if typ==2:
                    if delta < -16 or delta >15:continue
                    if delta:pc+=1;increment=11
                    if pc>10:continue
                elif not typ and k==0:increment=bits
                elif not typ and k==7:increment=HUFF_LENGTHS[q+4]
                else:
                    z=2*delta if delta>=0 else -2*delta-1;quotient=z>>k
                    if quotient>8:continue
                    increment=quotient+1+k
                pred=clamp(q*step-acc);dd=clamp(pred+preterm);cc=clamp(dd,-16384,16384)
                out=clamp(clamp(cc-postterm,-16384,16384)*2,-32768,32767)
                error=float(out-target[j])**2;loss=losses[path]+error;rate=rates[path]+increment
                ns[used]=loss/energy+lam*rate;nl[used]=loss;nr[used]=rate;npulses[used]=pc
                nh[used,0]=pred
                for t in range(1,10):nh[used,t]=hs[path,t-1]
                nd[used]=dd;nc[used]=cc;nq[used]=codes[path];nq[used,j]=q;used+=1
        count=min(beam,used)
        if not count:return np.zeros(n,np.int64),history,deemph,clip,np.inf,0,False
        # Selection sort is deterministic and avoids full O(N log N) arrays.
        for path in range(count):
            at=int(np.argmin(ns[:used]));scores[path]=ns[at];ns[at]=np.inf
            hs[path]=nh[at];ds[path]=nd[at];cs[path]=nc[at];codes[path]=nq[at]
            losses[path]=nl[at];rates[path]=nr[at];pulse_counts[path]=npulses[at]
    return codes[0],hs[0],ds[0],cs[0],losses[0],rates[0],True


@njit(cache=True)
def pitch_parameters(q,qh,bits):
    scores,gains=_pitch_scores(q,qh);at=-1;score=np.int64(0x7fffffffffffffff)
    for i in range(128):
        if gains[i]>1 and scores[i]<score:score=scores[i];at=i
    return (at+18,int(gains[at])) if at>=0 else (18,0)


@njit(cache=True)
def quantize_joint(ref,co,steps,pre,bright,lam,seed_scales,seed_widths,beam,allow_zero,level_floor_db=DEFAULT_LEVEL_FLOOR_DB):
    allq=np.empty(len(ref),np.int64);scales=np.empty(len(seed_scales),np.int64);widths=np.empty_like(scales)
    hints=np.empty(((len(ref)+39)//40,4),np.int64)
    hist=np.zeros(10,np.int64);dd=cc=0;qh=np.zeros(145,np.int64);previous_scale=0
    floor=relative_energy_floor(ref,level_floor_db)
    for bi in range(len(scales)):
        start=bi*80;end=min(start+80,len(ref));target=ref[start:end]
        energy=max(floor,np.mean(target.astype(np.float64)**2));best=np.inf
        oldb=seed_widths[bi];olds=seed_scales[bi]
        for bits in (0,2,3,4,5,6):
            if bits==0 and not allow_zero:continue
            if bits and oldb and abs(bits-oldb)>1:continue
            if bits and not oldb and bits>3:continue
            if oldb and bits:center=int(olds+16*(oldb-bits))
            elif bits:
                rms=max(1.,np.sqrt(np.mean(target.astype(np.float64)**2))/2)
                center=int(np.rint(128+16*np.log2(max(1.,rms/((1<<(bits-1))-.5))/16.384)))
            else:center=int(olds)
            used_scales=np.zeros(256,np.uint8)
            for offset in (-8,0,8):
                scale=alias_scale(min(255,max(0,center+offset)),previous_scale,steps) if bits else previous_scale
                if used_scales[scale] or bits and not steps[scale]:continue
                used_scales[scale]=1
                hh=hist.copy();d=dd;c=cc;h=qh.copy();q=np.empty(len(target),np.int64)
                modes=np.zeros((2,4),np.int64);cost=3+scale_bits(previous_scale,scale);loss=0.
                for local in range(0,len(target),40):
                    stop=min(local+40,len(target));x=target[local:stop];coeff=co[start+local:start+stop]
                    greedy,gl,gh,gd,gc=quantize_trial(x,coeff,hh,d,c,pre,bright,int(steps[scale]),bits)
                    coding,typ,lag,gain,k=chunk_mode(greedy,h,bits)
                    selected=greedy;sh=gh;sd=gd;sc=gc;sl=gl;sb=coding
                    sm=np.asarray([typ,lag,gain,k],np.int64);best_chunk=gl/energy+lam*coding
                    pl,pg=pitch_parameters(greedy,h,bits) if bits else (18,0)
                    proposals=np.asarray([[typ,lag,gain,k],[2,pl,pg,0],[2,18,0,0]],np.int64)
                    for mode in proposals:
                        if not bits and mode[0]:continue
                        # Literal pitch residual k7 is not a Rice symbol. A
                        # sparse proposal is still evaluated separately.
                        if mode[0]==1 and mode[3]==7:continue
                        candidate,th,td,tc,tl,tb,valid=trellis(x,coeff,hh,d,c,pre,bright,int(steps[scale]),bits,h,mode,lam,energy,beam)
                        header=5 if mode[0]==0 else 17 if mode[0]==1 else 18
                        objective=tl/energy+lam*(header+tb)
                        if valid and objective<best_chunk:
                            selected=candidate;sh=th;sd=td;sc=tc;sl=tl;sb=header+tb;sm=mode.copy();best_chunk=objective
                    q[local:stop]=selected;hh=sh;d=sd;c=sc;h=advance_history(h,selected)
                    loss+=sl;cost+=sb;modes[local//40]=sm
                objective=loss/energy+lam*cost
                if objective<best:
                    best=objective;bestq=q.copy();besth=hh.copy();bestd=d;bestc=c;bestqh=h.copy()
                    bestscale=scale;bestbits=bits;bestm=modes.copy()
        allq[start:end]=bestq;scales[bi]=bestscale;widths[bi]=bestbits
        hist=besth;dd=bestd;cc=bestc;qh=bestqh;previous_scale=bestscale
        for local in range(0,len(target),40):hints[(start+local)//40]=bestm[local//40]
    return allq,scales,widths,hints


def encode_joint(seed,reference,decoder,lam=.003,allow_zero=True,compact_features=24,kind='speech',beam=4,level_floor_db=DEFAULT_LEVEL_FLOOR_DB):
    if beam not in (1,4,8) or not np.isfinite(lam) or lam<0 or compact_features not in (0,24) or kind not in ('speech','music'):
        raise ValueError('Invalid existing-format joint search settings')
    ref=np.asarray(reference)
    if ref.ndim!=1 or ref.dtype.kind not in 'iu' or not 1<=len(ref)<=64000 or np.any(ref < -32768) or np.any(ref >32767):raise ValueError('Expected PCM16')
    frames,blocks,q0=decode(seed)
    if len(q0)!=len(ref):raise ValueError('Seed/reference sample count mismatch')
    start=time.perf_counter();co=coefficient_trace(frames,len(ref));steps=table('scale_table.inc')
    pre=int.from_bytes(seed[12:14],'little');bright=int.from_bytes(seed[14:16],'little')
    q,scales,widths,hints=quantize_joint(ref.astype(np.int64),co,steps,pre,bright,float(lam),
        np.asarray([b['scale'] for b in blocks],np.int64),np.asarray([b['bits'] for b in blocks],np.int64),beam,bool(allow_zero),float(level_floor_db))
    blob,bits=serialize(seed,frames,q,scales,widths,compact_features,hints)
    if len(blob)>65535:raise ValueError('Segment exceeds the existing 16-bit API')
    pcm=decoder.decode_one_s16(blob,len(ref))
    if pcm is None or not np.array_equal(pcm,decode_pcm16(blob)):raise AssertionError('Joint native/model mismatch')
    if decode(blob)[2]!=q.tolist():raise AssertionError('Joint pitch/innovation reconstruction mismatch')
    return blob,pcm,{'lambda':lam,'beam':beam,'allow_zero':allow_zero,'compact_features':compact_features,
        'level_floor_db':float(level_floor_db),'level_reference':'whole-recording RMS; soft error floor, no gate',
        'audio_packet_bytes':len(blob)-20,'file_bytes':len(blob),'v2_payload_bits':bits,
        'quality':quality(ref,pcm,kind),'native_model_pcm_exact':True,'decoder_modified':False,
        'stream_sha256':hashlib.sha256(blob).hexdigest(),'seconds':time.perf_counter()-start,
        'mode_counts':{name:int(np.count_nonzero(hints[:,0]==i)) for i,name in enumerate(('direct','pitch','sparse'))},
        'avr_cycles_measured':False}

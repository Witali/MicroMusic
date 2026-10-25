#!/usr/bin/env python3
"""Lossless-bit-budget LPX4 LSF refinement, OFFLINE ONLY.

Coordinate descent on *existing fixed-width* LPC spectral fields, while
scoring the actual unmodified integer C++ decoder output (signed PCM16).
No change to the compressed file length, bitstream syntax or AVR code.

Absolute LSF10 fields use 10 fixed bits. Raw 8-bit delta fields are included,
but variable-length LPC delta fields are kept untouched to avoid bitrate growth.
Reject any trial violating 10-bit LSF bounds or spectral ordering throughout
its prediction chain (until the next absolute frame).
"""
from __future__ import annotations
import argparse, hashlib, json, math, sys, time
from dataclasses import dataclass
from pathlib import Path
import numpy as np
from lpx4 import BitReader, get_rice, getplane, HUFF3_DECODE, decode as unpack_lpx4
from rice_v4_reference import read_scale
from rice_v7 import absolute_lsf10
from batch_decoder import BatchSession
from tune_pcm16 import read_wav16, metrics

@dataclass(frozen=True)
class Field:
    frame: int
    coeff: int
    bit_offset: int
    width: int
    stored: int  # unsigned for absolute, signed for deltas
    kind: str
    affected_end: int  # exclusive, next absolute frame
    min_change: int
    max_change: int


def patch_bits(blob:bytes, off:int, width:int, newvalue:int)->bytes:
    assert 0 <= newvalue < (1 << width)
    d = bytearray(blob)
    for j in range(width):
        idx=(off+j)//8; mask=1 << ((off+j)%8)
        if (newvalue >> j) & 1:d[idx] |=mask
        else:d[idx] &=~mask
    return bytes(d)


def read_scanned_fields(blob:bytes, minimum_gap:int=10):
    if blob[:6] != b'L4HY\x02\x03':raise ValueError('Expected L4HY v2 LSF10 stream')
    original_frames, _, original_q=unpack_lpx4(blob)
    n=int.from_bytes(blob[8:12],'little')
    frame_vectors=[];vec=np.zeros(10,dtype=np.int16)
    for f in original_frames:
        tag=f[0]
        if tag == 5:vec=np.asarray(absolute_lsf10(f[1:]),dtype=np.int16)
        elif tag == 6:vec=vec+np.asarray([int(x)-256 if x>=128 else int(x) for x in f[1:]],dtype=np.int16)
        elif tag!=0:raise ValueError('Unsupported LPC frame tag '+str(tag))
        frame_vectors.append(vec.copy())
    fields=[];rd=BitReader(blob,20);p=0;frame=0;scale=0
    def here():return rd.o*8-rd.n
    while p<n:
        is_new=rd.get(1)
        if is_new:
            is_delta=rd.get(1)
            if not is_delta:
                for j in range(10):
                    at=here();stored=rd.get(8)|(rd.get(2)<<8)
                    assert stored == int(frame_vectors[frame][j]),(frame,j,stored,frame_vectors[frame][j])
                    fields.append((frame,j,at,10,stored,'absolute'))
            else:
                raw=rd.get(1)
                for j in range(10):
                    at=here()
                    if raw:
                        b=rd.get(8);stored=b-256 if b>=128 else b
                        assert stored == int(frame_vectors[frame][j])-int(frame_vectors[frame-1][j])
                        fields.append((frame,j,at,8,stored,'delta'))
                    else:getplane(rd)
        for _ in range(2):
            if p>=n:break
            b=rd.get(3)
            scale=read_scale(rd,scale)
            count=min(n-p,80)
            for partial in range(0,count,40):
                ns=min(count-partial,40);typ=rd.get(2)
                if typ==0:
                    k=rd.get(3)
                    for i in range(ns):
                        if k==0:rd.get(b)
                        elif k==7:
                            s=''
                            while s not in HUFF3_DECODE:
                                s+=str(rd.get(1))
                                if len(s)>6:raise ValueError('corrupt Huffman')
                        else:get_rice(rd,k)
                elif typ in (1,2):
                    rd.get(7);rd.get(5)
                    if typ==1:
                        k=rd.get(3)
                        for i in range(ns):
                            if k==7:rd.get(8)
                            else:get_rice(rd,k)
                    else:
                        pulses=rd.get(4)
                        for i in range(pulses):rd.get(6);rd.get(5)
                else:raise ValueError('reserved excitation mode')
            p+=count
        frame+=1
    if frame!=len(original_frames) or rd.o!=len(blob):
        raise ValueError('Bad frame or bit length while scanning')
    timeline=np.asarray(frame_vectors,dtype=np.int32)
    if np.any(np.diff(timeline,axis=1)<minimum_gap):
        raise ValueError('Input LPC spectrum violates minimum spacing')
    result=[]
    for f,j,at,width,v,kind in fields:
        end=next((i for i in range(f+1,len(original_frames)) if original_frames[i][0]==5),len(original_frames))
        covered=timeline[f:end,:]
        # Apply candidate delta to one spectral dimension of all dependent frames.
        delta_lo=max(0-int(covered[:,j].min()),(1-minimum_gap)-1024)
        delta_hi=1023-int(covered[:,j].max())
        if j>0:delta_lo=max(delta_lo,minimum_gap-int(np.min(covered[:,j]-covered[:,j-1])))
        if j<9:delta_hi=min(delta_hi,int(np.min(covered[:,j+1]-covered[:,j]))-minimum_gap)
        if kind=='absolute':delta_lo=max(delta_lo,-v);delta_hi=min(delta_hi,1023-v)
        else:delta_lo=max(delta_lo,-128-v);delta_hi=min(delta_hi,127-v)
        result.append(Field(f,j,at,width,v,kind,end,int(delta_lo),int(delta_hi)))
    return result,timeline


def optimize(blob:bytes,ref:np.ndarray,batch:BatchSession,step_sizes=(16,8,4,2,1),
             max_trials=2400,passes=1, min_stoi_delta=-0.00003,
             max_cost_increase=0.0, min_sse_improvement=0.005,
             allow_delta=True):
    """Deterministic, bit-budget locked search with a global STOI acceptance gate.

    Score every candidate by PCM16 MSE of the *complete* C++ decoded waveform.
    Accept only changes that reduce error and respect the original STOI floor.
    The select/decoder paths remain unchanged on the AVR.
    """
    start=time.perf_counter()
    fields,timeline=read_scanned_fields(blob)
    if not allow_delta:fields=[f for f in fields if f.kind=='absolute']
    out=batch.decode_one_s16(blob,len(ref))
    if out is None:raise RuntimeError('Baseline C++ decode failure')
    baseline=metrics(ref,out)
    orig_stoi=baseline['stoi_pcm16']
    ref64=ref.astype(np.float64)
    def sse(pcm):
        z=ref64-pcm.astype(np.float64)
        return float(z@z)
    cur=blob;cur_pcm=out;cur_sse=sse(out)
    stats={'trials':0,'decode_batches':0,'accepted':[],'per_step':{},'inputs':len(fields)}
    # Use per-sample SSE for objective. STOI checked only for improving candidates.
    stop=False
    current_spectrum=timeline.copy()
    for sweep in range(passes):
        for step in step_sizes:
            if stop:break
            improvements=0
            for f in fields:
                # Original fixed bitfield value may have changed in prior sweeps.
                raw=0
                for j in range(f.width):raw|=((cur[(f.bit_offset+j)//8] >> ((f.bit_offset+j)%8))&1)<<j
                stored=raw-256 if f.width==8 and raw>=128 else raw
                # Conservative validity limits are relative to ORIGINAL stream.
                base_change=stored-f.stored
                choices=[]
                for sign in (-1,1):
                    d=base_change+sign*step
                    if f.min_change<=d<=f.max_change:
                        staged=current_spectrum[f.frame:f.affected_end,:].copy()
                        staged[:,f.coeff]+=sign*step
                        if np.any(staged<0) or np.any(staged>1023) or np.any(np.diff(staged,axis=1)<10):
                            continue
                        val=stored+sign*step
                        if f.width==8:val&=255
                        choices.append((sign,patch_bits(cur,f.bit_offset,f.width,val)))
                if not choices:continue
                if stats['trials']>=max_trials:stop=True;break
                choices=choices[:max_trials-stats['trials']]
                decoded=batch.decode_many_s16([b for _,b in choices],len(ref))
                stats['decode_batches']+=1
                stats['trials']+=len(choices)
                ranked=[]
                for (sign,b),pcm in zip(choices,decoded):
                    if pcm is None:continue
                    err=sse(pcm)
                    if err<cur_sse-min_sse_improvement:
                        ranked.append((err,sign,b,pcm))
                for err,sgn,b,pcm in sorted(ranked,key=lambda z:z[0]):
                    # STOI gate: no material degradation relative to INPUT baseline.
                    trial=metrics(ref,pcm)
                    if trial['stoi_pcm16'] + 1.e-12>=orig_stoi+min_stoi_delta:
                        cur=b;cur_pcm=pcm;cur_sse=err;improvements+=1
                        current_spectrum[f.frame:f.affected_end,f.coeff] += sgn*step
                        stats['accepted'].append({'frame':f.frame,'coeff':f.coeff,'kind':f.kind,
                                                  'change':sgn*step,'step':step,
                                                  'snr':trial['pcm16_snr_db'],'stoi':trial['stoi_pcm16']})
                        break
            stats['per_step'][f'{sweep}:{step}']=improvements
    assert np.all(np.diff(current_spectrum,axis=1)>=10)
    quality=metrics(ref,cur_pcm)
    assert len(blob)==len(cur)
    original_frames, _,original_codes=unpack_lpx4(blob)
    new_frames,_,new_codes=unpack_lpx4(cur)
    if original_codes!=new_codes:
        raise AssertionError('Refinement unexpectedly changed excitation quant codes')
    assert len(original_frames)==len(new_frames)
    assert quality['stoi_pcm16']>=baseline['stoi_pcm16']+min_stoi_delta-1e-12
    return cur,cur_pcm,{'baseline':baseline,'optimized':quality, 'file_bytes':len(cur),
        'original_sha256':hashlib.sha256(blob).hexdigest(),
        'new_sha256':hashlib.sha256(cur).hexdigest(),
        'avr_decoder_unchanged':True,'format_unchanged':True,
        'pcm16_changed':hashlib.sha256(out.tobytes()).digest()!=hashlib.sha256(cur_pcm.tobytes()).digest(),
        'meta':{k:v for k,v in stats.items() if k!='accepted'}, 'accepted_changes':stats['accepted'],
        'elapsed_s':round(time.perf_counter()-start,3)}


def main():
    ap=argparse.ArgumentParser(description='Refine existing LPX4 LSF values with unchanged byte count and decoder')
    ap.add_argument('input',type=Path)
    ap.add_argument('reference_wav',type=Path)
    ap.add_argument('output',type=Path)
    ap.add_argument('--max-trials',type=int,default=2400)
    ap.add_argument('--passes',type=int,default=1)
    ap.add_argument('--steps',default='16,8,4,2,1')
    ap.add_argument('--max-stoi-drop',type=float,default=0.00003)
    ap.add_argument('--report',type=Path)
    a=ap.parse_args()
    ref=read_wav16(a.reference_wav)
    with BatchSession('batch') as batch:
        b,pcm,report=optimize(a.input.read_bytes(),ref,batch,max_trials=a.max_trials,
            passes=a.passes,step_sizes=tuple(int(x) for x in a.steps.split(',')),
            min_stoi_delta=-a.max_stoi_drop)
    a.output.parent.mkdir(exist_ok=True,parents=True)
    a.output.write_bytes(b)
    a.output.with_suffix('.pcm16le').write_bytes(pcm.astype('<i2').tobytes())
    a.output.with_suffix('.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='accepted_changes'},ensure_ascii=False,indent=2))
if __name__=='__main__':main()

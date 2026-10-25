#!/usr/bin/env python3
"""Offline, fixed-bit CELP-pulse refinement for L4HY v2.

Modifies only already-present, fixed-width pulse position/amplitude and pitch
fields. The header, number of frames, pulse count, bit length, and MCU decoder
are unchanged. Candidates are scored by the actual C++ decoder on source WAV.
Never used on AVR. A candidate is accepted only with lower whole-clip PCM MSE;
the final file can be rejected against STOI/peak/clipping gates.
"""
from __future__ import annotations
import argparse, sys, wave, subprocess, tempfile, json, hashlib
from pathlib import Path
import numpy as np
from pystoi import stoi
from scipy import signal
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'tools'))
from lpx4 import BitReader,get_rice,getplane,signed_from_z,calc_pred,HUFF3_DECODE,LAG_MIN,LAG_MAX,decode
from rice_v4_reference import read_scale

def fieldpos(rd):return rd.o*8-rd.n

def patchbits(blob,at,length,value):
    out=bytearray(blob)
    if not (0<=value<(1<<length)):raise ValueError('value out of range')
    for j in range(length):
        byte=(at+j)>>3;bit=(at+j)&7
        out[byte]=(out[byte]&~(1<<bit))|(((value>>j)&1)<<bit)
    return bytes(out)

def parse_sections(data):
    assert data[:6]==b'L4HY\x02\x03'
    num=int.from_bytes(data[8:12],'little'); rd=BitReader(data,20)
    subsections=[];history=[];scale=0;p=0
    while p<num:
        # Frame @ 160 sample boundary
        first=rd.get(1)
        if first:
            second=rd.get(1)
            if not second:
                for _ in range(10):rd.get(8);rd.get(2)
            else:
                raw=rd.get(1)
                for _ in range(10):
                    if raw:rd.get(8)
                    else:getplane(rd)
        for blk in range(2):
            if p>=num:break
            b=rd.get(3);scale=read_scale(rd,scale)
            remaining=min(80,num-p)
            for st in range(0,remaining,40):
                count=min(40,remaining-st);typ=rd.get(2)
                info={'start':p+st,'count':count,'type':typ,'b':b}
                if typ==0:
                    k=rd.get(3)
                    for i in range(count):
                        if k==0:v=rd.get(b)-(1<<(b-1)) if b else 0
                        elif k==7:
                            s=''
                            while s not in HUFF3_DECODE:s+=str(rd.get(1))
                            v=HUFF3_DECODE[s]
                        else:v=get_rice(rd,k)
                        history.append(v)
                else:
                    info['lag_bit']=fieldpos(rd);lag=rd.get(7)+18
                    info['gain_bit']=fieldpos(rd);gain=rd.get(5)
                    info.update(lag=lag,gain=gain)
                    if typ==1:k=rd.get(3)
                    elif typ==2:
                        pc=rd.get(4);pulses=[]
                        for _ in range(pc):
                            posbit=fieldpos(rd);ix=rd.get(6)
                            ampbit=fieldpos(rd);z=rd.get(5)
                            pulses.append({'pos':ix,'amp':signed_from_z(z),'posbit':posbit,'ampbit':ampbit})
                        info['pulses']=pulses
                    else:raise ValueError('reserved type')
                    for i in range(count):
                        v=calc_pred(history,lag,gain,b)
                        if typ==1:
                            delta=rd.get(8) if k==7 else get_rice(rd,k)
                            if k==7 and delta>=128:delta-=256
                            v+=delta
                        else:
                            for item in pulses:
                                if item['pos']==i:v+=item['amp'];break
                            if b:v=max(-(1<<(b-1)),min((1<<(b-1))-1,v))
                            else:v=0
                        history.append(v)
                if typ==2:subsections.append(info)
            p+=remaining
    pyq=decode(data)[2]
    if history!=pyq:raise AssertionError('L4HY scanner reconstructed wrong quant codes')
    return subsections

def truth_pcm(path):
    with wave.open(str(path),'rb') as w:
        assert w.getframerate()==8000 and w.getsampwidth()==2 and w.getnchannels()==1
        return np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(float)/32768

def quality(x,y):
    assert len(x)==len(y)
    error=x-y
    snr=10*np.log10(max(np.mean(x*x),1e-30)/max(np.mean(error*error),1e-30))
    score=float(stoi(x,y,8000,extended=False))
    # Spectral error computed from STFT, weighted away from unvoiced silence.
    _,_,tx=signal.stft(x,fs=8000,nperseg=256,noverlap=128)
    _,_,ty=signal.stft(y,fs=8000,nperseg=256,noverlap=128)
    spectral=float(np.mean(np.abs(20*np.log10((np.abs(tx)+1.e-4)/(np.abs(ty)+1.e-4)))))
    return dict(snr_db=float(snr),stoi=score,rms=float(np.sqrt(np.mean(error*error))),spectral_db=spectral)

def refine(path,original,decoder,out,passes=2,max_eval=1500,max_stoi_loss=0.0,batch_decoder=None):
    data=path.read_bytes();info=parse_sections(data)
    originalx=truth_pcm(original)
    stats={'sparse_subframes':len(info),'input_bytes':len(data),'trials':0,'passes':passes}
    if not info:out.write_bytes(data);return stats
    with tempfile.TemporaryDirectory() as td:
        inp=Path(td)/'test.l4hy';pcmout=Path(td)/'test.pcm'
        def execute(blob):
            if batch_decoder is not None:
                raw=batch_decoder.decode_one(blob,len(originalx))
                return (raw.astype(np.float64)/128.0-1.0) if raw is not None else None
            inp.write_bytes(blob)
            proc=subprocess.run([str(decoder),str(inp),str(pcmout)],capture_output=True)
            if proc.returncode:return None
            z=np.frombuffer(pcmout.read_bytes(),dtype=np.uint8).astype(float)/128-1
            return z if len(z)==len(originalx) else None
        def execute_many(blobs):
            if batch_decoder is None:
                return [execute(blob) for blob in blobs]
            raw=batch_decoder.decode_many(blobs,len(originalx))
            return [z.astype(np.float64)/128.0-1.0 if z is not None else None for z in raw]
        current=execute(data)
        if current is None:raise RuntimeError('baseline decoder failed')
        before=quality(originalx,current)
        best=data;bestpcm=current
        bestmse=float(np.mean((originalx-current)**2))
        improvements=[]
        for loop in range(passes):
            changed=0
            for section in info:
                if stats['trials']>=max_eval:break
                # Per-sample entropy cost unchanged: fields are fixed width.
                specs=[('gain',section['gain_bit'],5,section['gain'],range(-3,4),0,31),
                       ('lag',section['lag_bit'],7,section['lag']-18,range(-3,4),0,127)]
                for j,pulse in enumerate(section['pulses']):
                    specs.append((f'p{j}.amp',pulse['ampbit'],5,(pulse['amp']*2 if pulse['amp']>=0 else -pulse['amp']*2-1),None,0,31))
                    specs.append((f'p{j}.pos',pulse['posbit'],6,pulse['pos'],range(-2,3),0,section['count']-1))
                for label,pos,width,stored,offsets,lower,upper in specs:
                    if stats['trials']>=max_eval:break
                    if label.endswith('.amp'):
                        # Work in signed pulse domain, with ZigZag packed to 5 bits.
                        v0=(stored//2 if not stored&1 else -(stored+1)//2)
                        candidates=[((v*2 if v>=0 else -v*2-1),v) for v in range(max(-16,v0-3),min(15,v0+3)+1) if v!=v0]
                    else:
                        candidates=[(stored+delta,None) for delta in offsets if delta and lower<=stored+delta<=upper]
                    locally_best=None
                    # Decode each field's alternative values in one C++ call.
                    # Sequential field order and strict-MSE tie breaking are
                    # unchanged: accepting one field affects subsequent fields.
                    tasks=[]
                    for encoded,signed_value in candidates:
                        if stats['trials']+len(tasks)>=max_eval:break
                        if label.endswith('.pos'):
                            j=int(label[1:label.index('.')]);last=section['pulses'][j-1]['pos'] if j>0 else -1
                            nex=section['pulses'][j+1]['pos'] if j+1<len(section['pulses']) else section['count']
                            if not (last<encoded<nex):continue
                        tasks.append((encoded,signed_value,patchbits(best,pos,width,encoded)))
                    ys=execute_many([blob for _,_,blob in tasks])
                    for (encoded,signed_value,trial),y in zip(tasks,ys):
                        stats['trials']+=1
                        if y is None:continue
                        mse=float(np.mean((originalx-y)**2))
                        if mse<bestmse-1e-11 and (locally_best is None or mse<locally_best[0]):locally_best=(mse,trial,y,encoded,signed_value)
                    if locally_best:
                        mse,trial,y,encoded,sval=locally_best
                        # Check intelligibility on the *real decoded PCM* at each acceptance.
                        score=quality(originalx,y)
                        if score['stoi']>=before['stoi']-max_stoi_loss:
                            best=trial;bestpcm=y;bestmse=mse;changed+=1
                            improvements.append({'subframe':section['start'],'field':label,'old':stored,'new':encoded,'pcm_snr_db':score['snr_db'],'stoi':score['stoi']})
                            if label=='gain':section['gain']=encoded
                            elif label=='lag':section['lag']=encoded+18
                            elif label.endswith('.amp'):
                                j=int(label[1:label.index('.')]);section['pulses'][j]['amp']=sval
                            elif label.endswith('.pos'):
                                j=int(label[1:label.index('.')]);section['pulses'][j]['pos']=encoded
                if stats['trials']>=max_eval:break
            if not changed or stats['trials']>=max_eval:break
        after=quality(originalx,bestpcm)
        assert len(data)==len(best)
        assert len(decode(best)[2])==len(bestpcm)
        out.write_bytes(best)
        stats.update(input_metrics=before,output_metrics=after,changes=improvements,
                     final_bytes=len(best),sha256=hashlib.sha256(best).hexdigest())
        return stats

def main():
    p=argparse.ArgumentParser()
    p.add_argument('source',type=Path);p.add_argument('original_wav',type=Path)
    p.add_argument('cpp_decoder',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--passes',type=int,default=2);p.add_argument('--max-eval',type=int,default=1400)
    p.add_argument('--report',type=Path)
    p.add_argument('--decode-backend',choices=('auto','batch','reference'),default='auto')
    a=p.parse_args()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    from batch_decoder import BatchSession
    with BatchSession(a.decode_backend) as batch:
        result=refine(a.source,a.original_wav,a.cpp_decoder,a.output,passes=a.passes,max_eval=a.max_eval,batch_decoder=batch)
    if a.report:a.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='changes'},ensure_ascii=False,indent=2))
if __name__=='__main__':main()

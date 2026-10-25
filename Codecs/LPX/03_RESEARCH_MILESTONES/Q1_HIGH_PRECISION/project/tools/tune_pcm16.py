#!/usr/bin/env python3
"""Offline tuning of existing LPX4 preQ14/brightQ14 fields against TRUE PCM16.

No PWM-domain metric, no changes to firmware/bitstream fields, no extra bytes.
Uses actual C++ fixed-point LPC synthesis to score every candidate.
"""
from __future__ import annotations
import argparse, json, hashlib, time, wave
from pathlib import Path
import numpy as np
from pystoi import stoi
from batch_decoder import BatchSession


def read_wav16(path:Path):
    with wave.open(str(path),'rb') as f:
        if (f.getnchannels(),f.getframerate(),f.getsampwidth())!=(1,8000,2):
            raise ValueError('Reference must be mono PCM16/8kHz WAV')
        return np.frombuffer(f.readframes(f.getnframes()),dtype='<i2').copy()


def metrics(ref:np.ndarray,pcm:np.ndarray,with_stoi=True):
    x=ref.astype(np.float64)/32768.0
    y=pcm.astype(np.float64)/32768.0
    if x.shape!=y.shape:raise ValueError('Sample count mismatch')
    mse=float(np.mean(np.square(x-y)))
    power=max(float(np.mean(np.square(x))),1e-30)
    out={'pcm16_snr_db':float(10*np.log10(power/max(mse,1e-30))),
         'pcm16_rmse':float(np.sqrt(mse)),
         'clip_count':int(np.count_nonzero((pcm==-32768)|(pcm==32767))),
         'pcm16_sha256':hashlib.sha256(pcm.astype('<i2').tobytes()).hexdigest()}
    if with_stoi:out['stoi_pcm16']=float(stoi(x,y,8000,extended=False))
    return out


def set_header(blob:bytes,pre:int,bright:int)->bytes:
    if not 0<=pre<=16384 or not 0<=bright<=11469:
        raise ValueError('Q14 field out of range')
    patched=bytearray(blob)
    patched[12:14]=pre.to_bytes(2,'little')
    patched[14:16]=bright.to_bytes(2,'little')
    return bytes(patched)


def tune(blob:bytes,ref:np.ndarray,batch,trial_limit=300,stoi_tolerance=0.0,min_snr_step=0.00001):
    initial=(int.from_bytes(blob[12:14],'little'),int.from_bytes(blob[14:16],'little'))
    total_samples=len(ref)
    if int.from_bytes(blob[8:12],'little')!=total_samples:raise ValueError('Reference length not equal to bitstream')
    cache={}
    batches=0
    def score_keys(keys):
        nonlocal batches
        keys=[x for x in dict.fromkeys(keys) if 0<=x[0]<=16384 and 0<=x[1]<=11469 and x not in cache]
        keys=keys[:max(0,trial_limit-len(cache))]
        for off in range(0,len(keys),24):
            group=keys[off:off+24]
            pcm=batch.decode_many_s16([set_header(blob,*q) for q in group],total_samples)
            batches+=1
            for key,y in zip(group,pcm):
                if y is None:cache[key]=None
                else:
                    dy=(ref.astype(np.float64)-y.astype(np.float64))
                    cache[key]=(float(np.dot(dy,dy)),y)
    score_keys([initial])
    if cache.get(initial) is None:raise RuntimeError('Baseline decoding failed')
    base_pcm=cache[initial][1]
    baseline=metrics(ref,base_pcm)
    initial_stoi=baseline['stoi_pcm16']
    current=initial
    best_sse=cache[current][0]
    accepted=[]
    for step in (1024,512,256,128,64,32,16,8,4,2,1):
        improve=True
        while improve and len(cache)<trial_limit:
            improve=False
            neighbours=[]
            for fld in (0,1):
                for sign in (-4,-2,-1,1,2,4):
                    arr=list(current);arr[fld]+=step*sign
                    neighbours.append(tuple(arr))
            score_keys(neighbours)
            # candidates with improved MSE, accurate STOI gate only on shortlisted files
            candidates=sorted((value[0],key,value[1]) for key,value in ((key,cache.get(key)) for key in neighbours) if value is not None and value[0]<best_sse-1e-9)
            for sse,key,p in candidates:
                test_stoi=metrics(ref,p)['stoi_pcm16']
                if test_stoi+1e-12>=initial_stoi-stoi_tolerance:
                    accepted.append({'preQ14':key[0],'brightQ14':key[1],
                                     'pcm16_snr_db':metrics(ref,p,False)['pcm16_snr_db'],
                                     'stoi_pcm16':test_stoi})
                    current=key;best_sse=sse;improve=True;break
    final_blob=set_header(blob,*current)
    final_pcm=cache[current][1]
    after=metrics(ref,final_pcm)
    assert len(final_blob)==len(blob)
    return final_blob,final_pcm,{'input_header':dict(preQ14=initial[0],brightQ14=initial[1]),
                                'output_header':dict(preQ14=current[0],brightQ14=current[1]),
                                'old':baseline,'new':after,'trials':len(cache),'batches':batches,
                                'accepted_changes':accepted,'unchanged_byte_count':len(final_blob)==len(blob),
                                'file_sha256':hashlib.sha256(final_blob).hexdigest()}


def main():
    p=argparse.ArgumentParser(description='Optimize LPX4 header for signed PCM16 instead of PWM')
    p.add_argument('input',type=Path);p.add_argument('reference_wav',type=Path)
    p.add_argument('output',type=Path)
    p.add_argument('--report',type=Path)
    p.add_argument('--max-trials',type=int,default=300)
    p.add_argument('--max-stoi-loss',type=float,default=0)
    o=p.parse_args()
    ref=read_wav16(o.reference_wav)
    with BatchSession('batch') as batch:
        b,p16,report=tune(o.input.read_bytes(),ref,batch,o.max_trials,o.max_stoi_loss)
    o.output.parent.mkdir(exist_ok=True,parents=True);o.output.write_bytes(b)
    if o.report:
        o.report.parent.mkdir(exist_ok=True,parents=True)
        o.report.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='accepted_changes'},ensure_ascii=False,indent=2))
if __name__=='__main__':main()

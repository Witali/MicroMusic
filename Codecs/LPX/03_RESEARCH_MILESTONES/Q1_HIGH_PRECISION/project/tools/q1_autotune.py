#!/usr/bin/env python3
"""Retune LPX4 VBR for fractional Q1 LPC, using actual native Q1 PCM16.

The chosen stream is not guaranteed to be better than the legacy decoder; it
is accepted only when it meets explicitly supplied SER/STOI/size thresholds.
"""
from __future__ import annotations
import argparse, json, os, sys, tempfile, hashlib, subprocess
from pathlib import Path
import numpy as np
import soundfile as sf
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'encoder_vbr'/'tools')]
from batch_decoder import BatchDecoder
from encode_vbr_fixedexact import make as make_l3av
from fast_vbr import Prepared
from lpx4 import encode as make_lpx4
from l3av_parse import unpack
from tune_pcm16 import metrics,read_wav16,tune

def run(data_dir:Path,output:Path,lambdas:list[float], min_ser:float=30.0,
        min_stoi:float=.95, max_bytes:int|None=None,selection:str='min-size',
        tune_header:bool=True):
    refs=['reference.wav','source_lsf_co.json','source_coeff_trace.csv','source_legacy.lpx3']
    for f in refs:
        if not (data_dir/f).is_file():raise FileNotFoundError(data_dir/f)
    ref=read_wav16(data_dir/'reference.wav')
    audio,sr=sf.read(str(data_dir/'reference.wav'))
    if sr!=8000 or len(audio)!=len(ref) or np.ndim(audio)!=1:
        raise ValueError('Expected 8kHz mono PCM16')
    context=Prepared(audio,data_dir/'source_lsf_co.json',data_dir/'source_coeff_trace.csv',data_dir/'source_legacy.lpx3')
    results=[]
    with tempfile.TemporaryDirectory(prefix='lpx4_q1_autotune_') as td:
        td=Path(td);lib=td/'libq1.so'
        cmd=['g++','-O3','-std=c++11','-fPIC','-shared',
             '-DLPX4_WIDE_FRAC=1','-DLPX4_FAST_SPLIT_Q1=1',
             '-I'+str(ROOT/'src'),str(ROOT/'src/Lpx4HybridCore.cpp'),
             str(ROOT/'src/native_batch_decoder.cpp'),'-o',str(lib)]
        subprocess.run(cmd,check=True)
        decoder=BatchDecoder(lib)
        encs=[]
        for lam in lambdas:
            path=td/'x.l3av'
            make_l3av(audio,data_dir/'source_lsf_co.json',data_dir/'source_coeff_trace.csv',
                     data_dir/'source_legacy.lpx3',path,float(lam),fast=True,context=context)
            blob,*_=make_lpx4(unpack(path.read_bytes()),float('inf'),fast=True)
            encs.append((float(lam),blob))
        for start in range(0,len(encs),16):
            group=encs[start:start+16]
            outs=decoder.decode_many_s16([v for _,v in group],len(ref))
            for (lam,blob),pcm in zip(group,outs):
                if pcm is None:results.append(dict(lam=lam,status='DECODE_ERROR'));continue
                m=metrics(ref,pcm)
                ok=(m['pcm16_snr_db']>=min_ser and m['stoi_pcm16']>=min_stoi and
                    (max_bytes is None or len(blob)<=max_bytes))
                results.append(dict(lam=lam,bytes=len(blob),stoi=m['stoi_pcm16'],
                                    ser_db=m['pcm16_snr_db'],status='PASS' if ok else 'REJECTED',
                                    _blob=blob,_pcm=pcm))
        passing=[r for r in results if r['status']=='PASS']
        if not passing:
            raise RuntimeError('No candidates satisfied requested quality/size thresholds')
        if selection=='min-size': key=lambda r:(-r['bytes'],r['ser_db'],r['stoi'])
        elif selection=='max-ser': key=lambda r:(r['ser_db'],r['stoi'],-r['bytes'])
        elif selection=='max-stoi': key=lambda r:(r['stoi'],r['ser_db'],-r['bytes'])
        else:raise ValueError(selection)
        best=max(passing,key=key)
        original=best.copy()
        if tune_header:
            allow=max(0.0,best['stoi']-min_stoi)
            tuned,pcm,stats=tune(best['_blob'],ref,decoder,trial_limit=180,stoi_tolerance=allow)
            quality=metrics(ref,pcm)
            if (quality['stoi_pcm16']>=min_stoi and quality['pcm16_snr_db']>=best['ser_db'] and
                (max_bytes is None or len(tuned)<=max_bytes)):
                best={**best,'_blob':tuned,'_pcm':pcm,'ser_db':quality['pcm16_snr_db'],
                       'stoi':quality['stoi_pcm16'],'bytes':len(tuned)}
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_bytes(best['_blob'])
        (output.with_suffix('.s16le')).write_bytes(best['_pcm'].astype('<i2').tobytes())
        report={'input':str(data_dir),'output':str(output),'chosen_lambda':best['lam'],
                'size_bytes':best['bytes'],'ser_original_db':best['ser_db'],
                'stoi':best['stoi'],'stream_sha256':hashlib.sha256(best['_blob']).hexdigest(),
                'decoder':'fast fractional Q1, 16x16 + carry; LPC not changed in codebook',
                'avr_real_time_verified':False,'min_ser':min_ser,'min_stoi':min_stoi,
                'selection':selection,'candidates':[{k:v for k,v in r.items() if not k.startswith('_')} for r in results]}
        (output.with_suffix('.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        return report

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data-dir',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--lambdas',default='0.0005,0.00055,0.0006,0.00065,0.00075,0.0008,0.0009,0.001,0.00115,0.0014')
    ap.add_argument('--min-ser',type=float,default=30.0)
    ap.add_argument('--min-stoi',type=float,default=0.95)
    ap.add_argument('--max-bytes',type=int)
    ap.add_argument('--selection',choices=['min-size','max-ser','max-stoi'],default='min-size')
    ap.add_argument('--no-header-tune',action='store_true')
    a=ap.parse_args()
    rep=run(a.data_dir,a.output,[float(x) for x in a.lambdas.split(',')],
            a.min_ser,a.min_stoi,a.max_bytes,a.selection,not a.no_header_tune)
    print(json.dumps({k:v for k,v in rep.items() if k!='candidates'},ensure_ascii=False,indent=2))
if __name__=='__main__':main()

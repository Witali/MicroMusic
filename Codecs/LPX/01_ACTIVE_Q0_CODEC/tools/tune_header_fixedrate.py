#!/usr/bin/env python3
"""Offline search of two existing Q14 header fields. No stream growth or new AVR code.

Optimizes PCM waveform MSE of decoded audio against original PCM16 while
requiring STOI >= initial STOI. Coefficients are in fixed-width 16-bit fields.
"""
import argparse,json,subprocess,tempfile,wave,hashlib
from pathlib import Path
import numpy as np
from pystoi import stoi
from refine_fixedrate import quality,truth_pcm

def run(src,wav,decoder,dest,report,max_trials=320,min_improvement=2e-9,batch_decoder=None):
    data=src.read_bytes();truth=truth_pcm(wav)
    pre0=int.from_bytes(data[12:14],'little');bright0=int.from_bytes(data[14:16],'little')
    with tempfile.TemporaryDirectory() as td:
        p=Path(td);i=p/'input.l4hy';o=p/'out.pcm'
        cache={}
        def make_blob(pre,bright):
            d=bytearray(data)
            d[12:14]=pre.to_bytes(2,'little');d[14:16]=bright.to_bytes(2,'little')
            return bytes(d)
        def dec_many(keys):
            selected=[];blobs=[]
            for pre,bright in keys:
                key=(pre,bright)
                if not (0<=pre<=16384 and 0<=bright<=11469):continue
                if key in cache or len(cache)+len(selected)>=max_trials:continue
                selected.append(key)
                blobs.append(make_blob(pre,bright))
            if batch_decoder is not None:
                raws=batch_decoder.decode_many(blobs,len(truth))
                decoded=[r.astype(np.float64)/128.0-1.0 if r is not None else None for r in raws]
            else:
                decoded=[]
                for blob in blobs:
                    i.write_bytes(blob)
                    r=subprocess.run([str(decoder),str(i),str(o)],capture_output=True)
                    y=(np.frombuffer(o.read_bytes(),dtype=np.uint8).astype(float)/128-1
                       if r.returncode==0 else None)
                    decoded.append(y if y is not None and len(y)==len(truth) else None)
            for key,blob,y in zip(selected,blobs,decoded):
                if y is not None:
                    mse=float(np.mean((truth-y)**2))
                    cache[key]=(mse,y,blob)
        def dec(pre,bright):
            dec_many([(pre,bright)])
            return cache.get((pre,bright))
        cur=(pre0,bright0);current=dec(*cur)
        if current is None:raise RuntimeError('baseline decode error')
        orig=quality(truth,current[1]);best_mse=current[0];changes=[]
        # Multiple step widths avoid costly floating point optimisation at runtime.
        for step in (512,128,32,8,2,1):
            improved=True
            while improved and len(cache)<max_trials:
                improved=False
                all_candidates=[]
                # Evaluate all 12 independent neighbours with one native call.
                neighbours=[]
                for which in (0,1):
                    for offset in (-4,-2,-1,1,2,4):
                        nn=list(cur);nn[which]+=step*offset;neighbours.append(tuple(nn))
                dec_many(neighbours)
                for nn in neighbours:
                    result=cache.get(nn)
                    if result is not None and result[0]<best_mse-min_improvement:all_candidates.append((result[0],nn,result))
                all_candidates.sort(key=lambda x:x[0])
                for mse,nn,candidate in all_candidates:
                    q=quality(truth,candidate[1]);
                    if q['stoi']+1e-12>=orig['stoi']:
                        changes.append(dict(pre=nn[0],bright=nn[1],snr_db=q['snr_db'],stoi=q['stoi']))
                        best_mse=mse;cur=nn;current=candidate;improved=True;break
        res=dict(input_bytes=len(data),output_bytes=len(current[2]),baseline_header={'pre':pre0,'bright':bright0},
                 output_header={'pre':cur[0],'bright':cur[1]},baseline=orig,final=quality(truth,current[1]),
                 decoded_trials=len(cache),trial_limit=max_trials,trial_limit_hit=len(cache)>=max_trials,accepted_changes=changes,
                 sha256=hashlib.sha256(current[2]).hexdigest())
        dest.write_bytes(current[2]);report.write_text(json.dumps(res,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({k:v for k,v in res.items() if k!='accepted_changes'},ensure_ascii=False,indent=2))
        return res
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('source',type=Path);a.add_argument('original_wav',type=Path)
    a.add_argument('cpp_decoder',type=Path);a.add_argument('output',type=Path);a.add_argument('--report',type=Path,required=True)
    a.add_argument('--max-trials',type=int,default=320)
    a.add_argument('--decode-backend',choices=('auto','batch','reference'),default='auto')
    v=a.parse_args()
    from batch_decoder import BatchSession
    with BatchSession(v.decode_backend) as batch:
        run(v.source,v.original_wav,v.cpp_decoder,v.output,v.report,max_trials=v.max_trials,batch_decoder=batch)

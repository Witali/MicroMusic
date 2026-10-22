#!/usr/bin/env python3
"""Automated VBR mode selection with decoder-in-the-loop / STOI feedback.

Conservative constraint: STOI relative to the original cannot be lower than the
reference by more than 0.007; cannot add large output-sample jumps.
This script does not transcode/keep compatibility in firmware; fixed 6-byte
frames are training input only, the emitted .vbr is the native format.
"""
from pathlib import Path
import argparse,json,math
import numpy as np
import soundfile as sf
from pystoi import stoi
from vbr_codec import parse_fixed,expand,compress
from reference_model import decode
ROOT=Path(__file__).resolve().parent
NAMES=('chego','otvechaesh','vinni')
REFS=ROOT/'references'

def synth(frames):
    return decode(frames.ravel()).astype(np.uint8)

def jumps(out,thr=48):
    return int(np.count_nonzero(np.abs(np.diff(out.astype(np.int16)))>=thr))

def dist(a,b):
    return float(np.sqrt(np.mean((a.astype(np.int16)-b.astype(np.int16))**2)))

def analyze(ref,signal,ref_pcm):
    x=(signal.astype(np.float64)-128)/128
    return {'stoi':float(stoi(ref,x,7500,extended=False)), 'new_clicks':max(0,jumps(signal)-jumps(ref_pcm)), 'clicks':jumps(signal),'rms_changed':dist(signal,ref_pcm)}

def search(frames,ref,baseline,lam,passes=2):
    n=len(frames)
    modes=np.zeros(n,dtype=np.uint8)
    orig_score=float(stoi(ref,(baseline.astype(np.float64)-128)/128,7500))
    original_jumps=jumps(baseline)
    cached={}
    def calc(modes):
        key=bytes(modes)
        if key in cached:return cached[key]
        new=expand(compress(frames,modes))
        out=synth(new)
        st=float(stoi(ref,(out.astype(np.float32)-128)/128,7500))
        drops=st-orig_score
        added=max(0,jumps(out)-original_jumps)
        dr=dist(out,baseline)
        # Score balances intelligibility, no artifacts, and bitrate.
        # The weak fidelity term avoids STOI-only noise overfitting.
        score=st +lam*(6*n-len(compress(frames,modes)))-0.00035*dr-0.002*added
        cached[key]=(score,st,added,dr)
        return cached[key]
    for p in range(passes):
        order=list(range(1,n))
        if p%2:order=order[::-1]
        updates=0
        for i in order:
            bestmode=int(modes[i]);best=calc(modes)[0]
            for m in (0,1,2,3):
                if m==bestmode:continue
                trial=modes.copy();trial[i]=m
                val=calc(trial)[0]
                if val>best+1e-9:
                    best,bestmode=val,m
            if bestmode!=int(modes[i]):modes[i]=bestmode;updates+=1
        if not updates:break
    bitstream=compress(frames,modes)
    out=synth(expand(bitstream))
    stats=analyze(ref,out,baseline)
    stats.update({'lambda':lam,'speech_bytes':len(bitstream),'saved_bytes':len(frames)*6-len(bitstream),
                  'types':{str(x):int(np.sum(modes==x)) for x in range(4)}})
    return modes,stats,out

def train_one(v,lam_values=(.00014,.00035,.0007,.0014,.0025),passes=2,floor=.007):
    folder=ROOT/'samples'/v
    frames=parse_fixed((folder/'speech_full.bin').read_bytes())
    ref,sr=sf.read(REFS/v/'original.wav')
    assert sr==7500
    baseline=synth(frames)
    stats0=analyze(ref,baseline,baseline)
    candidates=[]
    for l in lam_values:
        modes,stat,out=search(frames,ref,baseline,l,passes)
        eligible=stat['stoi'] >= stats0['stoi']-floor and stat['new_clicks']==0
        print(v,'lambda',l,'N',stat['speech_bytes'],'STOI',round(stat['stoi'],5),'clicks',stat['clicks'], 'eligible',eligible,flush=True)
        candidates.append((modes,stat,out,eligible))
    eligible=[a for a in candidates if a[3]]
    if eligible:
        # Pick maximum saving among safely intelligible candidates; ties favor STOI.
        winner=min(eligible,key=lambda a:(a[1]['speech_bytes'],-a[1]['stoi']))
    else:
        # Do not accept worsening: keep all full records, but still new VBR decoder.
        modes=np.zeros(len(frames),np.uint8)
        winner=(modes,{**stats0,'speech_bytes':len(frames)*6,'saved_bytes':0,'types':{'0':len(frames),'1':0,'2':0,'3':0}},baseline,True)
    modes,stat,out,_=winner
    bitstream=compress(frames,modes)
    assert np.array_equal(out,synth(expand(bitstream)))
    (folder/'speech.vbr').write_bytes(bitstream)
    (folder/'selected_modes.bin').write_bytes(bytes(modes))
    (folder/'expected_pcm.raw').write_bytes(bytes(out))
    (folder/'reference_pcm.raw').write_bytes(bytes(baseline))
    meta={'baseline':stats0,'vbr':stat,'frames':len(frames),'bytes_original':len(frames)*6,
          'bytes_vbr':len(bitstream),'selection':'minimum size subject to STOI>=baseline-0.007, no additional large clicks'}
    (folder/'metrics.json').write_text(json.dumps(meta,indent=2,ensure_ascii=False))
    return meta
if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--voice',action='append',choices=NAMES)
    parser.add_argument('--passes',type=int,default=2)
    parser.add_argument('--floor',type=float,default=.007)
    parser.add_argument('--lambdas',default='.00014,.00035,.0007,.0014,.0025',help='comma separated rate-distortion prices')
    args=parser.parse_args()
    all_result={}
    for voice in (args.voice or NAMES):all_result[voice]=train_one(voice,passes=args.passes,floor=args.floor,lam_values=[float(z) for z in args.lambdas.split(',')])
    (ROOT/'training_report.json').write_text(json.dumps(all_result,indent=2,ensure_ascii=False))

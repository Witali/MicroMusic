#!/usr/bin/env python3
"""MicroMusic LPC2 Universal v3: one-command automatic encoder/trainer.

Example:
  python train_encode.py --input speech.mp3 --name test

Runs pitch analysis, selects the best traditional LPC2 Voice v2 model based on
objective metrics, then performs closed-loop 2/3/4-bit excitation quantization.
No sex/gender parameter is needed: the pitch range, quantizer and tonal slope
are selected on the actual sound. Outputs are deterministic for given files.
"""
from __future__ import annotations
import argparse, json, math, os, subprocess, shutil
from pathlib import Path
import numpy as np, soundfile as sf
from scipy.signal import resample_poly
from pystoi import stoi
from playwright.sync_api import sync_playwright
from hybrid_codec import ROOT,JS_CODEC,coeffs_from_lpc2,encode_lpx3,decode_lpx3,spectral_shape_distance

JS_ENCODE=r'''async ({data, pitch,range,post})=>{
 LPC2_PITCH_MIN=range[0]; LPC2_PITCH_MAX=range[1];
 const x=Float32Array.from(data);
 const c={frameMs:20,windowMs:32,pre:.85,voicing:.38,pitchSmooth:.65,repeat:.05};
 if(pitch)c.pitchGuideHz=pitch;
 const enc=await encodeLPC2(x,8000,c),packed=packLPC2(enc.meta,enc.frames,enc.analysis);
 const dec=unpackLPC2(packed.buffer),out=await synthLPC2(dec.meta,dec.frames,post);
 return{base:Array.from(new Uint8Array(packed.buffer)),pcm:Array.from(out)};
}'''

def load_audio(path):
    # ffmpeg decodes WAV, MP3, AAC, OGG and most common formats equally.
    cmd=['ffmpeg','-v','error','-nostdin','-i',str(path),'-ac','1','-ar','8000','-f','f32le','-acodec','pcm_f32le','pipe:1']
    b=subprocess.check_output(cmd)
    if len(b)%4:raise ValueError('ffmpeg returned incomplete PCM')
    x=np.frombuffer(b,dtype='<f4').copy()
    if len(x)<1000:raise ValueError('Too short audio clip')
    if len(x)>8000*30:raise ValueError('Limit test clips to <=30 seconds')
    peak=float(np.max(abs(x)))
    if peak>1:x/=peak
    return x

def trim_edges(x,sr=8000,threshold_db=-46,margin=.07):
    hop=80
    active=[]
    for i in range(0,len(x),hop):
        block=x[i:i+hop];rms=np.sqrt(np.mean(block**2))
        if rms>10**(threshold_db/20):active.append(i)
    if not active:return x
    start=max(0,active[0]-int(margin*sr))
    end=min(len(x),active[-1]+hop+int(margin*sr))
    return x[start:end]

def pyin_pitch(x,sr=8000):
    import librosa
    f0, voiced, probability=librosa.pyin(x.astype('float64'),sr=sr,fmin=55,fmax=850,
                                          hop_length=80,frame_length=512)
    valid=np.isfinite(f0)&voiced&(probability>=.40)
    pitch=f0[valid]
    count=int(math.ceil(len(x)/160))
    guide=[]
    for j in range(count):
        t=(j+.5)*.020
        ids=np.flatnonzero((np.abs(np.arange(len(f0))*.01-t)<.025)&valid)
        guide.append(float(np.median(f0[ids])) if len(ids)>=2 else None)
    if len(pitch)<max(6,int(.07*len(f0))):return None,guide
    return np.percentile(pitch,[5,50,95]).tolist(),guide

def evaluate(ref,x,sr):
    n=min(len(ref),len(x));r=ref[:n];y=x[:n]
    ry=np.sqrt(np.mean(y*y));rr=np.sqrt(np.mean(r*r))
    match=np.clip(y*(rr/(ry+1e-9)),-1,1)
    return {'stoi':round(float(stoi(r,match,sr,extended=False)),4),
            'spectral_error':round(spectral_shape_distance(r,match,sr),4)}

def train(path,name=None,trim=True,fast=False,output=None):
    path=Path(path)
    if not path.exists():raise FileNotFoundError(path)
    name=name or path.stem.replace(' ','_')
    out=Path(output) if output else ROOT/'samples'/name
    out.mkdir(parents=True,exist_ok=True)
    x=load_audio(path)
    if trim:x=trim_edges(x)
    pitch,guide=(None,None) if fast else pyin_pitch(x)
    ranges=[(65,850)]
    if pitch:
        lo=max(55,int(math.floor(pitch[0]*.70/10)*10))
        hi=min(900,int(math.ceil(pitch[2]*1.25/10)*10))
        if hi-lo>120 and (lo,hi) not in ranges:ranges.append((lo,hi))
    print(f'Source {path.name} / {name}, {len(x)/8000:.3f} sec, pitch={pitch}, ranges={ranges}',flush=True)
    sf.write(out/'original.wav',x,8000,subtype='PCM_16')
    html=JS_CODEC.read_text(encoding='utf8')
    candidates=[]
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        pg=b.new_page(); pg.set_default_timeout(120000);pg.set_content(html,wait_until='load')
        for rg in ranges:
            for pitchmode in ([None,guide] if guide else [None]):
                for post in [.10,.35]:
                    v=pg.evaluate(JS_ENCODE,{'data':x.tolist(),'pitch':pitchmode,'range':rg,'post':post})
                    output_pcm=np.asarray(v['pcm'],np.float32)
                    scores=evaluate(x,output_pcm,8000)
                    score=scores['spectral_error']-.60*scores['stoi']
                    candidates.append((score,rg,'pYIN' if pitchmode else 'Viterbi',post,bytes(v['base']),output_pcm,scores))
                    print('Candidate',rg,('pYIN' if pitchmode else 'Viterbi'),'post',post,scores,flush=True)
        b.close()
    score,rg,pitchmode,post,base,old,metric_old=min(candidates,key=lambda item:item[0])
    print('Selected LPC2',rg,pitchmode,post,metric_old,'bytes',len(base),flush=True)
    (out/'base_lpc2.lp2').write_bytes(base)
    sf.write(out/'lpc2_voice_v2.wav',old,8000,subtype='PCM_16')
    cache=coeffs_from_lpc2(base)
    report={'original_seconds':round(len(x)/8000,3),'sample_rate':8000,'baseline':metric_old,
            'baseline_bytes':len(base),'selected_pitch_range':rg,'pitch_guide':pitchmode,
            'postfilter_strength':post,'modes':{}}
    for bits in (2,3,4):
        stream,pcm,info=encode_lpx3(x,8000,base,bits,cache=cache)
        test,m=decode_lpx3(stream,cache=cache)
        if not np.array_equal(pcm,test):raise AssertionError('encoded/decoded mismatch')
        (out/f'voice_v3_{bits}bit.lpx3').write_bytes(stream)
        sf.write(out/f'voice_v3_{bits}bit.wav',pcm,8000,subtype='PCM_16')
        scores=evaluate(x,pcm,8000)
        report['modes'][str(bits)]={**scores,**info}
        print('HQ',bits,scores,'rate',info['bitrate_kbps'],'size',info['bytes'],flush=True)
    (out/'metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    return report

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input',required=True,help='Original WAV, MP3, OGG etc')
    ap.add_argument('--name',default=None,help='clip filename stem')
    ap.add_argument('--out',default=None,help='directory for results')
    ap.add_argument('--no-trim',action='store_true')
    ap.add_argument('--fast',action='store_true',help='Skip slower pYIN analysis')
    args=ap.parse_args()
    train(args.input,args.name,not args.no_trim,args.fast,args.out)

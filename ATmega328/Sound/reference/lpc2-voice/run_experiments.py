#!/usr/bin/env python3
"""Compare LPC2 Improved v1 and voice-preserving v2 automatically, using original audio.
Generates versioned LPC2 v2 streams and WAVs, evaluates pitch, STOI and spectral mismatch.
The AVR firmware is NOT modified by this experiment.
"""
from pathlib import Path
import argparse, json, base64, math, shutil, os
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly, stft
from pystoi import stoi
import librosa
from playwright.sync_api import sync_playwright

D=Path(__file__).resolve().parent
ROOT=Path(os.environ.get('MICROMUSIC_DATA_ROOT',D.parent/'MicroMusic_MultiPhrase'))
SR=8000
CLIPS=['xtuj-ntt','ne-otv','vinni']

def audio(path):
    v,sr=sf.read(path,dtype='float32')
    if v.ndim==2:v=v.mean(axis=1)
    if sr!=SR:v=resample_poly(v,SR//math.gcd(sr,SR),sr//math.gcd(sr,SR))
    return np.asarray(v,'float32')

def pitch_guide(x):
    f0,v,prob=librosa.pyin(x.astype('float64'),sr=SR,fmin=65,fmax=850,frame_length=512,hop_length=80)
    valid=np.isfinite(f0)&v&(prob>=.5)
    values=f0[valid]
    if len(values)<max(12,int(.10*len(f0))):return None,[None]*int(np.ceil(len(x)/160))
    nframes=int(np.ceil(len(x)/160))
    out=[]
    for j in range(nframes):
        t=(j+.5)*.02
        ids=np.flatnonzero((np.abs(np.arange(len(f0))*.01-t)<.025)&valid)
        out.append(float(np.median(f0[ids])) if len(ids)>=2 else None)
    return np.percentile(values,[5,50,95]),out

def logmel(ref, y):
    # Frame-matched mean-normalized log-band discrepancy, an objective proxy for spectral timbre.
    n=min(len(ref),len(y));r=ref[:n];v=y[:n]
    f,t,a=stft(r,SR,nperseg=512,noverlap=384);_,_,b=stft(v,SR,nperseg=512,noverlap=384)
    bands=[(100,280),(280,480),(480,720),(720,1050),(1050,1450),(1450,1950),(1950,2550),(2550,3400)]
    aa=np.array([np.mean(np.abs(a)[(f>=lo)&(f<hi)],axis=0) for lo,hi in bands])
    bb=np.array([np.mean(np.abs(b)[(f>=lo)&(f<hi)],axis=0) for lo,hi in bands])
    aa=np.log(np.maximum(aa,1e-6));bb=np.log(np.maximum(bb,1e-6))
    aa=aa-aa.mean(axis=0,keepdims=True);bb=bb-bb.mean(axis=0,keepdims=True)
    w=np.maximum(0,np.mean(np.exp(aa),axis=0))**.55
    w/=w.sum()+1e-8
    return float(np.sum(w*np.mean(np.abs(aa-bb),axis=0)))

def metric(ref,y):
    n=min(len(ref),len(y));r=ref[:n];v=y[:n]
    # matched-gain comparison; don't score global volume difference as timbre.
    vm=float(np.sqrt(np.mean(v*v)));rm=float(np.sqrt(np.mean(r*r)))
    if vm>1e-6:v=np.clip(v*(rm/vm),-1,1)
    s=float(stoi(r,v,SR,extended=False)) if n>3000 else None
    return {'stoi':round(s,4) if s is not None else None,'spectral_error':round(logmel(r,v),4)}

JS_RUN=r'''async ({data,range,guide,post}) => {
  LPC2_PITCH_MIN=range[0];LPC2_PITCH_MAX=range[1];
  const x=new Float32Array(data);
  const config={frameMs:20,windowMs:32,pre:.85,voicing:.38,pitchSmooth:.65,repeat:.05};
  if(guide)config.pitchGuideHz=guide;
  const enc=await encodeLPC2(x,8000,config);
  const packed=packLPC2(enc.meta,enc.frames,enc.analysis);
  const decoded=unpackLPC2(packed.buffer);
  const pcm=await synthLPC2(decoded.meta,decoded.frames,post);
  const f0=decoded.frames.map(f=>f.mode===1||f.mode===2?8000/qLpc2Pitch(f.pitch,8000,decoded.meta.pitchMin,decoded.meta.pitchMax):0);
  return {bin:Array.from(new Uint8Array(packed.buffer)), pcm:Array.from(pcm), meta:decoded.meta,stats:decoded.stats, f0};
}'''
JS_OLD=r'''async ({data}) => {
  const bin=new Uint8Array(data).buffer;
  const dec=unpackLPC2(bin);
  const pcm=await synthLPC2(dec.meta,dec.frames,.35);
  return {pcm:Array.from(pcm),version:dec.meta.ver,pitchMin:dec.meta.pitchMin,pitchMax:dec.meta.pitchMax};
}'''

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--clips',nargs='*',default=CLIPS)
    opts=ap.parse_args()
    (D/'samples').mkdir(exist_ok=True)
    html=(D/'LPC2_Voice_v2.html').read_text(encoding='utf8')
    old=[];entries={}
    with sync_playwright() as p:
        chromium=shutil.which('chromium') or shutil.which('chromium-browser') or shutil.which('google-chrome')
        launch={'executable_path':chromium} if chromium else {}
        browser=p.chromium.launch(headless=True,args=['--no-sandbox'],**launch)
        page=browser.new_page()
        page.set_default_timeout(120000)
        page.set_content(html,wait_until='load')
        for clip in opts.clips:
            src=ROOT/'release'/clip/'source.wav';teacher=ROOT/'release'/clip/'lpc2.wav'
            x=audio(src);t=audio(teacher)
            if len(x)==0:continue
            pitch,guide=pitch_guide(x)
            if pitch is None:
                low,high=65,850
            else:
                low=max(65,int(np.floor(pitch[0]*.64/10)*10));high=min(950,int(np.ceil(pitch[2]*1.24/10)*10))
                if clip=='vinni':low,high=65,850
            ranges={'universal':[65,850], 'adaptive':[low,high]}
            print('\nCLIP',clip,'duration',round(len(x)/SR,3),'pitch quantiles',pitch,'auto-range',ranges['adaptive'],flush=True)
            oldlp2=(ROOT/clip/'teacher.lp2') if (ROOT/clip/'teacher.lp2').exists() else (ROOT.parent/'MicroMusic_AutoLPC2/results/teacher.lp2')
            if oldlp2.exists() and clip!='vinni':
                res=page.evaluate(JS_OLD,{'data':list(oldlp2.read_bytes())})
                oldraw=np.array(res['pcm'],dtype=np.float32)
                print('Compatibility old LPC2 v1',res['version'],res['pitchMin'],res['pitchMax'],'PCM max error',float(np.max(abs(oldraw[:len(t)]-t[:len(oldraw)]))))
            variants={'old_v1':{'name':'Старый LPC2 Improved v1 (55–420 Гц)','file':str(teacher),'metrics':metric(x,t),'pitch_range':[55,420]}}
            sf.write(D/'samples'/f'{clip}_original.wav',x,SR,subtype='PCM_16')
            for preset,rg in ranges.items():
                for guide_mode in ['unguided','source_pitch']:
                    if guide_mode=='source_pitch' and pitch is None:continue
                    for post in [.10,.35]:
                        key=f'{preset}_{guide_mode}_post{int(post*100):02}'
                        result=page.evaluate(JS_RUN,{'data':x.tolist(),'range':rg,'guide':guide if guide_mode=='source_pitch' else None,'post':post})
                        assert result['meta']['ver']==2
                        assert result['meta']['pitchMin']==rg[0] and result['meta']['pitchMax']==rg[1]
                        output=np.asarray(result['pcm'],dtype='float32')
                        fp=D/'samples'/f'{clip}_{key}.wav';sf.write(fp,np.clip(output,-1,1),SR,subtype='PCM_16')
                        bp=D/'samples'/f'{clip}_{key}.lp2';bp.write_bytes(bytes(result['bin']))
                        m=metric(x,output)
                        nvoiced=sum(1 for f in result['f0'] if f>0)
                        # Compare only source pYIN voiced-frame frequencies with coded pitch in same temporal bin
                        pct=[]
                        if guide:
                            for a,b in zip(guide,result['f0']):
                                if a and b:pct.append(abs(1200*np.log2(a/b)))
                        m.update({'pitch_error_cents_median':round(float(np.median(pct)),1) if len(pct)>4 else None,
                                  'bitstream_bytes':len(result['bin']),'voiced_frames':nvoiced})
                        variants[key]={'name':f'LPC2 Voice v2 {preset}, {guide_mode}, post {post}',
                                       'file':str(fp),'bitstream':str(bp),'metrics':m,'pitch_range':rg}
                        print('  ',key,'STOI',m['stoi'],'spec',m['spectral_error'],'F0cents',m['pitch_error_cents_median'],'bytes',m['bitstream_bytes'],flush=True)
            # Choose by combined spectral and speech intelligibility among pitch-guided options
            candidates=[(key,v) for key,v in variants.items()]
            best=min(candidates,key=lambda kv:kv[1]['metrics']['spectral_error']-0.55*kv[1]['metrics']['stoi']+.00005*(kv[1]['metrics'].get('pitch_error_cents_median') or 100))
            print('  SELECTED',best[0],flush=True)
            entries[clip]={'pitch_quantiles':pitch.tolist() if pitch is not None else None,'old':variants['old_v1'], 'variants':variants, 'best':best[0]}
        browser.close()
    (D/'experiment_report.json').write_text(json.dumps(entries,ensure_ascii=False,indent=2),encoding='utf8')
    print('\nSaved',D/'experiment_report.json')

if __name__=='__main__':main()

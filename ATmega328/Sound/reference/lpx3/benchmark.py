#!/usr/bin/env python3
"""Auto benchmark for all three voice clips. No human tuning or gender-specific constants."""
from pathlib import Path
import numpy as np, soundfile as sf, json
from pystoi import stoi
from scipy.signal import stft
from hybrid_codec import coeffs_from_lpc2, encode_lpx3, decode_lpx3, ROOT
P=Path('/mnt/data/MicroMusic_LPC2_TimbreFix/samples')

clips={'vinni':'Мужской голос', 'xtuj-ntt':'Высокий голос (реплика 1)','ne-otv':'Высокий голос (реплика 2)'}

def spec(ref,decoded,sr):
    n=min(len(ref),len(decoded));ref=ref[:n];decoded=decoded[:n]
    f,t,R=stft(ref,sr,nperseg=256,noverlap=192); _,_,X=stft(decoded,sr,nperseg=256,noverlap=192)
    bands=np.geomspace(110,sr*.48,20)
    a=[];b=[]
    for lo,hi in zip(bands[:-1],bands[1:]):
        sel=(f>=lo)&(f<hi)
        if not np.any(sel):continue
        a.append(np.mean(np.abs(R[sel]),axis=0));b.append(np.mean(np.abs(X[sel]),axis=0))
    A=np.log(np.maximum(np.array(a),1e-6)); B=np.log(np.maximum(np.array(b),1e-6))
    # Per-frame remove loudness effects to isolate timbral/spectral difference.
    A-=A.mean(axis=0);B-=B.mean(axis=0)
    w=np.sqrt(np.maximum(0,np.mean(np.abs(R),axis=0))); w/=w.sum()+1e-9
    return float(np.sum(w*np.mean(abs(A-B),axis=0)))

def metrics(a,b,sr):
    n=min(len(a),len(b));a=np.asarray(a[:n]);b=np.asarray(b[:n]);
    rms0=np.sqrt(np.mean(a*a));rms1=np.sqrt(np.mean(b*b));bn=np.clip(b*(rms0/(rms1+1e-9)),-1,1)
    return dict(stoi=round(float(stoi(a,bn,sr,extended=False)),4),spec=round(spec(a,bn,sr),4),snr_db=round(float(10*np.log10(np.mean(a*a)/(np.mean((a-b)**2)+1e-10))),2), rms=float(rms1))

def process():
    results={}
    for name,descr in clips.items():
        src,sr=sf.read(P/f'{name}_original.wav')
        old,sr0=sf.read(P/f'{name}_adaptive_source_pitch_post10.wav'); assert sr==sr0
        base=(P/f'{name}_adaptive_source_pitch_post10.lp2').read_bytes()
        print('Clip',name,'samples',len(src), 'old',metrics(src,old,sr),flush=True)
        cache=coeffs_from_lpc2(base)
        o={'original_seconds':round(len(src)/sr,3),'sample_rate':sr,'baseline':metrics(src,old,sr),'baseline_bytes':len(base),'modes':{}}
        d=ROOT/'samples'/name;d.mkdir(parents=True,exist_ok=True)
        sf.write(d/'original.wav',src,sr,subtype='PCM_16')
        sf.write(d/'lpc2_voice_v2.wav',old,sr,subtype='PCM_16')
        (d/'base_lpc2.lp2').write_bytes(base)
        for bits in [2,3,4]:
            blob,pcm,info=encode_lpx3(src,sr,base,bits,cache=cache)
            decoded,_=decode_lpx3(blob,cache=cache)
            assert float(np.max(abs(pcm-decoded)))<1e-7
            (d/f'voice_v3_{bits}bit.lpx3').write_bytes(blob)
            sf.write(d/f'voice_v3_{bits}bit.wav',pcm,sr,subtype='PCM_16')
            o['modes'][str(bits)]={**metrics(src,pcm,sr),**info}
            print('   bits',bits, 'byte',len(blob),'stoi',o['modes'][str(bits)]['stoi'],'spectral',o['modes'][str(bits)]['spec'],'snr_db',o['modes'][str(bits)]['snr_db'],flush=True)
        results[name]=o
        (d/'metrics.json').write_text(json.dumps(o,indent=2,ensure_ascii=False))
    (ROOT/'benchmark.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))

if __name__=='__main__':process()

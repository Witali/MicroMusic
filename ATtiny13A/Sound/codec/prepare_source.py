#!/usr/bin/env python3
"""Convert MP3/WAV/etc to trimmed normalized 7500-Hz mono PCM for LPC fitting.
The default private demo already has a hand-aligned reference WAV; this helper
handles new recordings with an automatic edge-silence detector.
"""
import argparse, subprocess
from pathlib import Path
import numpy as np,soundfile as sf
from scipy.ndimage import uniform_filter1d

def convert(source,out,trim=None,pad=.07):
    cmd=['ffmpeg','-nostdin','-v','error','-i',str(source),'-vn','-ac','1','-ar','7500',
         '-af','highpass=f=65','-f','f32le','pipe:1']
    raw=subprocess.run(cmd,capture_output=True,check=True).stdout
    wave=np.frombuffer(raw,dtype='<f4').astype('float64')
    if not len(wave):raise RuntimeError('Empty audio from ffmpeg')
    sr=7500
    if trim:
        lo,hi=map(float,trim.split(':'));l=max(0,round(lo*sr));h=min(len(wave),round(hi*sr))
    else:
        # RMS envelope over 70 ms detects speech edges while preserving internal pauses.
        rms=np.sqrt(uniform_filter1d(wave**2,size=525,mode='nearest'))
        thresh=max(.012,0.095*float(np.percentile(rms,95)))
        active=np.flatnonzero(rms>=thresh)
        if len(active):
            l=max(0,int(active[0]-pad*sr));h=min(len(wave),int(active[-1]+pad*sr))
        else:l=0;h=len(wave)
    if h-l<500:raise ValueError('No speech detected / trim removed entire clip')
    x=wave[l:h].copy()
    if np.max(abs(x))>.0001:x*=.9/np.max(abs(x))
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    sf.write(out,x,sr,subtype='PCM_16')
    print(f'Prepared {source.name}: {len(x)/sr:.3f} s; original interval {l/sr:.3f}..{h/sr:.3f} s')
    return out

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--trim',help='Explicit start:end in seconds (else VAD trim)')
    a=ap.parse_args();convert(a.source,a.out,a.trim)

#!/usr/bin/env python3
"""Deterministic audio preparation for MicroMusic LPC experiments.

ffmpeg decodes MP3/WAV to mono float32 at 7500 Hz. Optional alignment with
canonical reference for repeatable comparison; otherwise energy-based trimming.
Always saves the exact resulting PCM as WAV, so future optimizations can use
an immutable training reference instead of repeatedly decoding MP3.

Examples:
  python convert_audio.py --input voice.mp3 --output reference.wav
  python convert_audio.py --input voice.mp3 --output reference.wav \
       --start-samples 275 --samples 9216 --peak 0.895
  python convert_audio.py --input voice.mp3 --output aligned.wav \
       --align-to references/chego/original.wav
"""
import argparse, json, subprocess
from pathlib import Path
import numpy as np, soundfile as sf
from scipy.signal import correlate
SR=7500

def decode_ffmpeg(filename):
    raw=subprocess.check_output(['ffmpeg','-nostdin','-hide_banner','-loglevel','error',
                                 '-i',str(filename),'-ac','1','-ar',str(SR),
                                 '-f','f32le','-acodec','pcm_f32le','-'])
    x=np.frombuffer(raw,dtype='<f4').astype(np.float64)
    if not len(x):raise ValueError('Decoded audio is empty')
    return x

def find_segment(x, reference):
    y=np.asarray(reference,dtype=np.float64)
    if len(x)<len(y):raise ValueError('Recording shorter than alignment reference')
    # Cross-correlation of signed waveforms, retains exact source sample grid.
    corr=correlate(x,y,mode='valid',method='fft')
    pos=int(np.argmax(np.abs(corr)))
    segment=x[pos:pos+len(y)]
    gain=float(np.dot(segment,y)/(np.dot(segment,segment)+1e-30))
    normalized=segment*gain
    similarity=float(np.dot(normalized,y)/(np.linalg.norm(normalized)*np.linalg.norm(y)+1e-30))
    return normalized,pos,gain,similarity

def auto_trim(x,threshold_db=-38,padding_ms=32):
    # Sliding 20ms RMS, with explicit sample-domain padding.
    win=150
    energy=np.convolve(x*x,np.ones(win)/win,'same')
    rms=np.sqrt(energy)
    ref=max(float(np.max(rms)),1e-10)
    active=np.flatnonzero(rms>ref*(10**(threshold_db/20)))
    if not len(active):return x,0
    pad=round(padding_ms*SR/1000)
    start=max(0,int(active[0])-pad)
    end=min(len(x),int(active[-1])+pad+1)
    return x[start:end],start

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--align-to',help='Canonical evaluation WAV to align and RMS-match (private test only)')
    p.add_argument('--start-samples',type=int,default=None)
    p.add_argument('--samples',type=int,default=None,help='Exact resulting length in samples')
    p.add_argument('--peak',type=float,default=0.90,help='Peak normalization target, 0..1; set 0 to disable')
    p.add_argument('--threshold-db',type=float,default=-38)
    p.add_argument('--pad-ms',type=float,default=32)
    p.add_argument('--no-trim',action='store_true')
    args=p.parse_args()
    x=decode_ffmpeg(args.input)
    if args.align_to:
        y,sr=sf.read(args.align_to,dtype='float64');assert sr==SR and y.ndim==1
        x,start,gain,corr=find_segment(x,y)
    elif args.start_samples is not None:
        start=args.start_samples
        x=x[start:]
        gain,corr=1.0,None
    elif args.no_trim:
        start=0;gain,corr=1.0,None
    else:
        x,start=auto_trim(x,args.threshold_db,args.pad_ms)
        gain,corr=1.0,None
    if args.samples is not None:
        length=args.samples
        if len(x)<length:x=np.pad(x,(0,length-len(x)))
        x=x[:length]
    elif not args.align_to:
        # Whole multiples of 64 let encoder use exact 8.533ms frames.
        length=max(64,(len(x)+63)//64*64)
        x=np.pad(x,(0,length-len(x)))
    if not args.align_to and args.peak>0:
        peak=float(np.max(np.abs(x)))
        if peak>1e-10: x=x*(args.peak/peak)
    x=np.clip(x,-1,1)
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    sf.write(out,x,SR,subtype='PCM_16')
    report={'input':str(args.input),'wav':str(out),'sample_rate':SR,'samples':len(x),
            'duration_seconds':len(x)/SR,'start_sample':start,'gain':gain,
            'correlation_to_reference':corr,'peak':float(np.max(np.abs(x)))}
    out.with_suffix('.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()

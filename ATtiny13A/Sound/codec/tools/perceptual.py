"""Perceptual multi-reference objective for LPC2->tiny analysis-by-synthesis.
Uses the user-provided speech and an optional LPC2 Improved reference render.
All metrics are evaluations on digitally rendered PCM, not listening tests.
"""
from pathlib import Path
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly, stft
from pystoi import stoi

FS=7500

def load_wav(path):
    x,sr=sf.read(path,always_2d=True,dtype='float64')
    x=x.mean(axis=1)
    if sr!=FS:
        import math
        d=math.gcd(sr,FS)
        x=resample_poly(x,FS//d,sr//d)
    return x

def lpc2_pcm(path):
    # LPC2 Improved v11 decoded PCM is signed little-endian 16-bit at 8kHz.
    a=np.fromfile(path,dtype='<i2').astype('float64')/32768
    return resample_poly(a,15,16)

class Evaluator:
    def __init__(self,original,lpc2=None):
        self.original=np.asarray(original,np.float64)
        self.lpc2=np.asarray(lpc2 if lpc2 is not None else original,np.float64)
        self.size=len(self.original)
        self.nperseg=512;self.hop=128
        f,t,_=stft(self.original,FS,nperseg=512,noverlap=384,boundary='zeros',padded=True)
        edges=700*(np.expm1(np.linspace(np.log1p(125/700),np.log1p(3490/700),27)))
        ws=[]
        for lo,mid,hi in zip(edges[:-2],edges[1:-1],edges[2:]):
            w=np.maximum(0,np.minimum((f-lo)/(mid-lo),(hi-f)/(hi-mid)))
            w=w/max(w.sum(),1e-6)
            ws.append(w)
        self.filter=np.asarray(ws)
        self.ref=self._features(self.original)
        self.teacher=self._features(self.lpc2)
        weights=np.sqrt(np.mean(self.ref[0]**2,axis=0))**0.65
        weights=np.maximum(weights,0)
        weights[weights < weights.max()*0.08]=0
        self.weights=weights/(weights.sum()+1e-30)

    def _features(self,wave):
        a=np.asarray(wave,dtype=np.float64)[:self.size]
        if len(a)<self.size:a=np.pad(a,(0,self.size-len(a)))
        _,_,st=stft(a,FS,nperseg=self.nperseg,noverlap=self.nperseg-self.hop,boundary='zeros',padded=True)
        bands=self.filter@np.abs(st)
        logs=np.log(np.maximum(1e-6,bands))
        norm=logs-logs.mean(axis=0,keepdims=True)
        energy=np.log(np.maximum(1e-6,np.sqrt(np.mean(bands**2,axis=0))))
        return bands,norm,energy

    def metrics(self,samples,fast=False):
        y=np.asarray(samples,dtype=np.float64)[:self.size]
        if np.max(np.abs(y))>2: y=y/128.0
        _,spec,energy=self._features(y)
        w=self.weights
        dd=np.abs(spec-self.ref[1])
        dt=np.abs(spec-self.teacher[1])
        mel=float(w@np.mean(np.sqrt(dd*dd+0.05**2),axis=0))
        teacher=float(w@np.mean(np.sqrt(dt*dt+0.05**2),axis=0))
        center=energy-self.ref[2]
        center-=float(w@center)
        env=float(w@np.abs(center))
        step=np.abs(np.diff(samples.astype(np.int16)))
        click60=int(np.sum(step>=60))
        click48=int(np.sum(step>=48))
        maxstep=int(step.max()) if len(step) else 0
        st=float(stoi(self.original[:len(y)],y,FS,extended=False)) if not fast else 0.0
        return {'stoi':st,'mel_original':mel,'mel_lpc2':teacher,'envelope':env,
                'clicks_60':click60,'clicks_48':click48,'max_step':maxstep}

    def fitness(self,met,weights=None):
        ww=weights or {'stoi':2.1,'original':0.85,'lpc2':0.6,'envelope':0.14,'clicks':0.0008}
        return (ww['stoi']*met['stoi']-ww['original']*met['mel_original']-
                ww['lpc2']*met['mel_lpc2']-ww['envelope']*met['envelope']-
                ww['clicks']*met['clicks_48'])

if __name__=='__main__':
    from model_lite import render
    p=Path(__file__).parent
    x=load_wav(p/'references/original_reference.wav');teacher=lpc2_pcm(p/'references/lpc2_improved_reference.s16le')
    z=np.load(p/'firmware/best_parameters.npz')
    ev=Evaluator(x,teacher)
    sig=render(z['K'].astype('int64'),z['P'].astype('int64'),z['E'].astype('int64'),87*256)
    print('baseline',ev.metrics(sig),'teacher (self):',ev.metrics(np.rint(teacher[:len(x)]*128).astype('int16')))

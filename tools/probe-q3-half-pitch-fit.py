from pathlib import Path
import importlib.util,sys,json,time
import numpy as np
import soundfile as sf
import argparse
p=argparse.ArgumentParser(description='Fit a half-sample pitch research model against the full original')
for name in ('reference','model','output'):p.add_argument('--'+name,type=Path,required=True)
a=p.parse_args()
root=Path(__file__).resolve().parents[1]
a.output.mkdir(parents=True,exist_ok=True)
def module(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
fit=module('half_pitch_fitting',root/'tools/refine-q3-adaptive.py')
phase=module('half_pitch_render',root/'tools/build-q3-half-pitch-probe.py')
from types import SimpleNamespace
frac=SimpleNamespace(render=phase.oracle(a.output))
x,sr=sf.read(a.reference);assert sr==7500 and x.ndim==1
f,d,b,_=fit.probe.builder.load_model(a.model)
f,b,_=fit.select(f,d,b)['frames'],fit.select(f,d,b)['book'],None
flags=np.zeros(len(f),np.uint8)
a,c=frac.render(f,d,b,flags);z,zc=fit.probe.codec.render(f,d,b)
assert np.array_equal(a,z) and np.array_equal(c,zc)
spectral=fit.probe.search.SpectrogramObjective(x);tracks=fit.probe.HarmonicTrackObjective(x)
def score(frames,halves):
 payload=len(fit.probe.codec.pack_stream(frames,d))+int(np.sum((halves>0)&(frames[:,0]<=63)&(d!=192)))
 if payload>649:return None
 pcm,counts=frac.render(frames,d,b,halves);raw=pcm.astype(np.int16)-128
 if np.any(counts) or abs(raw).max()>115 or np.any(abs(np.diff(raw))>=48):return None
 y=raw/128
 q=dict(stoi=float(fit.probe.search.stoi(x,y,7500)),**spectral.evaluate(y),raw_mean=float(y.mean()),stream_bytes=payload)
 q['harmonic_metrics']=tracks.evaluate(y)
 return q
energy=lambda q:q['spectrogram_loss']+6*(.9-q['stoi'])+.1*q['harmonic_metrics']['harmonic_track_loss']
initial=best=score(f,flags);history=[];start=time.perf_counter()
for epoch in range(2):
 for i in np.flatnonzero((f[:,0]>1)&((f[:,1]&15)>0)):
  for delta in (-1,0,1):
   for half in (0,1):
    if not 1<=int(f[i,0])+delta<=126:continue
    g,fl=f.copy(),flags.copy();g[i,0]=int(f[i,0])+delta;fl[i]=half
    q=score(g,fl)
    if q and q['stoi']>=initial['stoi'] and q['spectrogram_loss']<=initial['spectrogram_loss'] and energy(q)<energy(best)-1e-12:
     f,flags,best=g,fl,q;history.append(dict(frame=int(i),period=int(g[i,0]),half=half,score=q))
 print(json.dumps(dict(epoch=epoch,accepted=len(history),stoi=best['stoi'],spectrum=best['spectrogram_loss'],half_frames=int(np.sum(flags)),elapsed=time.perf_counter()-start)),flush=True)
pcm,counts=frac.render(f,d,b,flags)
best['estoi']=fit.probe.deterministic_estoi(x,(pcm.astype(float)-128)/128,7500)
fit.probe.save(a.output/'report.json',dict(before=initial,after=best,history=history,frames=f.tolist(),durations=d.tolist(),pulsebook=b.tolist(),fractions=flags.tolist(),estimated_extra_code_bytes=24,avr_verified=False))

fit.probe.save(a.output/'model.json',dict(schema='q3-half-pitch-probe-v1',sample_rate=7500,reference_sha256=fit.probe.sha(a.reference),frames=f.tolist(),durations=d.tolist(),pulsebook=b.tolist(),fractions=flags.tolist()))

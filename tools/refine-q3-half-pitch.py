from pathlib import Path
import importlib.util,sys,json,time
import numpy as np
import soundfile as sf
import argparse
p=argparse.ArgumentParser(description='Polish a half-pitch model with full-clip spectral/recognition guards')
for name in ('reference','model','limits-report','output'):p.add_argument('--'+name,type=Path,required=True)
p.add_argument('--evaluations',type=int,default=4500)
a=p.parse_args()
root=Path(__file__).resolve().parents[1]
def module(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
fit=module('half_coordinate_api',root/'tools/refine-q3-adaptive.py')
phase=module('qualified_half_api',root/'tools/build-q3-half-pitch-probe.py')
out=a.output;out.mkdir(parents=True,exist_ok=True)
render=phase.oracle(out)
model=json.loads((a.model).read_text())
f=np.array(model['frames'],np.uint8);d=np.array(model['durations'],np.uint16);b=np.array(model['pulsebook'],np.int8);flags=np.array(model['fractions'],np.uint8)
x,sr=sf.read(a.reference);assert sr==7500 and x.ndim==1;spectral=fit.probe.search.SpectrogramObjective(x);tracks=fit.probe.HarmonicTrackObjective(x)
limits=json.loads((a.limits_report).read_text())['finalists']['guarded']
energy=lambda q:q['spectrogram_loss']+6*(.9-q['stoi'])
def score(state,halves,ceiling=None):
 layout=fit.select(state.frames,state.durations,state.book);state.frames,state.book=layout['frames'],layout['book']
 payload=phase.pack(state.frames,state.durations,state.book,halves)
 flash=(layout['code_bytes']+24+len(payload)-layout['prefix_bytes']+2)&~1
 if flash>1024:return None
 pcm,counts=render(state.frames,state.durations,state.book,halves);raw=pcm.astype(np.int16)-128
 if np.any(counts) or abs(raw).max()>115 or np.any(abs(np.diff(raw))>=48):return None
 y=raw/128;q=dict(stoi=float(fit.probe.search.stoi(x,y,7500)),**spectral.evaluate(y),raw_mean=float(y.mean()),stream_bytes=len(payload),flash_bytes=flash)
 if ceiling is not None and (energy(q)>=ceiling or q['stoi']<initial['stoi'] or q['spectrogram_loss']>limits['spectrogram_loss'] or abs(q['raw_mean'])>abs(limits['raw_mean'])):return None
 q['estoi']=fit.probe.deterministic_estoi(x,y,7500)
 detail=tracks.details(y);q['harmonic_metrics']=detail['metrics'];q['partial_violation_power']=fit.probe.check_partial_bounds(detail,duration_seconds=len(y)/7500)['violating_reference_power_fraction']
 if ceiling is not None:
  h=q['harmonic_metrics'];hlim=limits['harmonic_metrics']
  if q['estoi']<initial['estoi'] or any(h[k]>hlim[k] for k in ['harmonic_track_loss','frequency_error_cents','level_error_db']):return None
  if h['missing_reference_energy']>.19 or q['partial_violation_power']>limits['matched_strict_5db_bounds']['violating_reference_power_fraction']:return None
 return q
state=fit.probe.search.State(f,d,b,False,1);initial=best=score(state,flags);history=[];start=time.perf_counter();evaluated=0;seen=set()
for epoch in range(2):
 actions=fit.actions(state)
 if epoch%2:actions.reverse()
 for action in actions:
  if evaluated>=a.evaluations:break
  candidate=fit.apply(state,action)
  if candidate is None:continue
  identity=fit.key(candidate)
  if identity in seen:continue
  seen.add(identity);evaluated+=1;q=score(candidate,flags,energy(best)-1e-12)
  if q:
   state,best=candidate,q;history.append(dict(evaluation=evaluated,action=list(action),score=q))
  if evaluated%500==0:
   fit.probe.save(out/'progress.json',dict(evaluated=evaluated,accepted=len(history),score=best,elapsed=time.perf_counter()-start))
   print(json.dumps(dict(evaluated=evaluated,accepted=len(history),stoi=best['stoi'],spectrum=best['spectrogram_loss'])),flush=True)
 if evaluated>=a.evaluations:break
model.update(frames=state.frames.tolist(),durations=state.durations.tolist(),pulsebook=state.book.tolist())
fit.probe.save(out/'model.json',model);fit.probe.save(out/'report.json',dict(before=initial,after=best,evaluated=evaluated,accepted=len(history),history=history,elapsed_seconds=time.perf_counter()-start,hardware_tested=False))

#!/usr/bin/env python3
"""LP20 v9 offline encoder. Frozen multi-model Pareto selection, optional
same-rate token refinement and fractional duty optimization. ROM-only Z80.
Metrics are evaluated against the normalized input, not previous encodings.
"""
import argparse, json, sys, math, tempfile, shutil, uuid
from pathlib import Path
import numpy as np
import study as s
import fixed_rate, fractional
from pack_h10 import pack,unpack
from build_h10 import build
from pack_fractional import pack as fpack,unpack as funpack
from build_fractional import build as fbuild

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('wav');p.add_argument('--out',required=True);p.add_argument('--models',nargs='+',default=['pooled','single','balanced','class','rounded']);p.add_argument('--bps',type=float,default=5000.);p.add_argument('--refine',type=int,default=0,help='number of fixed-token-count Pareto sweeps');p.add_argument('--fractional',action='store_true');p.add_argument('--strict-rate',action='store_true',help='never increase bytes relative to initial valid model');p.add_argument('--rom',action='store_true');a=p.parse_args()
 out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=True);t=s.load(a.wav);assert len(t)>=s.FS and np.all(np.isfinite(t)), 'Need >= 1s non-silent WAV';best=None;log=[];budget=None
 for name in a.models:
  path=Path(name) if Path(name).is_file() else s.ROOT/'models'/(name+'_model.npz');d=dict(np.load(path),target=t);idx,y,m=s.encode_trial(d,path.stem,lam=30.,beam=1,targetbps=a.bps,tries=10,save_output=False)
  ok=not m['overflow'] and abs(m['kbps']*1000-a.bps)<=a.bps*.01 and all(math.isfinite(m[k]) for k in ('snr','stoi'))
  if budget is None and ok:budget=len(idx)
  if a.strict_rate and budget is not None:ok=ok and len(idx)<=budget
  accept=ok and (best is None or (m['snr']>=best[3]['snr'] and m['stoi']>=best[3]['stoi'] and (m['snr']>best[3]['snr'] or m['stoi']>best[3]['stoi'])))
  m=dict(m,model=path.stem,valid=bool(ok),accepted=bool(accept));log.append(m)
  if accept:best=d,idx,y,m
 (out/'candidates.json').write_text(json.dumps(log,indent=2));assert best is not None,'No valid candidate at requested rate'
 d,idx,y,m=best;tag='encode_'+uuid.uuid4().hex[:12];work=s.save(tag,d,idx,y,m)
 try:
  if a.refine>0:
   fixed_rate.run(work/'training.npz',tag+'_refine',a.refine);work=s.ROOT/'results'/(tag+'_refine')
  normal=work;isfrac=False
  if a.fractional:
   fractional.run(work/'training.npz',tag+'_fractional');fwork=s.ROOT/'results'/(tag+'_fractional');fd=np.load(fwork/'training.npz');isfrac=bool(np.any(fd['ww10']%10));
   if isfrac:work=fwork
  for f in ('training.npz','pwm.wav','reference.wav','metrics.json'):shutil.copy2(work/f,out/f)
  q=np.load(out/'training.npz');metrics=json.loads((out/'metrics.json').read_text());metrics['selected_model']=m['model'];metrics['fractional']=isfrac
  if isfrac:
   fpack(out/'training.npz',out/'sound.lp10f');yr=funpack(out/'sound.lp10f',out/'repacked.npz');assert np.array_equal(yr,q['y']);sf=out/'sound.lp10f'
  else:
   pack(out/'training.npz',out/'sound.lp10c');yr=unpack(out/'sound.lp10c',out/'repacked.npz');assert np.array_equal(yr,q['y']);sf=out/'sound.lp10c'
  if a.rom:
   try:(fbuild if isfrac else build)(out/'repacked.npz',out/'decoder',256,10,61)
   except ValueError as exc:
    # If fractional schedule is larger than 64 KiB, retain the integer result.
    if not isfrac:raise
    print('Fractional ROM build rejected:',exc,'; using integer baseline',file=sys.stderr)
    for f in ('training.npz','pwm.wav','reference.wav','metrics.json'):shutil.copy2(normal/f,out/f)
    q=np.load(out/'training.npz');metrics=json.loads((out/'metrics.json').read_text());metrics['selected_model']=m['model'];metrics['fractional']=False;sf.unlink();sf=out/'sound.lp10c';pack(out/'training.npz',sf);yr=unpack(sf,out/'repacked.npz');assert np.array_equal(yr,q['y']);build(out/'repacked.npz',out/'decoder',256,10,61)
  metrics.update(container_bytes=sf.stat().st_size,container_kbps=sf.stat().st_size*8/(len(t)/s.FS)/1000);(out/'metrics.json').write_text(json.dumps(metrics,indent=2));print('SELECTED',json.dumps(metrics))
 finally:
  for suf in ('','_refine','_fractional'):
   shutil.rmtree(s.ROOT/'results'/(tag+suf),ignore_errors=True)
if __name__=='__main__':main()

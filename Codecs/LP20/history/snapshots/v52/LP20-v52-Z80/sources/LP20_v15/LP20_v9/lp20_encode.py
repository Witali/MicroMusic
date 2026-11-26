#!/usr/bin/env python3
"""Encode new WAV with frozen LP20 dictionaries, selecting only nondecreasing
SNR and STOI relative to the first valid candidate. No on-device training.
The baseline is the first candidate, not a quality guarantee against other codecs.
"""
import argparse,json,math,subprocess,sys
from pathlib import Path
import numpy as np
import study as s
from pack_h10 import pack,unpack
from build_h10 import build

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('wav');p.add_argument('--out',required=True);p.add_argument('--models',nargs='+',default=[str(s.ROOT/(m+'_model.npz')) for m in ('single','pooled','balanced')]);p.add_argument('--bps',type=float,default=5000.);p.add_argument('--lam',type=float,default=30.);p.add_argument('--beam',type=int,default=1);p.add_argument('--rom',action='store_true');a=p.parse_args();out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
 t=s.load(a.wav);assert len(t)>=s.FS,'Need >= 1 second of audio';assert np.all(np.isfinite(t)),'Invalid audio (possibly silent)';best=None;log=[]
 for model in a.models:
  d=dict(np.load(model));d['target']=t;name=Path(model).stem
  idx,y,m=s.encode_trial(d,name,lam=a.lam,beam=a.beam,targetbps=a.bps,tries=10,save_output=False)
  m['model']=name;ok=m['overflow']==0 and abs(m['kbps']*1000-a.bps)<=a.bps*.015 and math.isfinite(m['snr']) and math.isfinite(m['stoi']);m['valid']=bool(ok)
  if ok and (best is None or (m['snr']>=best[3]['snr'] and m['stoi']>=best[3]['stoi'] and (m['stoi']>best[3]['stoi'] or m['snr']>best[3]['snr']))):best=(d,idx,y,m);m['accepted']=True
  else:m['accepted']=False
  log.append(m)
 (out/'candidates.json').write_text(json.dumps(log,indent=2));assert best is not None,'No valid candidate at target bitrate'
 d,idx,y,m=best;dd={k:d[k] for k in ('target','a','tb','bk','bm','lens','ww')};dd.update(idx=idx,y=y,bits=10);np.savez(out/'training.npz',**dd)
 pack(out/'training.npz',out/'sound.lp10c');yr=unpack(out/'sound.lp10c',out/'repacked.npz');assert np.array_equal(yr,y)
 _,lut,_=s.lut_for(d['ww']);r=s.resample_poly(t/127,768,125);g=.98/max(abs(r));z=s.nu.render_actual(lut[y+512],256,10)/.875*128/127;s.e.wav(out/'reference.wav',r*g);s.e.wav(out/'pwm.wav',z*g*min(1,.98/(max(abs(z))*g)));m['packed_bytes']=(out/'sound.lp10c').stat().st_size;m['packed_kbps']=m['packed_bytes']*8/(len(t)/s.FS)/1000;(out/'metrics.json').write_text(json.dumps(m,indent=2))
 if a.rom:build(out/'repacked.npz',out/'decoder',256,10,61)
 print('SELECTED',json.dumps(m))
if __name__=='__main__':main()

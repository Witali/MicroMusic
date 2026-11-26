#!/usr/bin/env python3
"""Use two new symmetric pairs, preserving original nominal levels and PWM patterns."""
from study50 import *

def make_map(ww,meta):
 # Old nominal mapping followed by nearest achievable amplitude. Return 1024 indices.
 keys=np.array(sorted(map(int,meta['patterns'])));p=np.array([meta['patterns'][str(k)] for k in keys]);nom=np.arange(-512,512)*1120/512+1280;ix=np.argmin(abs(nom[:,None]-keys[None,:])+1e-9*abs(keys[None,:]-1280),axis=1);act=p[ix].sum(1);u=np.unique(act);lv=(u-1280)*128/1120
 # Renderer rounds to 10-bit then uses nearest actual level (with clamping to old nominal interval). This is equivalent to mapping rounded inputs to lv for 10-bit, but floating input is used in threshold lookup.
 return keys,p,ix

def run(c):
 d,m,r,z=load(c);o='second' if c=='first' else 'first';dt,mt,rt,zt=load(o);lib=library();out=ROOT/c;old={int(k):v for k,v in m['patterns'].items()};base={k:v for k,v in old.items() if k not in (160,2400)};assert len(base)==59
 # Use cross-recording quantizer error in internal amplitude domain, not current test reference.
 from rd44 import levels
 _,q0=levels(dt,mt);x=np.arange(-512,512)/4;cnt=np.bincount(np.clip(np.rint(zt*4).astype(int)+512,0,1023),minlength=1024).astype(float);cnt/=cnt.sum();cnt=.99*cnt+.01/1024
 def ev(keys,pats):
  gg=np.array(keys);aa=np.array([sum(pats[k]) for k in gg]);ix=np.argmin(abs((x*1120/128+1280)[:,None]-gg[None,:])+1e-9*abs(gg[None,:]-1280),axis=1);return float(np.sum(cnt*(x-(aa[ix]-1280)*128/1120)**2)),ix
 # Maintain existing nominal values to avoid losing the encoder's original threshold tuning.
 for it in range(2):
  best=None
  for t in sorted(lib):
   if t<=1280 or any(abs(t-k)<9 or abs(2560-t-k)<9 for k in base) or t in [sum(v) for v in base.values()]:continue
   b=dict(base);b[t]=lib[t];b[2560-t]=lib[2560-t];keys=sorted(b);e,ix=ev(keys,b)
   if np.ptp(ix.reshape(256,4),axis=1).max()>1:continue
   if best is None or e<best[0]:best=(e,t,b)
  if best is None:break
  base=best[2];print(c,'add pair',best[:2],flush=True)
 nd=dict(d,ww10=np.array(sorted(base)));nm=dict(m,patterns={str(k):v for k,v in base.items()});w=render(z,nd,nm);a=measure(r,w);b=measure(r,render(d['target'],nd,nm));np.savez(out/'63-augment.npz',sums=np.array(sorted(base)),patterns=np.array([base[k] for k in sorted(base)]),nominal=True);wavfile.write(out/'63-augment.wav',48000,w);row=dict(clip=c,profile='63-augment',levels=len(base),legacy_lut=True,**a,direct_snr_db=b['snr_db'],direct_peak_pct=b['peak_error_pct'],direct_quiet_snr_db=b['quiet_snr_db']);print(c,'63-augment',row,flush=True)
 (out/'augment.json').write_text(json.dumps(row,indent=2))
if __name__=='__main__':run(sys.argv[1])

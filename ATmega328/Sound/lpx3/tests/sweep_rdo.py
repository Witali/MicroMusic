import sys, subprocess
from pathlib import Path
import json, numpy as np, soundfile as sf
from pystoi import stoi
R=Path(__file__).resolve().parents[1];S=R.parent/'private_inputs'
sys.path.insert(0,str(R/'tools'))
from pack_lpx3_avr import transcode
report=[]
for clip in ['vinni','xtuj-ntt','ne-otv']:
 p=S/clip;orig,sr=sf.read(p/'original.wav');lp=np.fromfile(p/'pcm_f32.bin',dtype='<f4')
 orig_stoi=stoi(orig,lp,8000)
 for qbits in (8,10):
  for tol in (None,0.002,0.004,0.006,0.008,0.012):
   tag='legacy' if tol is None else '%03d'%int(tol*1000)
   out=p/f'{clip}_q{qbits}_{tag}.l3av';pcm=out.with_suffix('.pcm8')
   meta=transcode(p/'voice_v3_3bit.lpx3',out,coeff_bits=qbits,rdo_tolerance=tol)
   subprocess.run([str(R/'build/decode_host'),str(out),str(pcm)],check=True,stdout=subprocess.DEVNULL)
   y=(np.fromfile(pcm,dtype='u1').astype(np.float32)-128)/127
   v=stoi(orig,y,8000)
   e=float(np.sqrt(np.mean((y-lp)**2)));meta.update({'clip':clip,'stoi':round(float(v),6),'delta_stoi':round(float(v-orig_stoi),6),'rms_vs_lpx3':round(e,6),'tag':tag})
   print(clip,'q'+str(qbits),'tol',tol,'n',out.stat().st_size,'deltaSTOI',round(v-orig_stoi,5),'rms',round(e,5),'2bit',meta['bits2_blocks'],flush=True)
   report.append(meta)
(R/'reports/vbr_sweep.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))

#!/usr/bin/env python3
"""Create private audio demos, reusable source archive, public synthetic demo.
External copyright audio samples are kept OUT of the code-only archive.
"""
from pathlib import Path
import numpy as np,soundfile as sf,json,zipfile,shutil
from build_hq import compile_one
ROOT=Path(__file__).resolve().parent
RELEASE=Path('/mnt/data');NAMES=['chego','otvechaesh','vinni']
manifest=json.loads((ROOT/'manifest.json').read_text())
def normalized(x):
 x=x.astype(np.float32)
 rms=float(np.sqrt(np.mean(x*x)))
 peak=float(np.max(np.abs(x)))
 return np.clip(x*min(.17/max(.001,rms),.87/max(.001,peak)),-1,1)
for n in NAMES:
 a,sr=sf.read(ROOT/'references'/n/'original.wav');lp,s2=sf.read(ROOT/'references'/n/'lpx3.wav');assert sr==s2==7500
 base=np.frombuffer((ROOT/'samples'/n/'baseline_pcm.raw').read_bytes(),np.uint8).astype(np.float32)/128-1
 hq=np.frombuffer((ROOT/'samples'/n/'avr_pcm.raw').read_bytes(),np.uint8).astype(np.float32)/128-1
 assert len(a)==len(lp)==len(base)==len(hq)
 sf.write(ROOT/'samples'/n/'avr_preview.wav',hq,sr,subtype='PCM_16')
 spacer=np.zeros(int(.26*sr),np.float32)
 ab=np.concatenate([normalized(x) if i==3 else np.r_[normalized(x),spacer] for i,x in enumerate([a,base,hq,lp])])
 sf.write(ROOT/'samples'/n/'AB_original_VBR2_HQ_LPX3.wav',ab,sr,subtype='PCM_16')

# A synthetic sample showing that the assembly/format can be compiled without proprietary recordings.
f=[];d=[]
for i in range(32):
 pitch=0 if i%11==0 else (20+int(i*3)%26)
 gain=min(15,2+int(abs(np.sin(i*.3))*9))
 mode=i%4
 coeff=[0x79,0x7B,0x88,0x88] if i%4==0 else [0x69,0x8A,0x88,0x88]
 f.append([pitch,(mode<<4)|gain,*coeff])
 d.append([256,128,64,128][i%4])
ff=np.asarray(f,np.uint8);dd=np.asarray(d,np.uint16)
record=compile_one('demo',ff,dd)
manifest['demo']=record
sf.write(ROOT/'samples'/'demo'/'avr_preview.wav',(ROOT/'samples'/'demo'/'expected_pcm.raw').read_bytes() and (np.frombuffer((ROOT/'samples'/'demo'/'expected_pcm.raw').read_bytes(),np.uint8).astype(np.float32)-128)/128,7500,subtype='PCM_16')
(ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False))

# Easy links at flat root.
shutil.copy2(ROOT/'index.html',RELEASE/'MicroMusic_MiniLPC_HQ.html')
all_names=NAMES
private=RELEASE/'MicroMusic_MiniLPC_HQ_Private.zip';public=RELEASE/'MicroMusic_MiniLPC_HQ_Code.zip'

def include_private(p):
 rel=p.relative_to(ROOT)
 if p.suffix in {'.pyc','.o'} or '__pycache__' in p.parts:return False
 if p.name in {'offline_player_check.js','browser_test.py','refine_run.log','refine_round2.log','training_run.log'}:return False
 return True
with zipfile.ZipFile(private,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for p in sorted(ROOT.rglob('*')):
  if p.is_file() and include_private(p):z.write(p,'MicroMusic_MiniLPC_HQ/'+str(p.relative_to(ROOT)))

allowed_root={'README.md','build_hq.py','model.py','vbr_codec.py','quality.py','train_hq.py','refine_hq.py','avr_emulator.js','verify.js','make_player.py','make_release.py','requirements.txt','ui_smoke.js','run_all.sh','build_demo.py','demo_verify.js'}
with zipfile.ZipFile(public,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for name in sorted(allowed_root):
  p=ROOT/name
  if p.exists():z.write(p,'MicroMusic_MiniLPC_HQ/'+name)
 for name in ['chego_base.S']:
  z.write(ROOT/'baselines'/name,'MicroMusic_MiniLPC_HQ/baselines/'+name)
 for fn in ['firmware.S','firmware.bin','firmware.hex','speech.hq','expected_pcm.raw','avr_preview.wav']:
  p=ROOT/'samples'/'demo'/fn;z.write(p,'MicroMusic_MiniLPC_HQ/samples/demo/'+fn)
print('Release archives:',private,private.stat().st_size,public,public.stat().st_size)

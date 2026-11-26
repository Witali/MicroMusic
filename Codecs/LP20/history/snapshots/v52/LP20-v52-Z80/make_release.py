#!/usr/bin/env python3
"""Transcode LP4V on the host, verify exact PWM output and build ROM pages.
Usage: python make_release.py /path/to/extracted/v51 archive siblings
Requires existing LP20-v51/first,second and LP20-v44,45,50, etc. For normal
index-only builds use build_pwm.py directly. No Z80 DCT decoder is claimed.
"""
from pathlib import Path
import os,sys,json,subprocess,csv,shutil
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
import numpy as np
from scipy.io import wavfile
from build_pwm import build,ROOT
B=Path(sys.argv[1]).resolve();sys.path[:0]=[str(B/'LP20-v50'),str(B/'LP20-v45')]
from adaptive45 import decode_v
from study50 import lut,render_raw,measure
from rd44 import metrics

def render_widths(widths,d):
 raw=(np.clip(widths[:,:,None]-np.arange(4)*80,0,80).astype(np.float32)*2/80-1).ravel()
 return render_raw(raw,d)

def audit(binfile,expected):
 return json.loads(subprocess.check_output([str(ROOT/'test_pwm'),str(binfile),str(expected)],text=True))

def main():
 p=np.load(ROOT/'pwm255.npy');l=lut(p);rows=[];page_rows=[]
 # Round-trip exact software reconstruction; each ROM subsequently emits every width exactly.
 for clip in ('first','second'):
  b=B/'LP20-v51'/clip;out=ROOT/'v51-preview'/clip;out.mkdir(parents=True,exist_ok=True);d=dict(np.load(B/'LP20-v44/input'/clip/'model.npz'));ref=wavfile.read(b/'reference.wav')[1];z,frames,_=decode_v(b/'Quality.lp4v',(b/'book.bin').read_bytes());idx=l[np.clip(np.rint(z*4).astype(int)+512,0,1023)].astype(np.uint8);np.save(out/'indices.npy',idx);(out/'indices.bin').write_bytes(idx.tobytes());wv=render_widths(p[idx],d);assert np.array_equal(wv,wavfile.read(b/'Quality.wav')[1]);wavfile.write(out/'Quality.wav',48000,wv)
  shutil.copy2(b/'Quality.lp4v',out/'Quality.lp4v');shutil.copy2(b/'book.bin',out/'book.bin');shutil.copy2(b/'dds.bin',out/'dds.bin');shutil.copy2(b/'reference.wav',out/'reference.wav')
  for page,a in enumerate(range(0,len(idx),60000),1):
   j=idx[a:a+60000];prefix=out/f'part{page}';core=build(j,prefix);test=audit(prefix.with_suffix('.bin'),prefix.with_suffix('.widths'));(out/f'part{page}-test.json').write_text(json.dumps(test,indent=2));m=json.loads(prefix.with_suffix('.json').read_text());page_rows.append(dict(clip=clip,part=page,start_sample=a,samples=len(j),start_s=a/7812.5,duration_s=len(j)/7812.5,core_bytes=m['core_bytes_including_eos'],occupied_rom=m['occupied_rom'],**{k:test[k] for k in ('io_writes','memory_writes','cycles_per_sample','cycles_per_period')}));print('PASS',clip,page,test,flush=True)
  # First part audio; exact continuous original-model slice, not board capture.
  wavfile.write(out/'part1-preview.wav',48000,wv[:round(min(60000,len(idx))*48000/7812.5)])
  m=metrics(ref,wv);rows.append(dict(profile='v51-preview',clip=clip,core_bytes=core+1,stream_bytes=len(idx),bitrate_kbps=62.5,lp4v_source_bytes=(b/'Quality.lp4v').stat().st_size,rom_parts=(len(idx)+59999)//60000,**m));print('Exact full audio confirmed',clip,m['snr_db'],m['peak_error_pct'],flush=True)
  # Independently measure legacy LPC images with 63 and 255 tables, using
  # the exact trace width mapping verified by the LPC emulator.
  for profile in ('native63','native255-experimental'):
   path=ROOT/profile/clip;m=json.loads((path/'decoder.json').read_text());model=dict(np.load(path/'model.npz'));width=np.load(path/'decoder.widths10.npy');pats=np.array([m['patterns'][str(int(i))] for i in np.unique(width)]);widths=pats[np.searchsorted(np.unique(width),width)];y=render_widths(widths,model);wavfile.write(path/'output.wav',48000,y);np.save(path/'emulated_widths.npy',widths.astype(np.uint16));ref=wavfile.read(B/'LP20_v39/release'/clip/'reference.wav')[1];v=metrics(ref,y);r=dict(profile=profile,clip=clip,core_bytes=m['used']-m['stream_bytes'],stream_bytes=m['stream_bytes'],bitrate_kbps=m['stream_bytes']*8*7812.5/len(width)/1000,occupied_rom=m['used'],rom_parts=1,**v);rows.append(r);print('METRICS',profile,clip,r['snr_db'],r['peak_error_pct'],flush=True)
  # IDCT workload: for each decoded sample, count how many nonzero terms
  # a literal sparse direct IDCT would require. Not a universal lower bound.
  n=np.array([len(f[-1]) for f in frames]);k=np.array([np.count_nonzero(f[-1]) for f in frames]);work=dict(samples=len(idx),blocks=len(frames),block_sizes={str(int(v)):int(np.sum(n==v)) for v in np.unique(n)},mean_nonzero_per_block=float(k.mean()),max_nonzero=int(k.max()),mean_direct_terms_per_sample=float(n@k/n.sum()),max_block_terms=int(np.max(n*k)),max_block_samples=int(n.max()),nominal_cycles_per_sample=2560,cycles_after_edges=2368);(out/'idct-workload.json').write_text(json.dumps(work,indent=2));print('WORKLOAD',clip,work,flush=True)
 for name,data in [('comparison',rows),('rom-pages',page_rows)]:
  keys=list(dict.fromkeys(k for r in data for k in r));f=open(ROOT/(name+'.csv'),'w',newline='');w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(data);f.close()
if __name__=='__main__':main()

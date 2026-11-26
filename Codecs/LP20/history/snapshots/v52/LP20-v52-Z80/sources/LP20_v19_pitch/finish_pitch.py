#!/usr/bin/env python3
"""Build and verify the existing ROM-only decoder with pitch-optimized tokens."""
from study_pitch import *
import subprocess
from build_context_fast import build
from pack_context import pack,unpack
V17=ROOT.parent/'LP20_v17_gain'
meta=json.loads((V18/'release/compact/decoder.json').read_text())
summary={}
for name in ('second','first'):
 p=ROOT/name;d=dict(np.load(p/'training.npz'));m=build(p/'training.npz',p/'decoder',period=320,grid=meta['grid'],alpha=.001)
 core=m['used']-m['stream_bytes'];assert core==14851
 v18=(V18/'release/compact/decoder.bin').read_bytes();bin=(p/'decoder.bin').read_bytes();assert bin[:core-1]==v18[:core-1], 'decoder code and tables changed'
 test=json.loads(subprocess.check_output([str(V17/'test_fast'),str(p/'decoder.bin'),str(p/'decoder.map'),str(p/'decoder.expected'),'320','8','0','16',str(p/'decoder.threads')],text=True));assert test['memory_writes']==0
 (p/'test.json').write_text(json.dumps(test,indent=2));sz=pack(d,m,p/'sound.lp10g');dd,mt=unpack(p/'sound.lp10g');assert np.array_equal(dd['y'],d['y']) and np.array_equal(dd['idx'],d['idx']);basefile=V18/'release/compact/sound.lp10g';s0=basefile.stat().st_size if name=='second' else pack(dict(np.load(p/'baseline_model.npz')),m,p/'baseline.lp10g');r=json.loads((p/'results.json').read_text());r.update(core_bytes=core,occupied_rom=m['used'],stream_kbps=len(d['idx'])*8*FS/len(d['y'])/1000,container_bytes=sz,baseline_container_bytes=s0,container_kbps=sz*8*FS/len(d['y'])/1000,core_identical_v18=True,**test);(p/'results.json').write_text(json.dumps(r,indent=2));summary[name]=r;print('FINAL',name,r['final'],{k:r[k] for k in ('core_bytes','stream_kbps','container_bytes','baseline_container_bytes','memory_writes')},flush=True)
r=json.loads((ROOT/'new_ru/results.json').read_text());r['stream_kbps']=r['stream_bytes']*8*FS/len(np.load(ROOT/'new_ru/training.npz')['y'])/1000;r['rom_test']='not built: original model has >256 excitation-bank pairs';summary['new_ru']=r;(ROOT/'summary.json').write_text(json.dumps(summary,indent=2))

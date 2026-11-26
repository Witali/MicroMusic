#!/usr/bin/env python3
"""Replace raw token stream in already verified ROM core, test exact output.
Reuses v20 timing/code/dictionary, no code modifications."""
import sys,struct,json,subprocess,hashlib,shutil
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'LP20_v20_study'))
from harmonic import np,model,decode,f,V18
from pack_context import pack,unpack
HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'LP20_v20_study'
CPU=HERE.parent/'LP20_v17_gain'/'test_fast'
if not CPU.exists():subprocess.run(['g++','-O3','-std=c++17',str(CPU.with_suffix('.cpp')),'-o',str(CPU)],check=True)
for name in ('first','second'):
 out=HERE/name;p=out/'decoder';old=BASE/'first'/'decoder_entropy';d=model(out/'training.npz');m=json.loads(old.with_suffix('.json').read_text());base=model(BASE/'first'/'entropy_training.npz');core=m['used']-m['stream_bytes']-1
 for k in ('a','bk','bm','lens','alt','ab','active','threshold','ww10'):assert np.array_equal(d[k],base[k]),k
 assert np.array_equal(d['y'],decode(d,d['idx'])[0]) and decode(d,d['idx'])[1]==0
 assert len(d['idx'])==json.loads((out/'results.json').read_text())['tokens']
 pre=old.with_suffix('.bin').read_bytes()[:core];stream=(d['idx']+1).astype(np.uint8).tobytes()+b'\0';raw=pre+stream;assert len(raw)<=65536 and core+1<=16384
 p.with_suffix('.bin').write_bytes(raw+bytes(65536-len(raw)));p.with_suffix('.stream').write_bytes(stream[:-1]);p.with_suffix('.asm').write_text(old.with_suffix('.asm').read_text().split('\nstream:\n')[0]+'\nstream:\n'+''.join('    db '+','.join(f'${x:02x}' for x in stream[i:i+16])+'\n' for i in range(0,len(stream),16))+'    defs 65536-$,0\n');shutil.copyfile(old.with_suffix('.map'),p.with_suffix('.map'))
 w=f.lut10(d['ww10'])[d['y']+512];np.save(p.with_suffix('.widths10.npy'),w);p.with_suffix('.expected').write_bytes(np.r_[0,d['y'],np.zeros(32,np.int16)].astype('<i2').tobytes());mapping={tuple(a[2:]):a[0] for a in struct.iter_unpack('<HH8H',p.with_suffix('.map').read_bytes())};neutral=mapping[tuple(m['patterns']['1280'])];threads=np.array([neutral]+[mapping[tuple(m['patterns'][str(int(x))])] for x in w]+[neutral]*32,dtype='<u2');p.with_suffix('.threads').write_bytes(threads.tobytes());m.update(used=len(raw),stream_bytes=len(stream)-1);p.with_suffix('.json').write_text(json.dumps(m,indent=2));sz=pack(d,m,p.with_suffix('.lp10g'));dd,_=unpack(p.with_suffix('.lp10g'));assert np.array_equal(dd['y'],d['y']) and np.array_equal(dd['idx'],d['idx']);test=json.loads(subprocess.check_output([str(CPU),str(p.with_suffix('.bin')),str(p.with_suffix('.map')),str(p.with_suffix('.expected')),'320','8','0','16',str(p.with_suffix('.threads'))],text=True));assert test['memory_writes']==0;test.update(core_bytes=core+1,occupied_rom=len(raw),container_bytes=sz,stream_bytes=len(stream)-1,core_sha256=hashlib.sha256(pre).hexdigest());p.with_suffix('.test.json').write_text(json.dumps(test,indent=2));print(name,test,flush=True)

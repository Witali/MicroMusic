#!/usr/bin/env python3
"""Re-run instruction-level tests for each generated ROM and validate the host 7-bit stream."""
from repack import *
import hashlib
cpu=HERE.parent/'LP20_v17_gain'/'test_fast'
subprocess.run(['g++','-O3','-std=c++17',str(cpu.with_suffix('.cpp')),'-o',str(cpu)],check=True)
summary={}
for name in ('first','second'):
 b=HERE.parent/'LP20_v21_rollout'/name;d0=model(b/'training.npz');met0=json.loads((b/'results.json').read_text())['best'];test0=json.loads((b/'decoder.test.json').read_text());summary[name]={'baseline':dict(test0,snr=met0['snr'],stoi=met0['stoi']),'variants':{}}
 for out in sorted((HERE/name).iterdir()):
  if not (out/'test.json').exists():continue
  p=out/'decoder';old=json.loads((out/'test.json').read_text());d=dict(np.load(out/'model.npz'));y,ov=decode_records(d);assert not ov and np.array_equal(y,d['y']);test=json.loads(subprocess.check_output([str(cpu),str(p.with_suffix('.bin')),str(p.with_suffix('.map')),str(p.with_suffix('.expected')),'320','8','0','16',str(p.with_suffix('.threads'))],text=True));assert test['memory_writes']==0
  exact=np.array_equal(y,d0['y']);met=json.loads((out/'result.json').read_text()) if (out/'result.json').exists() else json.loads((out/'metrics.json').read_text())['selected'] if (out/'metrics.json').exists() else met0
  old.update(test,pcm_equal_v21=bool(exact),sha256=hashlib.sha256(p.with_suffix('.bin').read_bytes()).hexdigest());(out/'test.json').write_text(json.dumps(old,indent=2));summary[name]['variants'][out.name]=dict(old,snr=met['snr'],stoi=met['stoi'],kbps=len(d['idx'])*8*FS/len(y)/1000)
  print('OK',name,out.name,old['core_bytes'],old['stream_bytes'],exact,flush=True)
 # Actual host bitstream: 1..127 codes, EOS=0, MSB-first contiguous 7-bit words.
 src=HERE/name/'long127_12_5';d=dict(np.load(src/'model.npz'));ix=d['idx'];codes=np.r_[ix+1,0].astype(np.uint8);assert max(codes)<=127
 data=np.packbits(((codes[:,None]>>np.arange(6,-1,-1))&1).ravel().astype(np.uint8),bitorder='big');out=HERE/name/'packed7_host';out.mkdir(exist_ok=True);(out/'tokens.lp7').write_bytes(data.tobytes());bits=np.unpackbits(data,bitorder='big')[:len(codes)*7].reshape(-1,7);back=(bits@(1<<np.arange(6,-1,-1))).astype(np.int16);assert back[-1]==0 and np.all(back[:-1]>0) and np.array_equal(back[:-1]-1,ix);dd=dict(d,idx=back[:-1]-1);yy,ov=decode_records(dd);assert not ov and np.array_equal(yy,d['y']);summary[name]['packed7_host']={'bytes_including_eos_and_pad':int(len(data)),'kbps':len(data)*8*FS/len(yy)/1000,'token_count':len(ix),'roundtrip_exact':True,'z80_verified':False,'reason':'No common 2560-T PWM schedule for the proposed reader'}
 print('HOST7',name,summary[name]['packed7_host'],flush=True)
(HERE/'summary.json').write_text(json.dumps(summary,indent=2))

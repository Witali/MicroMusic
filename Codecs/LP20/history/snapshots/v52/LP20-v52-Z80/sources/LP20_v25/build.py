#!/usr/bin/env python3
"""Build and verify native ROM candidates with v24 or direct-aware suffix packing."""
from study import *
import subprocess,traceback
import build_extended as original
import layout_builder as improved

def main(clip,profile):
 out=R/clip/profile;src=V23/clip/profile;basepath=V24/'extended239'/clip/profile/'96';meta=json.loads((src/'decoder.json').read_text());old=json.loads((src/'result.json').read_text());results=[]
 candidates=[]
 if (basepath/'model.npz').exists():candidates.append(('v24_relayout',basepath/'model.npz'))
 if (out/'contexts.json').exists():
  for a in json.loads((out/'contexts.json').read_text()):
   if 'ext_records' in a:candidates.append((a['name'],out/a['name']/'model.npz'))
 if profile=='exact_high':
  candidates.append(('base_reparse',out/'base_reparse'/'model.npz'))
 for name,model in candidates:
  for mode,builder in [('layout',improved),('original',original)]:
   if name=='v24_relayout' and mode=='original':continue
   path=out/name/mode;path.mkdir(parents=True,exist_ok=True);p=path/'decoder'
   try:
    mm=builder.build(model,p,period=320,grid=meta['grid'],alpha=.001);test=json.loads(subprocess.check_output([str(V24/'test_extended'),str(p.with_suffix('.bin')),str(p.with_suffix('.map')),str(p.with_suffix('.expected')),'320','8','0','16',str(p.with_suffix('.threads'))],text=True));assert p.with_suffix('.expected').read_bytes()==(src/'decoder.expected').read_bytes();assert np.array_equal(np.load(p.with_suffix('.widths10.npy')),np.load(src/'decoder.widths10.npy'));assert mm['patterns']==meta['patterns'];test.update(name=name,layout=mode,core_bytes=mm['used']-mm['stream_bytes'],occupied_rom=mm['used'],stream_bytes=mm['stream_bytes'],kbps=mm['stream_bytes']*8*7812.5/len(np.load(model)['y'])/1000,snr=old['snr'],stoi=old['stoi'],pcm_exact=True,pwm_widths_exact=True,book_bytes=mm['book_bytes'],book_in_holes=mm['book_in_holes']);(path/'test.json').write_text(json.dumps(test,indent=2));results.append(test);print('PASS',clip,profile,test,flush=True)
   except Exception as e:print('FAIL',clip,profile,name,mode,repr(e),flush=True);results.append(dict(name=name,layout=mode,error=repr(e)))
 (out/'builds.json').write_text(json.dumps(results,indent=2))
if __name__=='__main__':main(*sys.argv[1:])

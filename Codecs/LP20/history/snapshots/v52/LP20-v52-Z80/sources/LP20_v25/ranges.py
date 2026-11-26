#!/usr/bin/env python3
"""Optimize short/escape code split and validate actual ROM layout."""
from contexts import *
import layout_builder as builder
import subprocess

def main(clip,profile):
 src=V23/clip/profile;d=dict(np.load(src/'model.npz'));r=records(d);raw,loc=actual(d,r);syms=sorted({p for rr in r for p in rr});mp={p:i for i,p in enumerate(syms)};seq=np.array([mp[p] for p in raw],np.int16);prev=np.r_[0,d['y'][:-1]].astype(np.int32);pool=list(dict.fromkeys(tuple(mp[p] for p in rr) for rr in r));basepath=V24/'extended239'/clip/profile/'96'
 if (basepath/'model.npz').exists():
  old=dict(np.load(basepath/'model.npz'));rr=[tuple(mp[tuple(p)] for p in rec[:n]) for rec,n in zip(np.concatenate([old['records'],old['ext_records']]),np.r_[old['lengths'],old['ext_lengths']])];pool=list(dict.fromkeys(pool+rr))
 out=R/clip/profile/'range';out.mkdir(parents=True,exist_ok=True);res=[];solutions=[];md=json.loads((src/'decoder.json').read_text());old=json.loads((src/'result.json').read_text())
 for shortmax in (239,243,247,249,251,253,254):
  for th in ([24,32,48] if profile=='exact_high' else [24,64,96,112]):
   ctx=((prev>=th)|(prev< -th)).astype(np.uint8);sol=opt(seq,ctx,pool,len(syms),2,shortmax);rec=dict(shortmax=shortmax,threshold=th,stream_bytes=sol['stream'],estimated_book=sol['book'],estimate=sol['score']);print('EST',clip,profile,rec,flush=True);solutions.append((sol,ctx,rec))
 for shortmax in (243,247,249,251,253,254):
  sol,ctx,rec=min((x for x in solutions if x[2]['shortmax']==shortmax),key=lambda x:x[2]['estimate']);th=rec['threshold'];path=out/f'{shortmax}-{th}';model=path/'model.npz';rec['ext_records']=model_out(dict(d,threshold=np.array(th,dtype=d['threshold'].dtype)),sol,syms,ctx,model,shortmax)
  # Narrow direct windows start at dictionary page, avoid inaccessible suffix duplication.
  dd=dict(np.load(model));rec['attempts']=[]
  for page in (24,25,26):
   dd['direct_start']=np.int32(page*256);np.savez(model,**dd);pp=path/f'p{page}';pp.mkdir(exist_ok=True);p=pp/'decoder'
   try:
    mm=builder.build(model,p,period=320,grid=md['grid'],alpha=.001);test=json.loads(subprocess.check_output([str(V24/'test_extended'),str(p.with_suffix('.bin')),str(p.with_suffix('.map')),str(p.with_suffix('.expected')),'320','8','0','16',str(p.with_suffix('.threads'))],text=True));assert p.with_suffix('.expected').read_bytes()==(src/'decoder.expected').read_bytes();assert np.array_equal(np.load(p.with_suffix('.widths10.npy')),np.load(src/'decoder.widths10.npy'));assert mm['patterns']==md['patterns'];test.update(core_bytes=mm['used']-mm['stream_bytes'],occupied_rom=mm['used'],stream_bytes=mm['stream_bytes'],kbps=mm['stream_bytes']*8*7812.5/len(dd['y'])/1000,snr=old['snr'],stoi=old['stoi'],pcm_exact=True,pwm_widths_exact=True,page=page,shortmax=shortmax,threshold=th);(pp/'test.json').write_text(json.dumps(test,indent=2));np.savez(pp/'model.npz',**dd);rec['attempts'].append(test);print('PASS',clip,profile,test,flush=True);break
   except Exception as e:rec['attempts'].append(dict(page=page,error=repr(e)));print('FAIL',clip,profile,shortmax,th,page,repr(e),flush=True)
  res.append(rec)
 (out/'results.json').write_text(json.dumps(res,indent=2))
if __name__=='__main__':main(*sys.argv[1:])

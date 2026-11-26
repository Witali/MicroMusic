#!/usr/bin/env python3
"""Exact PWM beam reparse using the original byte-only compact dictionary."""
from pwm_exact import *
def main(clip,beam=6):
 src=V23/clip/'compact6';d=dict(np.load(src/'model.npz'));orig=d['y'].copy();rr=d['records'];ll=d['lengths'];th=int(d['threshold']);tb=f.compact_tables(d['a']);lut=lut10(d['ww10']);raw,loc=actual(d,records(d));ctx=np.r_[False,(orig[:-1]>=th)|(orig[:-1]<-th)];plan=d['idx'].astype(np.int32)+255*ctx[loc[:-1]].astype(np.int32);costs=np.ones(len(ll),np.int32);words=[]
 for c in (0,1):
  seen=set();keep=[]
  for k in range(255*c,255*(c+1)):
   a=rr[k,:ll[k]].tobytes()
   if a not in seen:keep.append(k);seen.add(a)
  words.append(keep)
 ww=np.full((2,max(map(len,words))),-1,np.int32)
 for i,w in enumerate(words):ww[i,:len(w)]=w
 start=time.time();new,cost=search(tb,rr,ll,ww,costs,th,orig,lut,plan,beam);y,ov=decode_plan(tb,rr,ll,new,th);assert not ov and len(y)==len(orig) and np.array_equal(lut[y+512],lut[orig+512]) and cost<=len(plan)
 print('SEARCH',clip,len(plan),cost,'PCM changes',np.count_nonzero(y!=orig),'seconds',time.time()-start,flush=True)
 used=set(map(int,new));common=min(used,key=lambda k:ll[k]);mat=rr.copy();lens=ll.copy()
 for k in range(510):
  if k not in used:mat[k]=rr[common];lens[k]=ll[common]
 z=dict(d,y=y,idx=(new%255).astype(np.int16),records=mat,lengths=lens);assert np.array_equal(decode_records(z)[0],y)
 out=R/clip/'compact6'/f'pwm_beam{beam}';md=json.loads((src/'decoder.json').read_text());old=json.loads((src/'result.json').read_text());test=buildcheck(z,out,md);assert np.array_equal(np.load(out/'decoder.widths10.npy'),np.load(src/'decoder.widths10.npy'));assert json.loads((out/'decoder.json').read_text())['patterns']==md['patterns'];test.update(baseline_stream=len(plan),baseline_rom=old['occupied_rom'],pcm_changed=int(np.count_nonzero(y!=orig)),max_pcm_delta=int(np.max(abs(y.astype(np.int32)-orig))),pwm_widths_exact=True,beam=beam,kbps=test['stream_bytes']*8*7812.5/len(y)/1000,snr=old['snr'],stoi=old['stoi']);(out/'test.json').write_text(json.dumps(test,indent=2));print('PASS',test,flush=True)
if __name__=='__main__':main(sys.argv[1],int(sys.argv[2]) if len(sys.argv)>2 else 6)

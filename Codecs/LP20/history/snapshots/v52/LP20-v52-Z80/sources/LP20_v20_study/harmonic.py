#!/usr/bin/env python3
"""Sparse phase-accumulator post-LPC correction. Host prototype; no new Z80 binary.
Actual payload contains canonical Huffman lengths, tokens, and 6-byte DDS events.
The same v19 model (dictionary, LPC and PWM tables) is external to the payload.
"""
import os,sys,struct,json,time
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE.parent/'LP20_v19_pitch'),str(HERE.parent/'LP20_v12_release')]
from study_pitch import ROOT,V18,model,decode,qtables,inspect,aligned,pcm_aligned,FS,pitch,f,np
import prefix
from scipy.signal import butter,sosfiltfilt
# 8 tables x 64 entries = 512 bytes, fixed across all voices.
GAINS=np.array([3,5,8,12,18,27,40,64],dtype=int)
WAVE=np.rint(GAINS[:,None]*np.sin(2*np.pi*np.arange(64)/64)).astype(np.int8)
HDR=struct.Struct('<4sBHHII') # magic, huffman mode, block size, event count, token count, huffman bytes
EV=struct.Struct('<HHBB') # frame index, phase increment, initial phase (8 MSBs), gain index

def shape(n,step,phase,gain):
 p=(np.arange(n,dtype=np.int64)*step+(phase<<8))&65535
 v=WAVE[gain,p>>10].astype(np.int16)
 # 16-sample edge taper; arithmetic shift, no multiply, no history.
 if n>=32:
  v[:8]>>=2;v[8:16]>>=1;v[-16:-8]>>=1;v[-8:]>>=2
 return v

def pack_lengths(ll):
 a=ll.ravel();assert a.max()<=15
 if len(a)%2:a=np.r_[a,0]
 return bytes((a[::2]<<4)|a[1::2])

def unpack_lengths(data,n):
 x=np.frombuffer(data,np.uint8);a=np.empty(len(x)*2,np.uint8);a[::2]=x>>4;a[1::2]=x&15;return a[:n]

def pack(d,ix,block,events,mode=1):
 ctx,ll=prefix.train(ix,d['lens'],mode);h,bits=prefix.encode(ix,ctx,ll);l=pack_lengths(ll)
 return HDR.pack(b'PH20',mode,block,len(events),len(ix),len(h))+l+h+b''.join(EV.pack(*ev) for ev in sorted(events))

def unpack(d,data):
 magic,mode,block,ne,nt,sz=HDR.unpack_from(data);assert magic==b'PH20';ctx=prefix.contexts(d['lens'],mode);nb=int(ctx.max())+1;ls=(nb*len(d['lens'])+1)//2;p=HDR.size;ll=unpack_lengths(data[p:p+ls],nb*len(d['lens'])).reshape(nb,-1);p+=ls;ix=prefix.decode(data[p:p+sz],nt,ctx,ll);p+=sz;y,ov=decode(d,ix);assert not ov;yy=y.copy();prev=-1
 for i in range(ne):
  bi,step,phase,gain=EV.unpack_from(data,p);p+=EV.size;assert bi>prev and gain<len(GAINS);prev=bi;s=bi*block;n=min(block,len(y)-s);assert n>0;yy[s:s+n]=np.clip(y[s:s+n].astype(np.int32)+shape(n,step,phase,gain),-512,511)
 assert p==len(data);return ix,y,yy

def candidates(d,m,block,metric,pt,u,v):
 y=d['y'];lev,qi,q=qtables(d,m);err=(u-v)*127/metric['gain'];n=len(y);out=[]
 for p in range(0,n,block):
  N=min(block,n-p)
  if N<32 or np.mean(pt['weight'][p:p+N])<.12:continue
  e=err[p:p+N];yy=y[p:p+N];freq=FS/np.median(pt['period'][p:p+N]);
  # Fit harmonic(s) to the error, not the signal. Explore small F0 variations.
  fs=(np.arange(1,min(12,int(3000/freq))+1)[:,None]*freq*np.array([.97,.985,1,1.015,1.03])[None,:]).ravel();steps=np.unique(np.rint(fs*65536/FS).astype(int));t=np.arange(N);a=2*np.pi*steps[:,None]*t[None,:]/65536
  win=np.ones(N);win[:8]=win[-8:]=.25;win[8:16]=win[-16:-8]=.5
  S=np.sin(a)*win;C=np.cos(a)*win;ss=np.sum(S*S,1);cc=np.sum(C*C,1);sc=np.sum(S*C,1);es=S@e;ec=C@e;den=ss*cc-sc*sc+1e-10
  bs=(es*cc-ec*sc)/den;bc=(ec*ss-es*sc)/den;A=np.hypot(bs,bc)*4;phase=np.rint(np.arctan2(bc,bs)*256/(2*np.pi)).astype(int)&255
  # Rank by continuous least-squares improvement, then exact quantized amplitude.
  best=None
  for k in np.argsort(-(es*bs+ec*bc))[:8]:
   for g in np.argsort(abs(GAINS-A[k]))[:3]:
    for ph in [(int(phase[k])+off)&255 for off in (-4,0,4)]:
     c=shape(N,int(steps[k]),ph,int(g));zz=np.clip(yy.astype(np.int32)+c,-512,511);dq=q[zz+512]-q[yy+512];de=np.sum(e*e-(e-dq)**2)
     if best is None or de>best[0]:best=(float(de),(p//block,int(steps[k]),ph,int(g)))
  if best and best[0]>0:out.append(best)
 return sorted(out,reverse=True)

def run(name):
 out=HERE/name;out.mkdir(exist_ok=True);d=model(ROOT/name/'training.npz');m=json.loads((V18/'release/compact/decoder.json').read_text());base,pt,r,z,u,v=inspect(d,d['y'],m);ix=d['idx'];budget=len(ix);log=[];best=None
 print('BASE',name,base,'budget',budget,flush=True)
 mode=min([0,1,2],key=lambda md:len(pack(d,ix,256,[],md)));empty=pack(d,ix,256,[],mode);allow=(budget-len(empty))//EV.size
 print('Huffman',mode,len(empty),'events available',allow,flush=True)
 for block in [128,256,512]:
  cand=candidates(d,m,block,base,pt,u,v);print('CANDIDATES',block,len(cand),flush=True)
  for num in sorted(set([max(1,allow//4),max(1,allow//2),max(1,allow),min(len(cand),allow*2)])):
   events=[ev for _,ev in cand[:num]];data=pack(d,ix,block,events,mode);i0,y,yy=unpack(d,data);assert np.array_equal(i0,ix) and np.array_equal(y,d['y']);met,_,rr,zz,*_=inspect(d,yy,m,pt);rec=dict(block=block,events=len(events),bytes=len(data),kbps=len(data)*8*FS/len(y)/1000,**met);log.append(rec);print('TRIAL',rec,flush=True)
   if len(data)<=budget and met['snr']>=base['snr'] and met['stoi']>=base['stoi'] and (best is None or met['snr']>best[0]['snr']):
    best=(rec,data);f.audio(out/'harmonic.wav',rr,zz);(out/'sound.ph20').write_bytes(data);np.save(out/'corrected.npy',yy)
 f.audio(out/'baseline.wav',r,z);f.e.wav(out/'reference.wav',r*.98/max(abs(r)));(out/'harmonic.json').write_text(json.dumps(dict(baseline=base,base_tokens=budget,packed_without_events=len(empty),mode=mode,max_events=allow,selected=best[0] if best else None,trials=log),indent=2));print('FINAL',name,best[0] if best else None,flush=True)
if __name__=='__main__':run(sys.argv[1])

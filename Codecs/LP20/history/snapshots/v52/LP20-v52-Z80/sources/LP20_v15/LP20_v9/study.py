"""LP20 v8: same bit-exact decoder, shared codebooks and constrained search."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1';os.environ['LP20_BASE']=str(__import__('pathlib').Path(__file__).resolve().parent)
import sys,json,time,math,subprocess
from pathlib import Path
import numpy as np
from scipy.signal import resample_poly
from scipy.io.wavfile import read
from scipy.ndimage import uniform_filter1d
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tools'))
import feedback_v7 as fb, encode as e, nonuniform_h10 as nu, build_h10 as h, encoder_core as c
from precision_study import FS,reconstruct
nu.ROOT=ROOT/'results'
BASE=Path('/mnt/data/LP20_PWM_feedback_v7/pass3balanced/training.npz')
def load(p,sec=None):
 sr,x=read(p);x=x.astype(float);x=x.mean(axis=1) if x.ndim>1 else x
 if sec:x=x[:int(sr*sec)]
 g=math.gcd(15625,2*sr);x=resample_poly(x,15625//g,2*sr//g);x-=x.mean();x*=125.73/max(abs(x));return np.pad(x,(0,(-len(x))%8))
def lut_for(ww):
 qid=np.array([min(range(len(ww)),key=lambda i:(abs(ww[i]-(128+v*112/512)),abs(ww[i]-128))) for v in range(-512,512)],dtype=np.int16);lut=ww[qid].astype(np.int32);return qid,lut,(lut-128)*128./112
def measure(t,y,ww):
 _,lut,_=lut_for(ww);ref=e.lp(resample_poly(t/127,768,125),3500);z=e.lp(nu.render_actual(lut[y+512],256,10)/.875*128/127,3500);return e.align_metric(ref,z)
def save(tag,d,idx,y,m):
 p=ROOT/'results'/tag;p.mkdir(parents=True,exist_ok=True);t=d['target'];dd={k:d[k] for k in ('target','a','tb','bk','bm','lens','ww')};dd.update(idx=idx,y=y,bits=10);np.savez(p/'training.npz',**dd)
 _,lut,_=lut_for(d['ww']);r=resample_poly(t/127,768,125);g=.98/max(abs(r));z=nu.render_actual(lut[y+512],256,10)/.875*128/127
 e.wav(p/'reference.wav',r*g);e.wav(p/'pwm.wav',z*g*min(1,.98/(max(abs(z))*g)));(p/'metrics.json').write_text(json.dumps(m,indent=2));return p
def encode_trial(d,tag,ex=.4,high=.55,mix=.2,alpha=0.,trust=0.,lam=24.,old=None,proj=None,beam=1,targetbps=5000,tries=3,save_output=True):
 t,tb,bk,bm,lens,ww=[d[k] for k in ('target','tb','bk','bm','lens','ww')];qid,lut,qlut=lut_for(ww);lev=(ww-128)*128./112
 w=(uniform_filter1d(t*t,156)+12.)**(-ex);w/=w.mean();w=(1-mix)*w+mix;dt=np.diff(t,prepend=0);wd=(uniform_filter1d(dt*dt,156)+6.)**(-ex);wd=wd/wd.mean()*high
 if old is None:extra=np.zeros((len(t),len(ww)),np.float32)
 else:
  extra=-alpha*proj+trust*w[:,None]*(lev[None,:]-qlut[old+512,None])**2;extra-=extra.min(axis=1)[:,None];extra=extra.astype(np.float32)
 target=len(t)/FS*targetbps/8;best=None;lo=None;hi=None
 for j in range(tries):
  start=time.time();ix=fb.trellis(t,tb,bk,bm,lens,w,wd,lam,qlut,qid,extra,beam);n=len(ix);print(tag,j,'lam',round(lam,3),'bytes',n,'s',round(time.time()-start,2),flush=True)
  if best is None or abs(n-target)<abs(len(best[0])-target):best=ix.copy(),lam
  if abs(n-target)<target*.009:break
  
  if n>target:lo=(lam,n)
  else:hi=(lam,n)
  if lo is not None and hi is not None:
   # interpolate on log scale, clipped inside valid bracket
   f=np.clip(np.log(lo[1]/target)/max(1e-9,np.log(lo[1]/hi[1])),.15,.85);lam=np.exp((1-f)*np.log(lo[0])+f*np.log(hi[0]))
  else:lam*=(n/target)**1.5
 ix,lam=best;y,_,over=reconstruct(t,tb,bk,bm,lens,ix,10);m=measure(t,y,ww);m.update(tag=tag,bytes=len(ix),kbps=len(ix)*8/(len(t)/FS)/1000,overflow=int(over),exponent=ex,high=high,globalmix=mix,alpha=alpha,trust=trust,lam=lam,beam=beam)
 if save_output:save(tag,d,ix,y,m)
 print('RESULT',json.dumps(m),flush=True);return ix,y,m

def get_proj(d,y):
 qid,lut,_=lut_for(d['ww']);g4,score=fb.grad_pwm(d['target'],y,lut);wave=np.clip(d['ww'][:,None]-np.arange(4)*64,0,64)/32.-1.;old=wave[qid[y+512]];g4*=len(y);proj=g4@wave.T;proj-=np.sum(g4*old,axis=1)[:,None];return proj.astype(np.float32)

def dual(which):
 d=dict(np.load(BASE));y=d['y'];m0=measure(d['target'],y,d['ww']);print('REFERENCE',m0,flush=True)
 p=ROOT/'latest_proj.npy'
 if p.exists():proj=np.load(p)
 else:proj=get_proj(d,y);np.save(p,proj)
 choices=[('dual_a',.35,.4,.25,1.0,2.,23.),('dual_b',.45,.6,.2,1.2,3.,27.),('dual_c',.25,.3,.25,.7,3.,22.),('dual_d',.45,.6,.12,2.0,3.,30.)]
 tag,ex,hi,mix,alpha,trust,lam=choices[which];encode_trial(d,tag,ex,hi,mix,alpha,trust,lam,y,proj,2,tries=3)

# Same stable LPC fit and synthesis-space VQ on training-only material.
def train_model(inputs,ww):
 rng=np.random.default_rng(20261125);t=np.concatenate([np.r_[x,np.zeros((-len(x))%80+80)] for x in inputs]);order=6;nb=8
 H=np.r_[np.zeros(order),t];X=np.stack([H[order-1-i:order-1-i+len(t)] for i in range(order)],axis=1);Y=t;xf=X.reshape(-1,80,order);yf=Y.reshape(-1,80);en=(yf*yf).sum(1);F=np.einsum('nki,nk->ni',xf,yf)/(en[:,None]+100.);w=(en+1000.)**.3;w/=w.mean();ct=[np.average(F,axis=0,weights=w)]
 for j in range(1,nb):
  dist=np.min(np.sum((F[:,None,:]-np.array(ct)[None,:,:])**2,axis=2),axis=1)*w;ct.append(F[rng.choice(len(F),p=dist/dist.sum())])
 ct=np.array(ct)
 for i in range(25):
  ass=np.argmin(np.sum((F[:,None,:]-ct[None,:,:])**2,axis=2),axis=1)
  for j in range(nb):
   if (ass==j).any():ct[j]=np.average(F[ass==j],axis=0,weights=w[ass==j])
 for it in range(5):
  aa=[]
  for j in range(nb):
   mask=ass==j;xx=xf[mask].reshape(-1,order);yy=yf[mask].ravel();wt=np.repeat((en[mask]/80+12.)**(-.2),80);s=np.sqrt(wt);aa.append(c.coeff(xx*s[:,None],yy*s,order) if len(xx)>order else c.coeff(X,Y,order))
  a=np.array(aa);err=(Y[:,None]-X@a.T).reshape(-1,80,nb);new=np.sum(err**2,axis=1).argmin(1)
  if len(set(new))<nb or np.array_equal(new,ass):break
  if it<4:ass=new
 a=np.rint(a*2**24)/2**24;tb=h.compact_tables(a);assign=np.repeat(ass,80);r=np.clip(np.rint((Y[:,None]-X@a.T)*4),-512,511)
 B=[];M=[];L=[]
 for ln,budget in zip([1,2,4,8,16,32,64,128],[16,24,39,60,62,32,16,6]):
  starts=np.arange(0,len(t)-ln+1,max(1,ln//4));lab=assign[starts];mass=np.array([np.sqrt(max(1,np.sum(r[assign==j,j]**2))*max(1,np.sum(lab==j))) for j in range(nb)]);q=budget*mass/mass.sum();counts=q.astype(int);counts[np.argsort(-(q-counts))[:budget-counts.sum()]]+=1
  for j,k in enumerate(counts):
   if not k:continue
   z=starts[lab==j];z=rng.choice(z,min(5000,len(z)),replace=False) if len(z)>5000 else z
   if not len(z):rr=np.zeros((1,ln),np.float32)
   else:rr=r[z[:,None]+np.arange(ln),j].astype(np.float32)
   imp=c.impulse(a[j],ln);zz=rr@imp.T;book=np.zeros((k,ln),np.float32);cz=np.zeros_like(book);dist=np.sum(zz*zz,axis=1);zn=dist.copy()
   for u in range(1,k):
    i=rng.choice(len(rr),p=dist/dist.sum()) if dist.sum()>0 else rng.integers(len(rr));book[u]=rr[i];cz[u]=zz[i];dist=np.minimum(dist,np.sum((zz-cz[u])**2,axis=1))
   for it in range(10):
    ix=np.argmin(zn[:,None]+np.sum(cz*cz,axis=1)-2*zz@cz.T,axis=1);sums=np.zeros_like(book,dtype=np.float64);np.add.at(sums,ix,rr);cnt=np.bincount(ix,minlength=k);good=np.flatnonzero(cnt[1:])+1;book[good]=sums[good]/cnt[good,None];cz=book@imp.T
   book=np.clip(np.rint(book),-512,511).astype(np.int16);B.extend(np.pad(book,((0,0),(0,128-ln))));M.extend([j]*k);L.extend([ln]*k)
 assert len(B)==255
 return dict(a=a,tb=tb,bk=np.array(B,np.int16),bm=np.array(M,np.uint8),lens=np.array(L,np.int32),ww=ww)

def corpus():
 C=ROOT/'corpus';inputs=[];manifest=[]
 train=[('older_user','/mnt/data/lp20_user_voice/source_mono.wav'),('archive_ru','/mnt/data/lpx_real_ru/original.wav')]
 synth=[('ru_male','ru+m2',158,'Шесть шустрых щенков шуршали в сухой траве. На тихой улице слышен шорох шин, звон стекла, свист ветра. Сегодня мы проверяем чистоту и разборчивость человеческой речи.'),('ru_female','ru+f3',176,'Пожалуйста, скажите, где находится ближайшая станция. Четыре человека спешат на поезд. Сначала нужно купить билет, затем подойти к третьей платформе.'),('en_male','en-us+m3',165,'Please check the first six channels. Quiet speech should remain clear, while sharp consonants, vowels, and short pauses preserve their original timing.'),('en_female','en+f2',153,'A small wooden ship sailed across the ocean. She heard the waves, watched the stars, and spoke softly about the bright blue sky.')]
 for name,voice,speed,txt in synth:
  p=C/(name+'.wav');subprocess.run(['espeak','-v',voice,'-s',str(speed),'-w',str(p),txt],check=True);train.append((name,str(p)))
 for name,p in train:
  t=load(p);inputs.append(t);manifest.append(dict(name=name,split='train',seconds=len(t)/FS,source=str(p),type='synthetic eSpeak' if name in [s[0] for s in synth] else 'recorded'))
 p=C/'ru_new.wav';subprocess.run(['espeak','-v','ru+f5','-s','142','-w',str(p),'Саша шёл по шоссе. Слышишь, как щебечут птицы? Чистый звук должен сохранять все тихие детали. Пятьдесят четыре, двадцать семь, восемьдесят два.'],check=True)
 tests=[('latest_user',np.load(BASE)['target']),('new_ru_tts',load(p)),('dialogue',load('/opt/pyvenv/lib/python3.13/site-packages/pyannote/audio/sample/sample.wav',12))]
 for name,t in tests:manifest.append(dict(name=name,split='test',seconds=len(t)/FS,source=('user second recording' if name=='latest_user' else 'eSpeak ru+f5 novel text' if name=='new_ru_tts' else 'pyannote/audio/sample/sample.wav first 12s; license not established, no redistribution')))
 (C/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2));return inputs,tests

def pooled():
 inputs,tests=corpus();ww=np.load(BASE)['ww'];print('CORPUS',[len(t)/FS for t in inputs],[(n,len(t)/FS) for n,t in tests],flush=True)
 for name,inp in [('single',inputs[:1]),('pooled',inputs)]:
  start=time.time();m=train_model(inp,ww);np.savez(ROOT/(name+'_model.npz'),**m);print('TRAINED',name,time.time()-start,'vectors',sum(m['lens']),flush=True)
 for name,t in tests:
  for model in ('single','pooled'):
   d=dict(np.load(ROOT/(model+'_model.npz')));d['target']=t;encode_trial(d,name+'_'+model,lam=24.,beam=1,tries=3,save_output=name!='dialogue')
if __name__=='__main__':
 if sys.argv[1]=='dual':dual(int(sys.argv[2]))
 else:pooled()

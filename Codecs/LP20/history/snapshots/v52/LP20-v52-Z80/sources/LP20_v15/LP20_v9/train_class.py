"""Training-only class-aware LP20. Exact integer prediction residual, 255
fixed variable-length vectors, 8 LPC banks. No format/kernel changes."""
import study as s
import numpy as np
import subprocess, json, time, argparse, os, uuid
from scipy.ndimage import uniform_filter1d
from pathlib import Path
from numba import njit
ROOT=s.ROOT; C=ROOT/'corpus'
EXTRA=[
 ('ru_low','ru+m1',141,'Тихое утро, на скамейке лежит мокрый шарф. В шесть часов дворник сметает шуршащие листья. Издалека слышен стук колёс, затем шаги и тихий разговор. Сегодня дождь, завтра ожидается солнце.'),
 ('ru_fast','ru+m4',202,'Четыре тысячи восемьсот шестьдесят пять. Запишите номер, пожалуйста. Проверка связи: раз, два, три, четыре. Звонкий голос, глухой звук, свист, шипение. Шофёр остановился возле железнодорожного переезда.'),
 ('ru_soft','ru+f2',135,'Послушай, как шелестят листья. Утром ещё прохладно, но к вечеру станет теплее. По стеклу медленно стекают капли. Щенок лежит у печки, а кошка тихо сидит на стуле. Спасибо, что пришли.'),
 ('ru_bright','ru+f4',190,'Пять чашек чая, шесть свежих булочек и семь ложек сахара. Сегодня мы читаем короткие предложения, чтобы проверить все гласные и согласные звуки. Мама мыла раму. Тридцать три корабля лавировали, лавировали.'),
 ('ru_alt','ru+m5',166,'В соседней комнате работает старый приёмник. Иногда слышно потрескивание, но диктор говорит достаточно ясно. Через несколько минут начинается передача о природе. Птицы щебечут, ручей журчит, ветер шумит в кронах деревьев.'),
 ('en_low','en-gb+m1',142,'A quiet voice speaks from the next room. Six small ships cross the silver sea. The morning train stops at the station. Clear speech contains soft consonants, sharp bursts, and changing vowels. Please leave a short message.'),
 ('en_fast','en-us+f4',200,'Check the frequency, phase, and amplitude of each signal. Speech should sound clear even when the speaker whispers. Fresh fish, crisp chips, six thin slices of cheese, and a glass of water. Turn the switch and press the button.'),
 ('de','de+m3',170,'Guten Morgen. Heute sprechen wir langsam und deutlich. Zwischen den Häusern weht ein kalter Wind. Die Kinder spielen im Garten. Bitte prüfen Sie die Lautstärke und die Verständlichkeit der Aufnahme.')]
TRAIN=['older_user','archive_ru','ru_male','ru_female','en_male','en_female']
@njit(cache=True)
def integer_residual(q,hist,tb):
 n=len(q);nb=tb.shape[0];out=np.empty((n,nb),np.float32)
 for i in range(n):
  for b in range(nb):
   z=0
   for j in range(hist.shape[1]):z+=tb[b,j,hist[i,j]+512]
   out[i,b]=max(-512,min(511,int(q[i])-((z+32)>>6)))
 return out

def train(inputs,ww,kind='class',seed=20261126):
 rng=np.random.default_rng(seed);order=6;nb=8;frame=160
 # Include amplitude variants without altering independent test recordings.
 t=np.concatenate([np.r_[x,np.zeros((-len(x))%frame+frame)] for x in inputs]);H=np.r_[np.zeros(order),t];X=np.stack([H[order-1-i:order-1-i+len(t)] for i in range(order)],axis=1);Y=t;xf=X.reshape(-1,frame,order);yf=Y.reshape(-1,frame);en=(yf*yf).sum(1);F=np.einsum('nki,nk->ni',xf,yf)/(en[:,None]+100.)
 # Low-lag correlation + periodicity (pitch lag) + high-band energy ratio.
 ff=np.abs(np.fft.rfft(yf*np.hanning(frame),n=256))**2;high=ff[:,64:].sum(1)/(ff.sum(1)+1e-9);ac=np.fft.irfft(ff,n=256);voicing=np.max(ac[:,16:100],axis=1)/(ac[:,0]+1e-9)
 if kind=='class':
  # Fixed groups selected without using any held-out clip. Three periodic,
  # three mixed, two noise-dominated banks; local error refits within group.
  cls=np.where((high>.32)|(F[:,0]<.1),2,np.where((voicing>.30)&(F[:,0]>.55),0,1));counts=(3,3,2)
 else:cls=np.zeros(len(F),int);counts=(8,)
 w=(en+1000.)**.17;w/=w.mean();a=[];ass=np.zeros(len(F),int);offset=0
 for group,nbg in enumerate(counts):
  ii=np.flatnonzero(cls==group);f=F[ii];wg=w[ii];ct=[np.average(f,axis=0,weights=wg)]
  for j in range(1,nbg):
   dist=np.min(np.sum((f[:,None,:]-np.array(ct)[None,:,:])**2,axis=2),axis=1)*wg;ct.append(f[rng.choice(len(f),p=dist/dist.sum())])
  ct=np.array(ct)
  for i in range(18):
   asg=np.argmin(np.sum((f[:,None,:]-ct[None,:,:])**2,axis=2),axis=1)
   for j in range(nbg):
    if (asg==j).any():ct[j]=np.average(f[asg==j],axis=0,weights=wg[asg==j])
  for it in range(5):
   aa=[]
   for j in range(nbg):
    m=ii[asg==j];xx=xf[m].reshape(-1,order);yy=yf[m].ravel();wt=np.repeat((en[m]/frame+8.)**(-.28),frame);z=np.sqrt(wt);aa.append(s.c.coeff(xx*z[:,None],yy*z,order) if len(xx)>order else s.c.coeff(X,Y,order))
   aa=np.array(aa);err=(yf[ii,:,None]-xf[ii]@aa.T);new=np.sum(err**2,axis=1).argmin(1)
   if len(set(new))<nbg or np.array_equal(new,asg) or it==4:break
   asg=new
  a.extend(aa);ass[ii]=asg+offset;offset+=nbg
 a=np.rint(np.array(a)*2**24)/2**24;tb=s.h.compact_tables(a);assign=np.repeat(ass,frame)
 q=np.clip(np.rint(Y*4),-512,511).astype(np.int16);hq=np.clip(np.rint(X*4),-512,511).astype(np.int16);r=integer_residual(q,hq,tb)
 energy=uniform_filter1d(Y*Y,size=156);rw=(energy+8.)**(-.45);rw/=rw.mean()
 # Allocate more short vectors to transient/noisy speech; each vector still
 # has one-byte index, bank and length are carried by the ROM table.
 B=[];M=[];L=[];budgets=[20,34,47,66,53,23,9,3] if kind=='class' else [16,24,40,56,95,18,4,2]
 assert sum(budgets)==255
 for ln,budget in zip([1,2,4,8,16,32,64,128],budgets):
  starts=np.arange(0,len(t)-ln+1,max(1,ln//4));lab=assign[starts];mass=np.array([np.sqrt(max(1,np.sum(rw[assign==j]*r[assign==j,j]**2))*max(1,np.sum(lab==j))) for j in range(nb)])
  if kind=='class':
   # Noise banks favour short blocks, tonal banks long. All bank types
   # retain the same LPC synthesis and do not add a flag to the stream.
   mass*=np.r_[np.full(3,1.0 if ln<=4 else 1.6),np.ones(3),np.full(2,1.9 if ln<=4 else .65)]
  qmass=budget*mass/mass.sum();num=qmass.astype(int);num[np.argsort(-(qmass-num))[:budget-num.sum()]]+=1
  for j,k in enumerate(num):
   if not k:continue
   z=starts[lab==j];z=rng.choice(z,min(4500,len(z)),replace=False) if len(z)>4500 else z
   if not len(z):rr=np.zeros((1,ln),np.float32);weights=np.ones(1,np.float32)
   else:rr=r[z[:,None]+np.arange(ln),j];weights=np.mean(rw[z[:,None]+np.arange(ln)],axis=1).astype(np.float32)
   weights/=weights.mean();imp=s.c.impulse(a[j],ln);zz=rr@imp.T
   # Penalize lost high-frequency energy in synthesis space as well as PCM error.
   dz=np.diff(zz,axis=1,prepend=0);features=np.concatenate([zz,dz*.48],axis=1);book=np.zeros((k,ln),np.float32);cz=np.zeros((k,ln*2),np.float32);dist=np.sum(features**2,axis=1);zn=dist.copy()
   def feat(b):
    v=b@imp.T;return np.concatenate([v,np.diff(v,axis=1,prepend=0)*.48],axis=1)
   for u in range(1,k):
    i=rng.choice(len(rr),p=(dist*weights)/(dist*weights).sum()) if dist.sum()>0 else rng.integers(len(rr));book[u]=rr[i];cz[u]=features[i];dist=np.minimum(dist,np.sum((features-cz[u])**2,axis=1))
   for it in range(10):
    ix=np.argmin(zn[:,None]+np.sum(cz*cz,axis=1)-2*features@cz.T,axis=1);sums=np.zeros_like(book,dtype=np.float64);np.add.at(sums,ix,rr*weights[:,None]);cnt=np.bincount(ix,weights=weights,minlength=k);good=np.flatnonzero(cnt[1:])+1;book[good]=sums[good]/cnt[good,None];cz=feat(book)
   book=np.clip(np.rint(book),-512,511).astype(np.int16);B.extend(np.pad(book,((0,0),(0,128-ln))));M.extend([j]*k);L.extend([ln]*k)
 assert len(B)==255
 print('classes',np.bincount(cls).tolist(),'vectors',len(B),'excitation words',sum(L),'training seconds',len(t)/s.FS,flush=True)
 return dict(a=a,tb=tb,bk=np.array(B,np.int16),bm=np.array(M,np.uint8),lens=np.array(L,np.int32),ww=ww)

def prepare():
 manifest=[]
 for name,voice,speed,txt in EXTRA:
  p=C/(name+'.wav')
  if not p.exists():
   tmp=p.with_name(p.stem+'_'+uuid.uuid4().hex+'.wav');subprocess.run(['espeak','-v',voice,'-s',str(speed),'-w',str(tmp),txt],check=True);os.replace(tmp,p)
 names=TRAIN+[x[0] for x in EXTRA];inp=[]
 for name in names:
  t=s.load(C/(name+'.wav'));inp.append(t);manifest.append(dict(name=name,seconds=len(t)/s.FS,type='recorded' if name in TRAIN[:2] else 'eSpeak',split='train'))
 (C/'train_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2));print('original train seconds',sum(len(x) for x in inp)/s.FS,flush=True)
 return inp
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--kind',choices=['class','rounded'],default='class');a=p.parse_args();inp=prepare();ww=np.load(ROOT/'models/pooled_model.npz')['ww'];# fixed amplitude augmentation for recorded inputs and a subset of TTS
 aug=inp+[x*.55 for x in inp[:6]]
 m=train(aug,ww,a.kind);np.savez(ROOT/'models'/(a.kind+'_model.npz'),**m)

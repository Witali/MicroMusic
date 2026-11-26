from study import *
def train_balanced(inputs,ww):
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
 a=np.rint(a*2**24)/2**24;tb=h.compact_tables(a);assign=np.repeat(ass,80);r=np.clip(np.rint((Y[:,None]-X@a.T)*4),-512,511);energy=uniform_filter1d(Y*Y,size=156);rw=(energy+12.)**(-.45);rw/=rw.mean()
 B=[];M=[];L=[]
 for ln,budget in zip([1,2,4,8,16,32,64,128],[16,24,40,56,95,18,4,2]):
  starts=np.arange(0,len(t)-ln+1,max(1,ln//4));lab=assign[starts];mass=np.array([np.sqrt(max(1,np.sum(rw[assign==j]*r[assign==j,j]**2))*max(1,np.sum(lab==j))) for j in range(nb)]);q=budget*mass/mass.sum();counts=q.astype(int);counts[np.argsort(-(q-counts))[:budget-counts.sum()]]+=1
  for j,k in enumerate(counts):
   if not k:continue
   z=starts[lab==j];z=rng.choice(z,min(5000,len(z)),replace=False) if len(z)>5000 else z
   if not len(z):rr=np.zeros((1,ln),np.float32)
   else:rr=r[z[:,None]+np.arange(ln),j].astype(np.float32)
   weights=np.mean(rw[z[:,None]+np.arange(ln)],axis=1).astype(np.float32) if len(z) else np.ones(1,np.float32);weights/=weights.mean();imp=c.impulse(a[j],ln);zz=rr@imp.T;book=np.zeros((k,ln),np.float32);cz=np.zeros_like(book);dist=np.sum(zz*zz,axis=1);zn=dist.copy()
   for u in range(1,k):
    i=rng.choice(len(rr),p=(dist*weights)/(dist*weights).sum()) if dist.sum()>0 else rng.integers(len(rr));book[u]=rr[i];cz[u]=zz[i];dist=np.minimum(dist,np.sum((zz-cz[u])**2,axis=1))
   for it in range(10):
    ix=np.argmin(zn[:,None]+np.sum(cz*cz,axis=1)-2*zz@cz.T,axis=1);sums=np.zeros_like(book,dtype=np.float64);np.add.at(sums,ix,rr*weights[:,None]);cnt=np.bincount(ix,weights=weights,minlength=k);good=np.flatnonzero(cnt[1:])+1;book[good]=sums[good]/cnt[good,None];cz=book@imp.T
   book=np.clip(np.rint(book),-512,511).astype(np.int16);B.extend(np.pad(book,((0,0),(0,128-ln))));M.extend([j]*k);L.extend([ln]*k)
 assert len(B)==255
 return dict(a=a,tb=tb,bk=np.array(B,np.int16),bm=np.array(M,np.uint8),lens=np.array(L,np.int32),ww=ww)

if __name__=='__main__':
 inputs,tests=corpus();ww=np.load(BASE)['ww'];aug=inputs[:2]+[x*.55 for x in inputs[2:]]+inputs[2:]+[inputs[0]*.65,inputs[1]*.65];m=train_balanced(aug,ww);np.savez(ROOT/'balanced_model.npz',**m);print('TRAINED balanced',sum(m['lens']),flush=True)
 for name,t in tests:
  d=dict(m);d['target']=t;encode_trial(d,name+'_balanced',lam=45 if name=='latest_user' else (160 if name=='new_ru_tts' else 30),tries=5,beam=1,save_output=name!='dialogue')

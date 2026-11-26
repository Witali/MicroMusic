#!/usr/bin/env python3
"""Bit-packed version with frame-to-frame pitch deltas and dead-zone optimization.
No per-frame byte length, residual sentinel delimits each frame. Software only."""
from hybrid import *
from collections import Counter
DEAD=np.array([.50,.75,1.,1.25,1.5])
HEADER2='<4sIHHBB'
@njit(cache=True)
def optimize(c,maxbits,scales,mb):
 n=len(c);best=np.full(maxbits+1,1e30);bs=np.full(maxbits+1,-1,np.int16);bk=np.full(maxbits+1,-1,np.int8);bd=np.full(maxbits+1,-1,np.int8)
 for i in range(len(scales)):
  s=scales[i];u=c/s;qr=np.rint(u).astype(np.int32)
  for d in range(len(DEAD)):
   err=0.;costs=np.full(4,10,np.int32);prev=-1
   for j in range(n):
    q=qr[j] if abs(u[j])>=DEAD[d] else 0;err+=(c[j]-q*s)**2;z=abs(q)
    if z==0:continue
    if z>=len(mb):z=len(mb)-1
    gap=j-prev-1;prev=j
    for k in range(4):costs[k]+=1+(gap>>k)+1+k+mb[z]
   k=np.argmin(costs);cost=costs[k]
   if cost<=maxbits and err<best[cost]:best[cost]=err;bs[cost]=i;bk[cost]=k;bd[cost]=d
 err=np.sum(c*c)
 if err<best[10]:best[10]=err;bs[10]=-2;bk[10]=0;bd[10]=0
 for b in range(1,maxbits+1):
  if best[b-1]<best[b]:best[b]=best[b-1];bs[b]=bs[b-1];bk[b]=bk[b-1];bd[b]=bd[b-1]
 return bs,bk,bd,best

def packet_bits(mode,par,c,s,k,dead,grid,K):
 w=Writer();w.put(mode,2)
 if mode:
  w.put(par[0],int(math.log2(grid)));a=1
  for _ in range(mode):w.put(par[a],int(math.log2(K)));w.put(par[a+1],8);w.put(par[a+2],8);a+=3
 w.put(max(s,0),7);w.put(k,2);q=np.zeros(len(c),int) if s==-2 else np.where(abs(c/SCALES[s])>=DEAD[dead],np.rint(c/SCALES[s]),0).astype(int);prev=-1
 for j in np.flatnonzero(q):
  v=q[j];gap=j-prev-1;prev=j;w.put(1,1);w.unary(gap>>k);w.put(gap&((1<<k)-1),k);w.eg(abs(v)-1);w.put(int(v<0),1)
 w.put(0,1);return np.asarray(w.bits,np.uint8)

def candidates(x,fr,wt,fft,grid,K,maxbits):
 pp=[(0,(),np.zeros(len(x)))]+pred(x,fr,wt,fft,grid);out=[]
 for mode,par,p in pp:
  c=dct(x-p,norm='ortho');head=2+(int(math.log2(grid))+mode*(int(math.log2(K))+16) if mode else 0);bs,bk,bd,err=optimize(c,maxbits-head,SCALES,MAGBITS);last=None
  for b in range(10,maxbits-head+1):
   if bs[b]==-1:continue
   key=(int(bs[b]),int(bk[b]),int(bd[b]))
   if key==last:continue
   last=key;bits=packet_bits(mode,par,c,*key,grid,K);assert len(bits)<=b+head;out.append((len(bits),float(err[b]),bits,mode,par[0] if mode else -1))
 return out

def delta_cost(prev,now,bits):
 if prev<0 or now<0:return 0
 return 4-bits if abs(now-prev)<=7 else 4

def alloc(cands,budget,grid,modes):
 bits=int(math.log2(grid));ca=[[c for c in a if c[3] in modes] for a in cands];arr=[];pitch=[]
 for a in ca:
  i0=np.array([i for i,c in enumerate(a) if c[3]==0]);i1=np.array([i for i,c in enumerate(a) if c[3]!=0]);nb=np.array([c[0] for c in a]);er=np.array([c[1] for c in a]);p=a[i1[0]][4] if len(i1) else -1;arr.append((i0,i1,nb,er));pitch.append(p)
 def search(lam):
  cost=np.array([0.,1e100]);sz=np.array([0,0]);old=-1;back=[];ix=[]
  for (i0,i1,nb,er),p in zip(arr,pitch):
   v=er+lam*nb;a=i0[np.argmin(v[i0])];pr0=int(np.argmin(cost));c0=cost[pr0]+v[a];s0=sz[pr0]+nb[a];pr1=0;b=-1;c1=1e100;s1=0
   if len(i1):
    b=i1[np.argmin(v[i1])];diff=delta_cost(old,p,bits);vv=cost+np.array([0.,lam*diff]);pr1=int(np.argmin(vv));c1=vv[pr1]+v[b];s1=sz[pr1]+nb[b]+(diff if pr1 else 0)
   back.append((pr0,pr1));ix.append((a,b));cost=np.array([c0,c1]);sz=np.array([s0,s1]);old=p
  k=int(np.argmin(cost));total=int(sz[k]);sel=[]
  for a,b in zip(ix[::-1],back[::-1]):sel.append(a[k]);k=b[k]
  return total,sel[::-1]
 lo=0.;hi=max(1.,max(max(c[1] for c in a) for a in ca));best=None
 for _ in range(32):
  mid=(lo+hi)/2;n,ix=search(mid)
  if n<=budget:hi=mid;best=ix
  else:lo=mid
 assert best is not None
 # greedy improvements accounting for both adjacent delta edges.
 def localcost(i,k):
  c=ca[i][k];p=c[4];prev=ca[i-1][best[i-1]][4] if i else -1;next_=ca[i+1][best[i+1]][4] if i+1<len(ca) else -1;return c[0]+delta_cost(prev,p,bits)+delta_cost(p,next_,bits)
 def total():return sum(ca[i][k][0]+delta_cost(ca[i-1][best[i-1]][4] if i else -1,ca[i][k][4],bits) for i,k in enumerate(best))
 rem=budget-total()
 for _ in range(100):
  choices=[]
  for i,(a,k) in enumerate(zip(ca,best)):
   bc=localcost(i,k)
   for j,c in enumerate(a):
    if c[1]>=a[k][1]:continue
    db=localcost(i,j)-bc;dg=a[k][1]-c[1]
    if db<=rem:choices.append((dg/max(db,0.1),dg,i,j,db))
  if not choices:break
  _,_,i,j,db=max(choices);best[i]=j;rem-=db
 return [a[i] for a,i in zip(ca,best)],budget-rem

def write_stream(path,sel,n,frame,grid,K,L):
 w=Writer();old=-1;nb=int(math.log2(grid));counts=Counter()
 for _,_,v,m,p in sel:
  if p>=0 and old>=0:
   w.bits.extend(v[:2]);d=p-old
   if abs(d)<=7:w.put(d+7,4);counts['delta']+=1
   else:w.put(15,4);w.put(p,nb);counts['escape']+=1
   w.bits.extend(v[2+nb:])
  else:w.bits.extend(v);counts['absolute']+=int(p>=0)
  old=p
 Path(path).write_bytes(struct.pack(HEADER2,b'LP4P',n,frame,grid,K,L)+w.bytes());return len(w.bits),dict(counts)

def decode(path,book):
 raw=Path(path).read_bytes();magic,n,frame,grid,K,L=struct.unpack_from(HEADER2,raw);assert magic==b'LP4P' and book.shape==(K,L);r=Reader(raw[struct.calcsize(HEADER2):]);wt=wave_table(book);st=steps(grid);old=-1;out=[];modes=[];nb=int(math.log2(grid));kb=int(math.log2(K))
 for pos in range(0,n,frame):
  m=r.get(2);nn=min(frame,n-pos);p=np.zeros(nn);pi=-1
  if m:
   if old<0:pi=r.get(nb)
   else:
    delta=r.get(4);pi=r.get(nb) if delta==15 else old+delta-7
   assert 0<=pi<grid;waves=[]
   for _ in range(m):i=r.get(kb);a=r.get(8);g=r.get(8);waves.append(wave(wt[i],st[pi],a,g,nn))
   p=waves[0] if m==1 else waves[0]*(1-np.linspace(0,1,nn))+waves[1]*np.linspace(0,1,nn)
  old=pi;s=r.get(7);k=r.get(2);q=np.zeros(nn);j=-1
  while r.get(1):
   gap=(r.unary()<<k)|r.get(k);j+=gap+1;assert j<nn;z=r.eg()+1;q[j]=z*(-1 if r.get(1) else 1)
  out.append(p+idct(q*SCALES[s],norm='ortho'));modes.append(m)
 assert not r.bits[r.pos:].any() and len(r.bits)-r.pos<8;return np.concatenate(out),np.array(modes),r.pos

def run(clip,train_path,test_path,out,K,L,grid,frame):
 out=Path(out);out.mkdir(exist_ok=True,parents=True);x=np.load(test_path)['target'];book,count=train(np.load(train_path)['target'],K,L);book.tofile(out/'book.bin');wt=wave_table(book);fft=[np.fft.rfft(w,axis=1) for w in (wt,wt*wt,wt*np.roll(wt,-1,axis=1))];p0=np.arange(0,len(x),frame);f0=pitch_analysis(x,np.minimum(p0+frame//2,len(x)-1));a=[];start=time.time()
 for k,(p,(fr,score)) in enumerate(zip(p0,f0)):
  a.append(candidates(x[p:p+frame],fr,wt,fft,grid,K,320))
  if k%300==299:print(clip,k+1,'s',round(time.time()-start,1),flush=True)
 budget=(int(len(x)*1000/FS)-struct.calcsize(HEADER2))*8;rows=[]
 for tag,modes in [('transform',(0,)),('sample',(0,1)),('morph',(0,1,2))]:
  sel,sz=alloc(a,budget,grid,modes);path=out/(tag+'.lp4p');n,dc=write_stream(path,sel,len(x),frame,grid,K,L);assert n==sz;z,m,nb=decode(path,book);assert n==nb and np.isclose(np.dot(x-z,x-z),sum(c[1] for c in sel),rtol=1e-6);np.save(out/(tag+'.npy'),z);met=dict(clip=clip,profile=tag,frame=frame,grid=grid,K=K,L=L,train_cycles=count,bytes=path.stat().st_size,kbps=path.stat().st_size*8*FS/len(x)/1000,book_bytes=book.nbytes,dds_table_bytes=grid*2,frame_count=len(m),mode_counts=np.bincount(m,minlength=3).tolist(),delta=dc,pcm_snr=10*np.log10(np.dot(x,x)/np.dot(x-z,x-z)));assert met['kbps']<=8;rows.append(met);print('PACKED',met,flush=True)
 (out/'results.json').write_text(json.dumps(rows,indent=2))
if __name__=='__main__':run(sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4],*map(int,sys.argv[5:]))

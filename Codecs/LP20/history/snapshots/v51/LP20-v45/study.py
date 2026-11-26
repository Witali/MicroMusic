import heapq, math, struct, json
from pathlib import Path
import numpy as np
from trellis42 import read_frames
from v42 import *
from repack import decode_r

def lengths(freq):
    heap=[(int(f)+1,i,[i]) for i,f in enumerate(freq)];heapq.heapify(heap);ln=[0]*len(heap);k=len(heap)
    while len(heap)>1:
        a,_,x=heapq.heappop(heap);b,_,y=heapq.heappop(heap)
        for i in x+y:ln[i]+=1
        heapq.heappush(heap,(a+b,k,x+y));k+=1
    return ln

def codes(lens):
    c=0;p=0;out={}
    for i in sorted(range(len(lens)),key=lambda i:(lens[i],i)):
        n=int(lens[i]);c<<=n-p;out[i]=(c,n);c+=1;p=n
    assert c==1<<p
    return out

def eglen(v):return 2*(int(v)+1).bit_length()-1

def pairs(frames):
    out=[]
    for m,par,p,s,k,q,_ in frames:
        nz=np.flatnonzero(q);prev=-1
        for j in nz:
            out.append((prev,int(j)-prev-1,abs(int(q[j])),int(q[j])<0,len(nz),s));prev=int(j)
    return np.array(out,dtype=int)

def ctx(prev,nz,s,typ):
    if typ==0:return 0
    if typ==1:return int(prev>=32)+int(prev>=96)
    if typ==2:return int(prev>=16)+int(prev>=48)+int(prev>=96)
    if typ==3:return int(prev>=32)+int(prev>=96)+3*int(nz>=36)
    if typ==4:return int(prev>=32)+int(prev>=96)+3*int(s>=65)
    raise ValueError(typ)

def nc(typ):return [1,3,4,6,6][typ]
def indexes(data,G,M,typ):
    p,g,m,sg,nz,s=data.T
    c=np.zeros(len(p),int)
    if typ in (1,3,4):c=(p>=32).astype(int)+(p>=96)
    if typ==2:c=(p>=16).astype(int)+(p>=48)+(p>=96)
    if typ==3:c+=3*(nz>=36)
    if typ==4:c+=3*(s>=65)
    return c*((G+1)*M)+np.minimum(g,G)*M+np.minimum(m,M)-1

def build(data,G,M,typ):
    f=np.bincount(indexes(data,G,M,typ),minlength=nc(typ)*(G+1)*M).reshape(nc(typ),-1)
    return [lengths(row) for row in f]

def cost(data,lens,G,M,typ):
    p,g,m,sg,nz,s=data.T
    return int(np.asarray(lens).ravel()[indexes(data,G,M,typ)].sum()+np.sum(2*np.floor(np.log2(g[g>=G]-G+1))+1)+np.sum(2*np.floor(np.log2(m[m>=M]-M+1))+1)+len(p))

def baseline(hdr,frames):
    n,fr,grid,K,L,b=hdr;pm=0;pp=();ps=None;head=0;coef=0;count=0
    st=steps(grid)
    for m,par,p,s,k,q,_ in frames:
        nz=np.flatnonzero(q);head+=sum(v for _,v in fields(m,par,pm,pp,grid,K,fr,st))+ (7 if ps is None else sum(w for _,w in delta(s,ps,7,4)));count+=(len(nz)>>5)+6;coef+=2;prev=-1
        for j in nz:
            gap=int(j)-prev-1;prev=int(j);coef+=(gap>>k)+1+k+eglen(abs(int(q[j]))-1)+1
        pm,pp,ps=m,par,s
    return head,count,coef

if __name__=='__main__':
    src=Path(__file__).resolve().parent;data={};frs={};hdrs={};base={}
    for clip in ['first','second']:
        h,f=read_frames(src/clip/'morph.lp42',(src/clip/'book.bin').read_bytes());hdrs[clip]=h;frs[clip]=f;data[clip]=pairs(f);base[clip]=baseline(h,f)
    rows=[]
    for G in [2,3,4,6,8,12]:
        for M in [3,4,6,8,12,16]:
            for typ in range(5):
                row=[G,M,typ];ok=True
                for clip,train in [('first','second'),('second','first')]:
                    l=build(data[train],G,M,typ)
                    if max(map(max,l))>15:ok=False;break
                    h,c,_=base[clip]
                    sz=struct.calcsize(HEADER42)+3+math.ceil((G+1)*M*nc(typ)/2)+math.ceil((h+c+cost(data[clip],l,G,M,typ))/8)
                    row.append(sz)
                if ok:rows.append(row)
    rows.sort(key=lambda r:sum(r[3:]));print('best joint G M context sizes',rows[:20]);Path('sweep.json').write_text(json.dumps(rows,indent=1))

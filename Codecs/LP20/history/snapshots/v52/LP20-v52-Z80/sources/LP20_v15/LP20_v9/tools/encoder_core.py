#!/usr/bin/env python3
"""Adaptive LPC/VQ encoder; all arithmetic matches the NMOS Z80 byte decoder.
Training is clip-specific unless -- separate training is supplied by caller.
"""
import os
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
import math, json, struct, argparse
from pathlib import Path
import numpy as np
from scipy.signal import resample_poly,butter,sosfiltfilt
from scipy.io.wavfile import read,write
from numba import njit
from pystoi import stoi
ROOT=Path(__file__).resolve().parent
FS=15625;SR=48000;K=255;SCALE=112.;GAIN=.6*SCALE/128

def load(path):
    sr,x=read(path);d=x.dtype
    x=x.astype(float)/(max(abs(np.iinfo(d).min),np.iinfo(d).max) if np.issubdtype(d,np.integer) else 1)
    if x.ndim>1:x=x.mean(axis=1)
    g=math.gcd(FS,sr);x=resample_poly(x,FS//g,sr//g);x-=x.mean();x*=.97/max(np.max(np.abs(x)),1e-12);return x

def coeff(X,Y,order):
    R=X.T@X;R.flat[::order+1]+=max(np.trace(R)/order*.003,1e-8);a=np.linalg.solve(R,X.T@Y);gamma=.985
    while True:
        c=a*gamma**np.arange(1,order+1)
        if np.sum(abs(c))<=4 and max(abs(np.roots(np.r_[1,-c])))<=.985:return c
        gamma*=.98

def design(t,order,nb,frame=64):
    hist=np.r_[np.zeros(order),t];X=np.stack([hist[order-i-1:order-i-1+len(t)] for i in range(order)],axis=1);Y=t
    if nb==1:return np.array([coeff(X,Y,order)]),np.zeros(len(t),np.int16),X
    f=np.arange(len(t))//frame;nf=f[-1]+1
    # cluster local normalized autocorrelation features; weight lightly by energy
    F=[];energy=[]
    for i in range(nf):
        yy=Y[f==i];xx=X[f==i];z=np.sum(yy*yy);energy.append(z);F.append((xx.T@yy)/(z+100.))
    F=np.array(F);energy=np.array(energy);weights=np.sqrt(energy+1000.);weights/=weights.mean()
    rng=np.random.default_rng(202607);c=[np.average(F,axis=0,weights=weights)]
    for i in range(1,nb):
        d=np.min(np.sum((F[:,None,:]-np.array(c)[None,:,:])**2,axis=2),axis=1)*weights;c.append(F[rng.choice(nf,p=d/d.sum())])
    c=np.array(c)
    for _ in range(30):
        ids=np.argmin(np.sum((F[:,None,:]-c[None,:,:])**2,axis=2),axis=1)
        for j in range(nb):
            mask=ids==j
            if mask.any():c[j]=np.average(F[mask],axis=0,weights=weights[mask])
    # Refit LPC using actual waveforms for each bank. Reassign frames by prediction error.
    for _ in range(5):
        a=np.array([coeff(X[ids[f]==j],Y[ids[f]==j],order) if np.sum(ids==j)>1 else coeff(X,Y,order) for j in range(nb)])
        err=(Y[:,None]-X@a.T)**2
        costs=np.array([np.bincount(f,weights=err[:,j],minlength=nf) for j in range(nb)]).T
        new=costs.argmin(axis=1)
        if np.all(new==ids):break
        # avoid empty groups
        if len(set(new))<nb:break
        ids=new
    a=np.array([coeff(X[ids[f]==j],Y[ids[f]==j],order) for j in range(nb)])
    return a,ids[f],X

def tables(a):
    v=np.arange(256,dtype=np.int16);v[v>=128]-=256
    return np.rint(a[:,:,None]*v[None,None,:]).astype(np.int16)

def impulse(a,n):
    h=np.zeros(n);h[0]=1
    for i in range(1,n):h[i]=sum(a[j]*h[i-j-1] for j in range(min(i,len(a))))
    return np.array([[h[i-j] if i>=j else 0 for j in range(n)] for i in range(n)],np.float32)

def init_book(r,a,k,seed):
    rng=np.random.default_rng(seed);r=r.astype(np.float32);M=impulse(a,r.shape[1]);z=r@M.T
    if len(r)==0:r=np.zeros((1,len(M)),np.float32);z=r.copy()
    book=np.zeros((k,r.shape[1]),np.float32);cz=np.zeros_like(book);d=np.sum(z*z,axis=1)
    for j in range(1,k):
        i=rng.choice(len(r),p=d/d.sum()) if d.sum()>0 else rng.integers(len(r));book[j]=r[i];cz[j]=z[i];d=np.minimum(d,np.sum((z-cz[j])**2,axis=1))
    zn=np.sum(z*z,axis=1)
    for _ in range(12):
        ix=np.argmin(zn[:,None]+np.sum(cz*cz,axis=1)[None,:]-2*z@cz.T,axis=1)
        sums=np.zeros_like(book,dtype=np.float64);np.add.at(sums,ix,r);cnt=np.bincount(ix,minlength=k);good=np.flatnonzero(cnt[1:])+1;book[good]=sums[good]/cnt[good,None];cz=book@M.T
    return np.clip(np.rint(book),-128,127).astype(np.int16)

def initialize(t,order,nb,n):
    a,assign,X=design(t,order,nb,64);tb=tables(a);x=np.clip(np.rint(t),-128,127).astype(np.int16);h=np.r_[np.zeros(order,np.int16),x];pred=np.stack([sum(tb[j,i,h[order-1-i:order-1-i+len(t)]&255] for i in range(order)) for j in range(nb)],axis=1);r=np.clip(x[:,None]-pred,-128,127);lab=assign[::n]
    # Codebook allocation proportional to sqrt(usage times residual energy), with a floor.
    mass=np.array([np.sqrt(max(1,np.sum(r[assign==j,j]**2,dtype=np.float64))*max(1,np.sum(lab==j))) for j in range(nb)])
    counts=np.full(nb, min(24,K//nb),int);rest=K-counts.sum();raw=rest*mass/mass.sum();counts+=raw.astype(int)
    for j in np.argsort(-(raw-raw.astype(int)))[:K-counts.sum()]:counts[j]+=1
    bk=[];bm=[]
    for j in range(nb):
        rr=r[:,j].reshape(-1,n)[lab==j];bk.append(init_book(rr,a[j],counts[j],2603+j));bm.extend([j]*counts[j])
    return a,tb,np.vstack(bk),np.array(bm,np.uint8)

@njit(cache=True)
def samp(h,tab,r):
    s=int(r)
    for i in range(len(h)):s+=int(tab[i,h[i]&255])
    y=((s+128)&255)-128
    for i in range(len(h)-1,0,-1):h[i]=h[i-1]
    h[0]=y
    return y,s!=y
@njit(cache=True)
def qout(y,mid):return max(-mid,min(mid,(y*mid+64)//128))*(128./mid)
@njit(cache=True)
def cost(y,w,target,pe,weight,mid):
    e=qout(y,mid)-target;d=y-target;lo=.75*e+.25*pe
    return .85*((1-weight)*e*e+weight*lo*lo)+.15*d*d+(250000. if w else 0.),e
@njit(cache=True)
def simulate(target,bk,tb,bm,idx,weight,mid):
    n=bk.shape[1];order=tb.shape[1];h=np.zeros(order,np.int16);y=np.empty(len(target),np.int16);hist=np.empty((len(idx),order),np.int16);w=0;tot=0.;pe=0.
    for b,k in enumerate(idx):
        hist[b]=h
        for j in range(n):
            p=b*n+j;v,wr=samp(h,tb[bm[k]],bk[k,j]);y[p]=v;w+=int(wr);c,pe=cost(v,wr,target[p],pe,weight,mid);tot+=c
    return y,hist,tot,w
@njit(cache=True)
def beam(target,bk,tb,bm,width,weight,mid):
    n=bk.shape[1];order=tb.shape[1];nb=len(target)//n
    oldh=np.zeros((width,order),np.int16);oldc=np.full(width,1e30);oldc[0]=0.
    newh=np.empty_like(oldh);newc=np.empty_like(oldc);parent=np.empty(width,np.uint8);code=np.empty(width,np.uint8);parents=np.empty((nb,width),np.uint8);codes=np.empty((nb,width),np.uint8);tmp=np.empty(order,np.int16);active=1
    for b in range(nb):
        off=b*n;newc[:]=1e30;count=0
        for q in range(active):
            for k in range(len(bk)):
                tmp[:]=oldh[q];c=oldc[q];pe=0. if b==0 else qout(tmp[0],mid)-target[off-1]
                for j in range(n):
                    v,w=samp(tmp,tb[bm[k]],bk[k,j]);z,pe=cost(v,w,target[off+j],pe,weight,mid);c+=z
                    if c>=newc[width-1]:break
                if c>=newc[width-1]:continue
                dup=-1
                for z in range(count):
                    eq=True
                    for i in range(order):
                        if newh[z,i]!=tmp[i]:eq=False;break
                    if eq:dup=z;break
                if dup>=0:
                    if c>=newc[dup]:continue
                    for z in range(dup,count-1):newc[z]=newc[z+1];newh[z]=newh[z+1];parent[z]=parent[z+1];code[z]=code[z+1]
                    count-=1;newc[count]=1e30
                at=min(count,width-1)
                while at>0 and c<newc[at-1]:newc[at]=newc[at-1];newh[at]=newh[at-1];parent[at]=parent[at-1];code[at]=code[at-1];at-=1
                newc[at]=c;newh[at]=tmp;parent[at]=q;code[at]=k;count=min(width,count+1)
        active=count;oldc[:]=newc;oldh[:]=newh;parents[b]=parent;codes[b]=code
    idx=np.empty(nb,np.uint8);q=0
    for b in range(nb-1,-1,-1):idx[b]=codes[b,q];q=parents[b,q]
    y,h,c,w=simulate(target,bk,tb,bm,idx,weight,mid)
    return idx,y,h,c,w
@njit(cache=True)
def local(k,bk,tb,bm,t,start,pos,f,l,weight,mid):
    n=bk.shape[1];h=np.empty(tb.shape[1],np.int16);tot=0.
    for i in range(f,l):
        b=pos[i];h[:]=start[b];off=b*n;pe=0. if b==0 else qout(h[0],mid)-t[off-1]
        for j in range(n):
            v,w=samp(h,tb[bm[k]],bk[k,j]);c,pe=cost(v,w,t[off+j],pe,weight,mid);tot+=c
    return tot
@njit(cache=True)
def refine(bk,tb,bm,t,start,pos,offset,step,weight,mid):
    out=bk.copy();m=bm.copy();n=bk.shape[1]
    for k in range(len(bk)):
        f,l=offset[k],offset[k+1]
        if f==l:continue
        best=local(k,out,tb,m,t,start,pos,f,l,weight,mid)
        for j in range(n):
            old=out[k,j];val=old
            for d in (-2*step,-step,step,2*step):
                if not -128<=old+d<=127:continue
                out[k,j]=old+d;c=local(k,out,tb,m,t,start,pos,f,l,weight,mid)
                if c<best:best=c;val=old+d
            out[k,j]=val
        # jointly try assigning codeword to another LPC bank; rederive residual
        # from its reconstructed start and target. In practice only retain a
        # reassignment if closed-loop error really decreases.
        oldb=m[k];oldv=out[k].copy();bv=oldv.copy();bb=oldb
        for bank in range(tb.shape[0]):
            if bank==oldb:continue
            m[k]=bank
            rsum=np.zeros(n,np.float64)
            for i in range(f,l):
                b=pos[i];h=start[b].copy()
                for j in range(n):
                    x=int(np.rint(t[b*n+j]));p=0
                    for a in range(len(h)):p+=int(tb[bank,a,h[a]&255])
                    rsum[j]+=max(-128,min(127,x-p))
                    for a in range(len(h)-1,0,-1):h[a]=h[a-1]
                    h[0]=x
            for j in range(n):out[k,j]=int(np.rint(rsum[j]/(l-f)))
            c=local(k,out,tb,m,t,start,pos,f,l,weight,mid)
            if c<best:best=c;bv=out[k].copy();bb=bank
        out[k]=bv;m[k]=bb
    return out,m


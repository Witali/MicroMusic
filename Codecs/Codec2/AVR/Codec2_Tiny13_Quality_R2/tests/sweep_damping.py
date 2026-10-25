import math,sys,numpy as np
from pathlib import Path
sys.path.insert(0,'/mnt/data/Codec2_Tiny13_Optimized/tests')
from test_codec2tiny import fields
P=Path(__file__).resolve().parents[1]
ks=[round(256*math.sin(math.pi*100*i/8000)) for i in range(31)]
def s8(x):return (x&255)-256 if x&128 else x
def tq(a,b):return a//b if a>=0 else -((-a)//b)
def sweep(data,damping=0,scale=1):
 pp=0; pos=[0]*3;v=[0]*3;phase=0;noise=0xa5;result=[];outfrac=0;statesat=0;maxs=0
 for q in range(0,len(data),8):
  fr=data[q:q+8];v0,v1,p,e,l=fields(fr)
  k=[];su=0
  for j in range(6):
   d=l[j]+1 if j not in (3,4,5) or l[j]<8 else 2*l[j]-6
   su=(su+d)&255
   if j%2==0:old=su
   else:k.append(ks[min(30,((old+su)>>1)>>2)])
  step=410+22*p+(p>>2)+(p>>3)
  for t in range(160):
   vv=v0 if t<80 else v1
   tmp=phase+step;pulse=tmp>=65536;phase=tmp&65535
   if vv:exc=((e>>2)+1)*scale if pulse else 0
   else:
    noise^=(noise<<3)&255;noise&=255
    noise^=(noise>>5);noise&=255
    noise^=(noise<<1)&255;noise&=255
    exc=((e>>3)+1)*scale *(-1 if noise&128 else 1)
   out=0
   for j in range(3):
    vv=s8(v[j]);yy=s8(pos[j]);vnew=(vv-tq(k[j]*yy,128))&255
    vi=s8(vnew)
    if damping==0:leak=tq(vi,16)
    elif damping==1:leak=((vi+15)//16) if vi>0 else (vi//16)
    elif damping==2:leak=(vi//16)
    else:leak=tq(vi+8 if vi>=0 else vi-8,16)
    vn=(vnew-leak+exc)
    if vn<0 or vn>255: pass
    vn&=255
    ynew=(pos[j]+tq(k[j]*s8(vn),128))
    if ynew<0 or ynew>255:pass
    ynew&=255
    if not -128 <= vi-leak+exc<=127:statesat+=1
    if not -128 <= yy+tq(k[j]*s8(vn),128)<=127:statesat+=1
    maxs=max(maxs,abs(vi),abs(s8(ynew)))
    v[j]=vn;pos[j]=ynew;out+=s8(ynew)
   outfrac+=(abs(out)>=63)
   result.append((out*2+128)&255)
 a=np.array(result,dtype=np.uint8)
 return (round(float(np.mean(a.astype(np.int16)-128)),2),round(float(np.std(a.astype(np.int16)-128)),2),round(float(outfrac/len(a)*100),2),round(float(statesat/len(a)),3),maxs)
for name in ['speech.c2zx','codec2_3200_8byte_frames.bin']:
 d=(P/'tests'/name).read_bytes()
 for dam in range(4):
  for scale in [1,2]:print(name,'dam',dam,'scale',scale,'mean,std,overflow%,state-overflow/sample,maxstate',sweep(d,dam,scale))

#!/usr/bin/env python3
"""MicroMusic HQ4: reproducible AVR-bit-exact speech parameter search + assembly.
Changes only speech data; code remains the verified 406-byte HQ3 mul_q4 optimized decoder.
For each candidate, checks Flash, STOI, spectral difference and waveform clicks.
"""
import os,time,random,json,hashlib,csv,subprocess,sys,argparse
from pathlib import Path
import numpy as np,soundfile as sf
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'MicroMusic_MiniLPC_HQ2'))
from model import decode
from quality import Compare
BASE=ROOT/'MicroMusic_MulQ4_Opt_release'
REF=ROOT/'MicroMusic_HQ3_Verified_Release'
NAMES=['chego','otvechaesh','vinni'];CODE_SIZE=406;MAX=1024-CODE_SIZE-1

def unpack(b):
 i=0;rows=[];dur=[];old=[0]*4
 while i<len(b):
  h=b[i];i+=1
  if h==255:break
  if h&192==192:duration=((h&3)*64 or 256);p=b[i];i+=1
  else:duration=((h>>6)*64 or 256);p=h&63
  ctrl=b[i];i+=1;t=ctrl>>6
  if t==0:old=list(b[i:i+4]);i+=4
  elif t==2:old[:2]=b[i:i+2];i+=2
  elif t==3:old[2:]=b[i:i+2];i+=2
  rows.append([p,ctrl&63,*old]);dur.append(duration)
 assert i==len(b)
 return np.array(rows,np.uint8),np.array(dur,np.uint16)

def pack(f,d):
 b=bytearray();old=np.zeros(4,np.uint8)
 for row,ns in zip(f,d):
  p=int(row[0]);ns=int(ns)
  if p<=63:b.append(p|{64:64,128:128,256:0}[ns])
  else:b.extend([192|{64:1,128:2,256:0}[ns],p])
  k=row[2:6]
  if np.array_equal(k,old):t=1
  elif np.array_equal(k[:2],old[:2]):t=3
  elif np.array_equal(k[2:],old[2:]):t=2
  else:t=0
  b.append((t<<6)|(int(row[1])&63))
  if t==0:b.extend(k)
  if t==2:b.extend(k[:2])
  if t==3:b.extend(k[2:])
  old=k.copy()
 return bytes(b)

def update_coeff(f,i,k,val):
 j=2+k//2;v=int(f[i,j]);f[i,j]=((v&15)|(val<<4)) if k&1 else ((v&240)|val)

def build(name,ff,dd,ref):
 out=ROOT/'HQ4'/name;out.mkdir(parents=True,exist_ok=True)
 stream=pack(ff,dd)
 assert np.array_equal(unpack(stream)[0],ff) and np.array_equal(unpack(stream)[1],dd)
 (out/'speech.hq').write_bytes(stream)
 (out/'firmware.S').write_text((BASE/name/'firmware.S').read_text())
 subprocess.run(['clang','-target','avr','-mmcu=attiny13','-c','firmware.S','-o','firmware.o'],cwd=out,check=True,capture_output=True)
 subprocess.run(['llvm-objcopy','-O','binary','firmware.o','firmware.bin'],cwd=out,check=True,capture_output=True)
 data=(out/'firmware.bin').read_bytes();assert len(data)<=1024 and data[406:406+len(stream)]==stream and data[-1]==255
 lines=[]
 for off in range(0,len(data),16):
  chunk=list(data[off:off+16]);arr=[len(chunk),(off>>8)&255,off&255,0]+chunk;arr.append(-sum(arr)&255);lines.append(':'+''.join(f'{x:02X}' for x in arr))
 (out/'firmware.hex').write_text('\n'.join(lines+[':00000001FF'])+'\n')
 pcm=decode(ff,dd,0);(out/'expected_pcm.raw').write_bytes(pcm.tobytes());sf.write(out/'preview.wav',(pcm.astype('float32')-128)/128,7500,subtype='PCM_16')
 np.savez(out/'parameters.npz',frames=ff,durations=dd)
 quality=Compare(ref).scores(pcm)
 return {'phrase':name,'stoi':float(quality[0]),'spectral_error':float(quality[1]),'clicks_48':int(quality[2]),'flash_bytes':len(data),'speech_bytes':len(stream),'code_bytes':406,'frames':len(ff),'samples':len(pcm),'sha256':hashlib.sha256(data).hexdigest()}

def train(name,seconds=15,seed=20261022):
 f,d=unpack((BASE/name/'speech.hq').read_bytes())
 assert pack(f,d)==(BASE/name/'speech.hq').read_bytes()
 ref,sr=sf.read(REF/name/'original.wav');assert sr==7500
 comp=Compare(ref);initial=comp.scores(decode(f,d,0));best=initial[0]-0.003*initial[1]
 rng=random.Random(seed);accepted=0;evals=0;start=time.monotonic()
 print(name,'initial',initial,'data',len(pack(f,d)),flush=True)
 while time.monotonic()-start<seconds:
  i=rng.randrange(len(f));col=rng.randrange(11);ff=f.copy()
  if col==0:
   if f[i,0]:ff[i,0]=max(15,min(126,int(f[i,0])+rng.choice([-4,-3,-2,-1,1,2,3,4])))
  elif col==1:
   if f[i,0] and rng.random()<.2:ff[i,0]=0
   else:
    head=int(f[i,1]);ff[i,1]=(head&48)|max(0,min(15,(head&15)+rng.choice([-2,-1,1,2])))
  elif col==2:
   head=int(f[i,1]);ff[i,1]=(head&15)|(rng.randrange(4)<<4)
  else:
   k=col-3;j=2+k//2;v=(int(f[i,j])>>(4*(k&1)))&15;nv=max(0,min(15,v+rng.choice([-2,-1,1,2])));update_coeff(ff,i,k,nv)
  if len(pack(ff,d))>MAX:continue
  val=comp.scores(decode(ff,d,0));evals+=1
  if val[2] or val[0]<initial[0]-0.00002:continue
  obj=val[0]-0.003*val[1]
  if obj>best+0.000005:
   best=obj;f=ff;accepted+=1
 fin=build(name,f,d,ref);fin['initial_stoi']=initial[0];fin['trials']=evals;fin['accepted']=accepted
 print(name,'result',fin,flush=True)
 return fin

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--seconds',type=float,default=15);ap.add_argument('--names',nargs='+',default=NAMES);args=ap.parse_args()
 results=[train(n,args.seconds,20261022+i) for i,n in enumerate(args.names)]
 (ROOT/'HQ4'/'results.json').write_text(json.dumps(results,indent=2,ensure_ascii=False))
 with (ROOT/'HQ4'/'report.csv').open('w',newline='') as fh:
  w=csv.DictWriter(fh,fieldnames=results[0].keys());w.writeheader();w.writerows(results)

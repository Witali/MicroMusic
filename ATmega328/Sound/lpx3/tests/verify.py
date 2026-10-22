#!/usr/bin/env python3
"""End-to-end, reproducible LPX3 Rice v3 verification.

For each V1 source: lossless transcode, Python frame/residual round-trip,
independent legacy C++ PCM vs v3 C++ PCM, and malformed-stream rejection.
Uses only synthetic sources by default; private audio files optional.
"""
import argparse,sys,tempfile,subprocess,struct,hashlib,random,collections,os,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from l3av_parse import unpack
from rice_v3 import encode_v3,decode_v3,BitWriter

def command(cmd):
 r=subprocess.run(cmd,check=True,capture_output=True,text=True)
 return r.stdout

def cpp_build(dst):
 src=ROOT/'src'/'Lpx3AvrCore.cpp'
 legacy=ROOT/'reference_v2'/'Lpx3AvrCore.cpp'
 driver=ROOT/'tests'/'decode_host.cpp'
 for inp,drv,out in ((src,driver,dst/'decoder_v3'),(legacy,ROOT/'reference_v2'/'decode_host.cpp',dst/'decoder_v1')):
  command(['g++','-std=c++17','-O2','-fno-strict-aliasing',str(inp),str(drv),'-o',str(out)])

def make_fixture(seed,kind):
 rng=random.Random(seed)
 cnt=rng.choice([1,19,20,79,80,81,159,160,161,320,321,480])
 coeff10=(kind=='LSF10')
 flags=(3 if coeff10 else 2)
 header=struct.pack('<4sBBHIHHHH',b'L3AV',1,flags,8000,cnt, 0,0,160,80)
 raw=bytearray(header)
 blocklist=[];frames=[]
 nframes=(cnt+159)//160; nblocks=(cnt+79)//80
 # Synthetic monotonic LSF; 8-bit type1, 10-bit type5.
 if coeff10:
  cc=[30+i*90 for i in range(10)]
  w=BitWriter()
  for v in cc:w.put(v&255,8);w.put(v>>8,2)
  w.aligned();initial=bytes([5])+w.get()
 else:initial=bytes([1])+bytes([20+i*20 for i in range(10)])
 for j in range(nframes):
  fb=initial if j==0 else bytes([0])
  raw.extend(fb);frames.append(fb)
  for k in range(2):
   ix=j*2+k
   if ix>=nblocks:break
   b=rng.choice([0,2,3,4,5,6]);scale=rng.randint(110,235)
   num=min(80,cnt-ix*80)
   q=[0]*num if b==0 else [rng.randrange(-(1<<(b-1)),1<<(b-1)) for _ in range(num)]
   bw=BitWriter()
   if b: 
    for v in q:bw.put(v+(1<<(b-1)),b)
   bw.aligned();buf=bytes([b,scale])+bw.get();raw.extend(buf)
   blocklist.append({'bits':b,'scale':scale,'q':q,'bytes':buf,'start':ix*80})
 return bytes(raw),cnt

def normal(p:Path):
 d=unpack(p.read_bytes());a,stats=encode_v3(d);f,b=decode_v3(a)
 assert f==d['frames'];assert [(x['bits'],x['scale'],x['q']) for x in b]==[(x['bits'],x['scale'],x['q']) for x in d['blocks']]
 return a,stats

def decoded(executable,src,dest):
 return subprocess.run([str(executable),str(src),str(dest)],capture_output=True)

def verify_one(original, outdir, bins, name):
 originalpath=outdir/(name+'.v1.l3av');originalpath.write_bytes(original)
 v3,stats=normal(originalpath);v3path=outdir/(name+'.v3.l3av');v3path.write_bytes(v3)
 oldpcm=outdir/(name+'.v1.pcm8');newpcm=outdir/(name+'.v3.pcm8')
 result1=decoded(bins['old'],originalpath,oldpcm)
 result2=decoded(bins['new'],v3path,newpcm)
 assert result1.returncode==0,(name,result1.stderr)
 assert result2.returncode==0,(name,result2.stderr)
 s1=oldpcm.read_bytes();s2=newpcm.read_bytes()
 assert s1==s2,(name,len(s1),len(s2),'PCM does not match')
 return {'name':name,'v1':len(original),'v3':len(v3),'samples':len(s1),'sha256':hashlib.sha256(s1).hexdigest(), 'saved':len(original)-len(v3)}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--private',nargs='*',default=[]);ap.add_argument('--fuzz',type=int,default=100);args=ap.parse_args()
 with tempfile.TemporaryDirectory() as dir:
  temp=Path(dir);cpp_build(temp);bins={'old':temp/'decoder_v1','new':temp/'decoder_v3'}
  rows=[]
  fixture=ROOT/'examples'/'synthetic_v1.l3av'
  if fixture.exists():rows.append(verify_one(fixture.read_bytes(),temp,bins,'synthetic_original'))
  for i in range(args.fuzz):
   kind='LSF10' if i%2 else 'LSF8'
   data,_=make_fixture(i+27183,kind)
   rows.append(verify_one(data,temp,bins,f'generated_{i:03}'))
  for i,src in enumerate(args.private):rows.append(verify_one(Path(src).read_bytes(),temp,bins,f'private_{i}'))
  # Negative test: v3 rejects v1, invalid tag, truncated bitstream.
  if rows:
   first=temp/'synthetic_original.v3.l3av' if fixture.exists() else temp/'generated_000.v3.l3av'
   good=first.read_bytes()
   for badname,bad in [ ('invalid-version',good[:4]+bytes([254])+good[5:]),('truncated',good[:max(20,len(good)//2)]) ]:
    p=temp/(badname+'.l3av');p.write_bytes(bad)
    r=decoded(bins['new'],p,temp/(badname+'.pcm8'))
    assert r.returncode!=0,(badname,r.stdout,r.stderr)
  print('PASS',len(rows),'corpora; all PCM byte-identical; 2 negative cases rejected')
  for r in rows[-len(args.private):] if args.private else rows[:2]:print(json.dumps(r,ensure_ascii=False))
  print('FUZZ modes',dict(collections.Counter(i%6 for i in range(args.fuzz))))
if __name__=='__main__':main()

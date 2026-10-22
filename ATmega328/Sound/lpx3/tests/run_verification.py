#!/usr/bin/env python3
"""Repeatable tests: original L3AV vs Rice/v2 dictionary on host and AVR-object build.
Contains no copyrighted speech samples; provide v1 input paths as optional arguments.
"""
import argparse,sys,math,subprocess,hashlib,struct,tempfile,json,os,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from l3av_parse import unpack
from offline_pair_dictionary import compress,decompress,rice_candidate,BitWriter

def call(c):
 r=subprocess.run(c,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 if r.returncode:
  raise RuntimeError(f'FAIL {c}:\n{r.stdout}\n{r.stderr}')
 return r.stdout.strip()

def fixture():
 b=bytearray(struct.pack('<4sBBHIHHHH',b'L3AV',1,3,8000,160*64,10000,0,160,80))
 pats=[(i%64-32,(((i//64)*17+(i*23)%64)%64)-32) for i in range(120)]
 assert len(set(pats))==120
 for fi in range(64):
  b+=bytes([5])+bytes(13) if fi==0 else bytes([0])
  for half in range(2):
   pos=fi*2+half
   pairs=[pats[((pos//8)*13 + (i*3)%53)%120] for i in range(40)]
   bw=BitWriter()
   for p in pairs:
    for q in p:bw.put(q+32,6)
   b+=bytes([6,127])+bw.bytes()
 return bytes(b)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--l3av',nargs='*',default=[]);ap.add_argument('--full',action='store_true');args=ap.parse_args()
 with tempfile.TemporaryDirectory() as tdir:
  tdir=Path(tdir)
  flags=['-std=c++11','-O2','-DLPX3_FAST_LPC_INTERP','-DLPX3_LPC_SEGMENTS=2']
  bins={}
  for cap in (0,64,512):
   out=tdir/f'decoder_{cap}'
   print(call(['c++',*flags,f'-DLPX3_PAIR_DICT_BYTES={cap}',str(ROOT/'src/Lpx3AvrCore.cpp'),str(ROOT/'tests/decode_host.cpp'),'-o',str(out)]))
   bins[cap]=out
  files=[('synth',fixture())]
  for p in args.l3av:files.append((Path(p).stem,Path(p).read_bytes()))
  allreports=[]
  for name,data in files:
   doc=unpack(data);fname=tdir/(name+'.v1.l3av');fname.write_bytes(data)
   base=tdir/(name+'.ref.pcm8')
   print(call([str(bins[0]),str(fname),str(base)]))
   opts=[]
   for cap in (64,128,256,512):
    for win in (4,8,16,32,512):
     for rice in (False,True):
      d,stats=compress(doc,cap,win,True,True,rice)
      fs,bs=decompress(d)
      assert fs==doc['frames']
      assert [(x['bits'],x['scale'],x['q']) for x in bs]==[(x['bits'],x['scale'],x['q']) for x in doc['blocks']]
      opts.append((d,stats,rice))
   for cap in (64,128,256,512):
    best=min((x for x in opts if x[1]['cap']==cap and x[2]),key=lambda x:x[1]['bytes'])
    dat,stats,_=best;encoded=tdir/(name+f'-{cap}.l3av');encoded.write_bytes(dat)
    pcm=tdir/(name+f'-{cap}.pcm8')
    print(call([str(bins[512]),str(encoded),str(pcm)]))
    assert pcm.read_bytes()==base.read_bytes()
    assert len(dat)<=len(data)
   # Force dynamic dictionary mode even when no compression, test references.
   for cap in (64,512):
    d,stats=compress(doc,cap,8 if cap==512 else 4,True,False,False)
    out=tdir/(name+f'-force-dict-{cap}.l3av');out.write_bytes(d)
    pcm=tdir/(name+f'-force-dict-{cap}.pcm8')
    print(call([str(bins[512]),str(out),str(pcm)]))
    assert pcm.read_bytes()==base.read_bytes()
    if name=='synth':
     assert stats['cold_hits']>0,stats
     assert stats['updates']>0,stats
     assert stats['dict_blocks']>0
   best_rice=min((x for x in opts if x[2]),key=lambda x:x[1]['bytes'])
   report={k:v for k,v in best_rice[1].items() if k not in ('fallback',)}
   report.update(name=name,bytes_v1=len(data),sha256_ref_pcm=hashlib.sha256(base.read_bytes()).hexdigest())
   allreports.append(report)
  # Reject an uninitialized dictionary reference (first pattern in first block).
  bad=bytearray(fixture());bad[4]=2;bad[5]=(bad[5]&3)|4|(3<<4)
  first_block=20+14
  bad[first_block]=0x46  # 6-bit quantizer, pair-dictionary flag
  bad[first_block+2]=1 # LSB bit prefix 10 + slot #0, no prior update
  corrupted=tdir/'invalid-first-reference.l3av';corrupted.write_bytes(bad)
  x=subprocess.run([str(bins[512]),str(corrupted),str(tdir/'corrupted.pcm8')],capture_output=True)
  assert x.returncode!=0 and b'decoder error=' in x.stderr, (x.returncode,x.stderr)
  # Reject invalid unbounded quotient in Rice mode.
  bad2=bytearray(fixture());bad2[4]=2;bad2[5]&=3
  bad2[first_block]=0x96 # b=6, k=1
  for ix in range(first_block+2,first_block+7):bad2[ix]=0
  corrupted2=tdir/'invalid-rice-quotient.l3av';corrupted2.write_bytes(bad2)
  y=subprocess.run([str(bins[0]),str(corrupted2),str(tdir/'corrupted2.pcm8')],capture_output=True)
  assert y.returncode!=0 and b'decoder error=' in y.stderr,(y.returncode,y.stderr)
  print('PASS two corrupt-stream negative tests')
  for a in allreports:print('VERIFIED',json.dumps(a,ensure_ascii=False))
  print(f'PASS: {len(allreports)} lossless sample corpora; synthetic includes cold references and 512B dictionary updates')

if __name__=='__main__':main()

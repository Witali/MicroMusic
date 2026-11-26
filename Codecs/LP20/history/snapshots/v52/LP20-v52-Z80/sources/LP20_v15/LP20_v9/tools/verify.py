import json,struct,subprocess,tempfile
from pathlib import Path
from build import make,unpack
ROOT=Path(__file__).resolve().parent

def ref(tb,bk,bm,stream,order,block,banks,tail=32):
 h=[0]*order;out=[0]
 for i in [*stream]+[0]*((tail+block-1)//block):
  for j in range(block):
   y=(bk[j*256+i]+sum(tb[(bm[i]*order+k)*256+h[k]] for k in range(order)))&255;out.append(y);h=[y]+h[:-1]
 return bytes(out)
def verify(args,rom=None,meta=None):
 tb,bk,bm,stream,order,block,banks,period,pulses,levels=args
 if rom is None:rom,_,meta=make(*args)
 expect=ref(tb,bk,bm,stream,order,block,banks);dm=b''.join(struct.pack('<HH',a,w) for a,w in zip(meta['dispatch'],meta['widths']))
 with tempfile.TemporaryDirectory() as td:
  d=Path(td);(d/'rom').write_bytes(rom);(d/'map').write_bytes(dm);(d/'expected').write_bytes(expect)
  p=subprocess.run([str(ROOT/'test_cpu'),str(d/'rom'),str(d/'map'),str(d/'expected'),str(period),str(pulses),str(meta['port']),str(meta['high'])],capture_output=True,text=True)
  if p.returncode:raise RuntimeError(p.stderr)
  return json.loads(p.stdout)
def main():
 import numpy as np, argparse
 p=argparse.ArgumentParser();p.add_argument('--payload');p.add_argument('--rom');p.add_argument('--meta');a=p.parse_args()
 if a.payload:
  assert a.rom and a.meta
  print(json.dumps(verify(unpack(a.payload),Path(a.rom).read_bytes(),json.loads(Path(a.meta).read_text())),indent=2));return
 rng=np.random.default_rng(20);out=[]
 for order in (4,6,8,10):
  for period,pulses,levels in [(250,5,97),(200,6,121),(160,8,97),(128,10,77)]+([(120,10,73)] if order<10 else []):
   for n in (4,8,16):
    bk=np.tile(np.arange(256,dtype=np.uint8),(n,1));bm=np.arange(256,dtype=np.uint8)%4
    args=(bytes(order*4*256),bk.tobytes(),bm.tobytes(),bytes(range(1,256)),order,n,4,period,pulses,levels)
    a=verify(args);assert a['levels_exercised']==levels,(a,levels)
    tb=rng.integers(0,256,size=order*4*256,dtype=np.uint8).tobytes();bk=rng.integers(0,256,size=(n,256),dtype=np.uint8);bk[:,0]=0
    args=(tb,bk.tobytes(),bm.tobytes(),rng.integers(1,256,size=127,dtype=np.uint8).tobytes(),order,n,4,period,pulses,levels)
    b=verify(args);out.append(dict(order=order,period=period,block=n,levels=levels,coverage=a,random=b));print(order,period,n,a['levels_exercised'],b['samples_including_boot_and_tail'],flush=True)
 (ROOT/'synthetic_tests.json').write_text(json.dumps(out,indent=2))
if __name__=='__main__':main()

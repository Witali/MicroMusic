#!/usr/bin/env python3
"""Cross-check LPX4 Python and native C++ decoders, plus LPX3 v7 reference PCM."""
import sys,subprocess,tempfile,random,hashlib,json,struct
from pathlib import Path
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/'tools'))
sys.path.insert(0,str(Path('/mnt/data/LPX3_Optimization_2026-10-23/MicroMusic_LPX3_RiceV7_Compact_Huff3/tests')))
from l3av_parse import unpack
from lpx4 import encode,decode
from rice_v7 import encode_v7
from verify import gen

def exec_decoder(exe,source,output):
 r=subprocess.run([str(exe),str(source),str(output)],capture_output=True)
 if r.returncode!=0:raise AssertionError((r.returncode,r.stderr.decode(),r.stdout.decode()))
 return output.read_bytes()

def run(nfuzz=100):
 old=Path('/mnt/data/LPX3_Optimization_2026-10-23/decode_v7')
 ours=R/'tests'/'decode_host'
 rows=[]
 with tempfile.TemporaryDirectory() as td:
  tmp=Path(td)
  sources=[('synthetic',Path('/mnt/data/LPX3_Optimization_2026-10-23/MicroMusic_LPX3_RiceV7_Compact_Huff3/examples/synthetic_v1.l3av').read_bytes())]
  sources += [(str(i),gen(20261024+i)) for i in range(nfuzz)]
  sources += [(n,Path('/mnt/data/LPX3_Optimization_2026-10-23/inputs/'+n+'_v1.l3av').read_bytes()) for n in ['xtuj-ntt','ne-otv','vinni']]
  for label,raw in sources:
   doc=unpack(raw)
   compressed,info,chunk,outq=encode(doc)
   frames,blocks,back=decode(compressed)
   assert outq==back and outq==[v for b in doc['blocks'] for v in b['q']]
   assert [(x['bits'],x['scale']) for x in doc['blocks']]==[(x['bits'],x['scale']) for x in blocks]
   q1=[int(v) for f in frames for v in f]
   v7,_=encode_v7(doc)
   (tmp/'new.l4hy').write_bytes(compressed);(tmp/'old.l3av').write_bytes(v7)
   pcmnew=exec_decoder(ours,tmp/'new.l4hy',tmp/'new.pcm8')
   pcmold=exec_decoder(old,tmp/'old.l3av',tmp/'old.pcm8')
   assert pcmnew==pcmold,(label, 'PCM different')
   rows.append({'label':label,'samples':doc['sampleCount'],'bytes_lpx3_v7':len(v7),'bytes_lpx4':len(compressed),'sha256':hashlib.sha256(pcmnew).hexdigest(), 'pitch_subframes':info.get('exact',0)})
  # malformed bitstream detection
  invalid=[];last=bytes(compressed)
  for k in range(1,17):
   broken=last[:-k]
   (tmp/'broken.l4hy').write_bytes(broken)
   r=subprocess.run([str(ours),str(tmp/'broken.l4hy'),str(tmp/'broken.pcm8')],capture_output=True)
   assert r.returncode!=0,('truncated silently',k)
   invalid.append(k)
  for i,value in enumerate((bytes([0]),bytes([3]),bytes([255]))):
   broken=bytearray(last);broken[4]=value[0]
   (tmp/'broken.l4hy').write_bytes(broken)
   assert subprocess.run([str(ours),str(tmp/'broken.l4hy'),str(tmp/'broken.pcm8')],capture_output=True).returncode!=0
 out={'passed':len(rows),'negatives_passed':len(invalid)+3,'items':rows[-3:]}
 (R/'reports'/'verification.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
 print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__':run(int(sys.argv[1]) if len(sys.argv)>1 else 100)

#!/usr/bin/env python3
"""Integration tests for LPX3-AVR ROM codec and foreground decode.
Private voice samples are optional. Synthetic test is always available.
"""
import json,struct,subprocess,sys,io,random,hashlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from pack_lpx3_avr import pack_bits_lsb,pack_huffman,HEADER,transcode
PLAYER=ROOT/'build/decode_host'

def run(infile:Path,outfile:Path):
 p=subprocess.run([str(PLAYER),str(infile),str(outfile)],capture_output=True,text=True)
 assert p.returncode==0,(p.stderr,infile)
 return outfile.read_bytes()

def test_synthetic():
 data=ROOT/'examples/LPX3_PROGMEM/synthetic_voice.l3av'
 out=ROOT/'build/synthetic.pcm8'
 pcm=run(data,out);assert len(pcm)==16000
 assert np.std(np.frombuffer(pcm,dtype=np.uint8))>8,'synthetic waveform is silent'
 assert len(set(pcm))>10
 print('PASS: synthetic audio / 16000 samples')

def test_huffman():
 rng=random.Random(50)
 cases=[]
 for bmode in [2,3,4,0x83]:
  for n in [1,2,13,55,80,160]:
   arr=[rng.randrange(8) for _ in range(n)] if bmode==0x83 else [rng.randrange(1<<bmode) for _ in range(n)]
   cases.append((bmode,n,arr))
 for mode,n,codes in cases:
  expected=pack_huffman(codes) if mode==0x83 else pack_bits_lsb(codes,mode)
  if mode==0x83:
   bitstr=''.join(format(x,'08b') for x in expected);lookup={v:k for k,v in __import__('pack_lpx3_avr').HUFF.items()}
   decoded=[];cur=''
   for bit in bitstr:
    cur+=bit
    if cur in lookup:decoded.append(lookup[cur]);cur=''
    if len(decoded)==n:break
  else:
   b=mode;decoded=[];val=buf=0
   for bit in np.unpackbits(np.frombuffer(expected,dtype=np.uint8),bitorder='little'):
    val|=int(bit)<<buf;buf+=1
    if buf==b:
     decoded.append(val);val=buf=0
    if len(decoded)==n:break
  assert decoded==codes,(mode,n)
 print('PASS: entropy coding roundtrip 24 cases')

def test_corrupt():
 valid=(ROOT/'examples/LPX3_PROGMEM/synthetic_voice.l3av').read_bytes()
 cases=[b'',b'BAD'+valid[3:],valid[:13],valid[:31],valid[:-1],valid[:20]+bytes([99])+valid[21:]]
 for i,data in enumerate(cases):
  test=ROOT/f'build/malformed_{i}.l3av';test.write_bytes(data)
  p=subprocess.run([str(PLAYER),str(test),str(ROOT/'build/invalid.pcm8')],capture_output=True)
  assert p.returncode!=0,(i,p.stdout.decode())
 print('PASS: invalid magic/truncation/unexpected frame tag rejected')

def test_source_voices():
 src=ROOT.parent/'private_inputs';rows=[]
 if not src.exists():return []
 for phrase in ('vinni','xtuj-ntt','ne-otv'):
  d=src/phrase
  if not (d/'voice_v3_3bit.lpx3').exists():continue
  for srcbits in (2,3,4):
   f=d/f'voice_v3_{srcbits}bit.lpx3'
   if not f.exists():continue
   for qbits in (8,10):
    out=ROOT/'build'/f'{phrase}_{srcbits}bit_lsf{qbits}.l3av'
    info=transcode(f,out,coeff_bits=qbits,representation='lsf',rdo_tolerance=.004 if srcbits==3 else None)
    pcm=run(out,ROOT/'build'/f'{phrase}_{srcbits}bit_lsf{qbits}.pcm8')
    assert len(pcm)==info['samples']
    rows.append({'voice':phrase,'input_bits':srcbits,'coeff_bits':qbits,'samples':info['samples'],
                 'old_bytes':info['original_lpx3_bytes'],'new_bytes':info['l3av_bytes'],'sha256':hashlib.sha256(pcm).hexdigest()})
 print('PASS: private 3 voices x 3 input bit depths x 2 coefficient bit depths',len(rows),'streams')
 return rows

if __name__=='__main__':
 test_synthetic();test_huffman();test_corrupt();rows=test_source_voices()
 (ROOT/'reports/regression_streams.json').write_text(json.dumps(rows,indent=2))
 print('PASS ALL TESTS')

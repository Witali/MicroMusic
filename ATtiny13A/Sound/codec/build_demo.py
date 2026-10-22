#!/usr/bin/env python3
"""Rebuild a copyright-free 16-frame native VBR test speech on ATtiny13A."""
from pathlib import Path
import json,subprocess,hashlib
import numpy as np
from vbr_codec import expand
from reference_model import decode
ROOT=Path(__file__).resolve().parent
D=ROOT/'synthetic';D.mkdir(exist_ok=True)
# Synthetic made-up waveform, not from a copyrighted utterance.
coeff=[0x89,0x76,0x97,0x87]
stream=bytearray()
for i in range(16):
 pitch=0 if i in (5,10) else (18+(i%5)*3)
 gain=(3+i%6)&15
 profile=i%4
 kind=0 if i in (0,4,8,12) else (1 if i%3==1 else (2 if i%3==2 else 3))
 row=bytes([pitch,gain|(profile<<4)|(kind<<6)])
 if kind==0:
  coeff=[(0x89+i)%256,0x76,0x97,0x87];row+=bytes(coeff)
 elif kind==2:row+=bytes(coeff[:2])
 elif kind==3:row+=bytes(coeff[2:])
 stream.extend(row)
(D/'speech.vbr').write_bytes(stream)
frames=expand(bytes(stream))
(D/'expected_pcm.raw').write_bytes(bytes(decode(frames.ravel())))
# Source is from the synthetic-source-only distribution; 388 bytes of AVR code.
source=(D/'firmware.S').read_text()
assert '.set VOICE_ADDR,0x184' in source
subprocess.run(['clang','-target','avr','-mmcu=attiny13','-c','firmware.S','-o','fw.o'],cwd=D,check=True)
subprocess.run(['llvm-objcopy','-O','binary','fw.o','firmware.bin'],cwd=D,check=True)
b=(D/'firmware.bin').read_bytes()
assert len(b)==0x184+len(stream)+1 and len(b)<=1024
rows=[]
for a in range(0,len(b),16):
 block=b[a:a+16];fields=[len(block),a>>8,a&255,0,*block];rows.append(':'+''.join(f'{n:02X}' for n in fields+[(-sum(fields))&255]))
(D/'firmware.hex').write_text('\n'.join(rows+[':00000001FF'])+'\n')
print('Synth demo:',len(b),'Flash bytes,',len(stream),'speech bytes;',len(frames),'frames',hashlib.sha256(b).hexdigest())

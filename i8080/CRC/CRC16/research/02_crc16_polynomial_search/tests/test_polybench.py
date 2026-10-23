#!/usr/bin/env python3
"""Intel 8080 CRC-16 reproducible emulation tests, table-free and ROM-only.
No third-party packages required.
"""
import os,sys,random
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from crc8080_tools import assemble, crc, patch_rom, emulate

PROFILES={
 'odd-fast':('poly0007_36B',0x0007,36,6885169,32767),
 'fastest':('poly0009_33B',0x0009,33,6164278,57337),
 'balanced':('poly001B_38B',0x001B,38,8130353,59055),
 'primitive':('poly002D_39B',0x002D,39,8785713,65535),
}


def flip(rom, offsets):
   out=bytearray(rom)
   for i in offsets:
       assert 0 <= i < 524288
       out[i//8]^=1<<(7-(i%8))
   return out


def p_order(p):
  a=1
  for k in range(1,65536):
    a=((a<<1)^(p if a&0x8000 else 0))&65535
    if a==1:return k
  raise AssertionError('period did not return')


def test_step(p):
  rng=random.Random(p)
  for _ in range(80000):
    state=rng.randrange(65536)
    b=rng.randrange(256)
    t=b^(state>>8)
    if p==0x0007:product=t^(t<<1)^(t<<2)
    elif p==0x0009:product=t^(t<<3)
    elif p==0x001b:product=(t^(t<<1))^((t^(t<<1))<<3)
    elif p==0x002d:product=(t^(t<<2))^((t^(t<<2))<<3)
    else:raise AssertionError(p)
    closed=(((state&255)<<8)^product)&0xffff
    # Independent bitwise long division on a 2-byte state and one message byte
    step=state^(b<<8)
    for _ in range(8):step=((step<<1)^(p if step&0x8000 else 0))&65535
    assert step==closed,(p,state,b,step,closed)


def test_profile(name, rng):
  asm,p,nbytes,tstates,order=PROFILES[name]
  src=(ROOT/'src'/f'{asm}.asm').read_text()
  binary,labels=assemble(src)
  assert len(binary)==nbytes,(name,len(binary))
  assert p_order(p)==order
  (ROOT/'src'/f'{asm}.bin').write_bytes(binary)
  rom=patch_rom(binary,poly=p)
  assert crc(rom,p)==0
  assert rom[-2:]==crc(rom[:-2],p).to_bytes(2,'big')
  info=emulate(rom,init=rng.randrange(256),crc_layout='HC',trace_addresses=True)
  assert info['cycles']==tstates,(name,info['cycles'],tstates)
  assert info['INTE'] and info['CRC']==0 and info['DE']==0
  assert info['rom_reads']==65536 and info['unique_rom_reads']==65536
  print(name,hex(p),len(binary),'bytes',info['cycles'],'cycles',round(info['cycles']/65536,6),'T/B','GOOD PASS',flush=True)
  if p!=0x0007:return
  # Correct firmware with random contents; CRC footer recomputed from scratch
  random_rom=bytearray(rom)
  random_rom[len(binary):-2]=rng.randbytes(65534-len(binary))
  random_rom[-2:]=crc(random_rom[:-2],p).to_bytes(2,'big')
  correct=emulate(random_rom,crc_layout='HC')
  assert correct['INTE'] and correct['CRC']==0
  print('  random image: PASS',flush=True)
  for pos in [0x0100*8,0x7fff*8+4,0x8000*8,0xfffe*8,0xffff*8+7]:
    bad=flip(rom,[pos]);assert crc(bad,p)!=0
    out=emulate(bad,crc_layout='HC')
    assert not out['INTE'] and out['CRC']==crc(bad,p) and out['rom_reads']==65536
  print('  five isolated errors including CRC footer: detected',flush=True)
  # Any three flipped positions MUST be detected with factor (x+1).
  bad=flip(rom,[0x1000*8+4,0x1234*8+7,0x7400*8+2])
  out=emulate(bad,crc_layout='HC')
  assert not out['INTE'] and out['CRC']==crc(bad,p)
  print('  triple error: detected',flush=True)
  # Explicit undetectable TWO-bit error: pair distance equal to order=32767 bits.
  start=0x2000*8
  undetected=flip(rom,[start,start+order])
  assert crc(undetected,p)==0
  out=emulate(undetected,crc_layout='HC')
  assert out['INTE'] and out['CRC']==0
  print('  intentional 2-bit collision: NOT detected (expected)',flush=True)
  # Polynomial itself is a 4-bit codeword, span 17 bits:
  # x^16 + x^2 + x +1 => bit errors at positions from left [0,14,15,16].
  undetected=flip(rom,[start,start+14,start+15,start+16])
  assert crc(undetected,p)==0
  out=emulate(undetected,crc_layout='HC')
  assert out['INTE'] and out['CRC']==0
  print('  intentional local 4-bit collision: NOT detected (expected)',flush=True)
  # Test all one-bit positions algebraically (2KiB block and entire 64KiB ROM)
  s=1
  for i in range(524288):
    assert s!=0
    s=((s<<1)^(p if s&0x8000 else 0))&0xffff
  # All pairs are different within 2 KiB codeword; all triples rejected by x+1.
  assert order>2048*8 and p.bit_count()%2==1
  print('  all single positions + 2KiB <=3-bit guaranteed detection: PASS',flush=True)


def main():
  r=random.Random(0x8080)
  for name in PROFILES:
     test_step(PROFILES[name][1]);test_profile(name,r)
  print('PASS: emulator, arithmetic, intentional undetected patterns',flush=True)

if __name__=='__main__':main()

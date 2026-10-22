#!/usr/bin/env python3
"""Single NEW-only HQ3 bitstream (AVR compatible). No legacy mode.
Variable frame length in 64-sample units, 4 excitation profiles,
8 signed Q4 lattice coefficients, selective half-formant updates.
"""
import numpy as np
from pathlib import Path

def decode_stream(blob):
    pos=0;frames=[];durations=[];coeff=[0]*4
    while pos<len(blob):
        b=blob[pos];pos+=1
        if b==0xff:break
        if b&0xc0==0xc0:
            length=(b&3)*64 or 256
            pitch=blob[pos];pos+=1
        else:
            length=(b>>6)*64 or 256
            pitch=b&63
        h=blob[pos];pos+=1;kind=h>>6
        if kind==0:coeff=list(blob[pos:pos+4]);pos+=4
        elif kind==2:coeff[:2]=blob[pos:pos+2];pos+=2
        elif kind==3:coeff[2:]=blob[pos:pos+2];pos+=2
        frames.append([pitch,h&63,*coeff]);durations.append(length)
    if pos != len(blob):raise ValueError(f'Unparsed data: {len(blob)-pos}')
    return np.asarray(frames,np.uint8),np.asarray(durations,np.uint16)

def encode_stream(f,d,terminator=True):
    assert len(f)==len(d) and all(int(x) in (64,128,192,256) for x in d)
    b=bytearray();old=[0]*4
    for i,(row,length) in enumerate(zip(f,d)):
        p=int(row[0]); length=int(length)
        assert 0<=p<=126
        if p<64 and length in (64,128,256):
            b.append(p|{64:0x40,128:0x80,256:0}[length])
        else:
            b.extend((0xc0|((length//64)&3),p))
        coef=list(map(int,row[2:6])); head=int(row[1])&63
        if i==0 or (coef[:2]!=old[:2] and coef[2:]!=old[2:]):typ=0
        elif coef==old:typ=1
        elif coef[:2]!=old[:2]:typ=2
        else:typ=3
        b.append(head|typ<<6)
        if typ==0:b.extend(coef)
        if typ==2:b.extend(coef[:2])
        if typ==3:b.extend(coef[2:])
        old=coef
    if terminator:b.append(255)
    return bytes(b)

def src_size(path):
    s=Path(path).read_text()
    for line in s.splitlines():
        if '.set VOICE_ADDR,' in line:return int(line.split(',')[-1].strip(),0)
    raise RuntimeError('VOICE_ADDR missing')
if __name__=='__main__':
 for n in ['chego','otvechaesh','vinni']:
    raw=Path(__file__).parent/'inputs'/n/'speech.hq'
    f,d=decode_stream(raw.read_bytes())
    assert np.array_equal(decode_stream(encode_stream(f,d))[0],f)
    assert encode_stream(f,d,terminator=False)==raw.read_bytes()
    print(n,'frames',len(f),'samples',sum(d),'stream bytes',len(raw.read_bytes()))

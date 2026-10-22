"""HQ3 native-only VBR stream encoder/decoder for ATtiny13A. No legacy compatibility.
For native data: first octet holds duration and 6-bit pitch; extended octet for periods >=64.
Speech parameters: gain and impulse shape plus 8 signed four-bit reflection coefficients.
"""
from pathlib import Path
import numpy as np

def unpack(data):
    pos=0; frames=[]; duration=[]; types=[]; old=[0]*4
    while pos<len(data):
        h=data[pos];pos+=1
        if h==255:break
        mode=h>>6
        if mode==3:
            length=(h&3)*64
            if length==0:length=256
            p=data[pos];pos+=1
        else:
            length={0:256,1:64,2:128}[mode]
            p=h&63
        assert 0<=p<=126,(pos,h,p)
        hdr=data[pos];pos+=1
        kind=hdr>>6
        if kind==0:
            old=list(data[pos:pos+4]);pos+=4
        elif kind==2:
            old[:2]=data[pos:pos+2];pos+=2
        elif kind==3:
            old[2:]=data[pos:pos+2];pos+=2
        frames.append([p,hdr&63,*old]);duration.append(length);types.append(kind)
    assert pos==len(data) and data[pos-1]==255,(pos,len(data),data[pos-1])
    return np.asarray(frames,np.uint8),np.asarray(duration,np.int32),np.asarray(types,np.uint8)

def encode(frames,durations):
    out=bytearray(); old=[0]*4
    for f,dur in zip(frames,durations):
        pitch=int(f[0]); assert pitch<=126
        assert dur in (64,128,256)
        if pitch<=63:
            h=pitch|{64:64,128:128,256:0}[dur]
            out.append(h)
        else:
            out.extend([192|{64:1,128:2,256:0}[dur],pitch])
        new=list(map(int,f[2:6]));head=int(f[1])&63
        if new==old:kind=1
        elif new[:2]==old[:2]:kind=3
        elif new[2:]==old[2:]:kind=2
        else:kind=0
        out.append(head|(kind<<6))
        if kind==0:out.extend(new)
        elif kind==2:out.extend(new[:2])
        elif kind==3:out.extend(new[2:])
        old=new
    return bytes(out)

if __name__=='__main__':
 for n in ('chego','otvechaesh','vinni'):
    data=Path(__file__).resolve().parent/'baseline'/n/'speech.hq'
    b=data.read_bytes();f,d,k=unpack(b+b'\xff')
    print(n,'frames',len(f),'samples',sum(d),'speech',len(b),'bytes','count',np.bincount(k,minlength=4).tolist(),'repack same',encode(f,d)==b)

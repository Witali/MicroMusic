"""Reproducible stream encoder and exact numerical HQ3 decoder for optimization.
The AVR instruction interpreter must independently verify final HEX.
"""
from pathlib import Path
import numpy as np
import sys
sys.path.insert(0,str(Path(__file__).parent/'MicroMusic_MiniLPC_HQ2'))
from model import decode

CLIPS=('chego','otvechaesh','vinni')
BASE=Path(__file__).parent/'MicroMusic_MulQ4_Opt_release'
REF=Path(__file__).parent/'MicroMusic_HQ3_Verified_Release'

def unpack_stream(payload):
    """Read only HQ3-new stream, 2/4/6 byte VBR spectral updates."""
    k=[0,0,0,0]
    f=[];dur=[];i=0
    while i<len(payload):
        b=payload[i];i+=1
        if b==255:break
        cls=b&0xc0
        if cls==0xc0:
            duration=(b&3)*64 or 256
            pitch=payload[i];i+=1
        else:
            duration=cls or 256
            pitch=b&63
        hdr=payload[i];i+=1
        t=hdr>>6
        if t==0:
            k=list(payload[i:i+4]);i+=4
        elif t==2:
            k[:2]=payload[i:i+2];i+=2
        elif t==3:
            k[2:]=payload[i:i+2];i+=2
        f.append([pitch,hdr&63,*k]);dur.append(duration)
    if i!=len(payload) and payload[i:]:
        raise ValueError(f'extra bytes after EOF: {len(payload)-i}')
    return np.array(f,np.uint8),np.array(dur,np.uint16)

def pack_stream(f,d):
    out=bytearray();old=[0]*4
    for idx,(frame,n) in enumerate(zip(f,d)):
        p=int(frame[0]);h=int(frame[1])&63
        assert p<=126 and n in (64,128,192,256), (idx,p,n)
        if p<=63 and n!=192:
            out.append((int(n)&0xc0)|p)
        else:
            out.extend([0xc0|((int(n)//64)&3),p])
        k=list(map(int,frame[2:]))
        if idx==0 or (old[:2]!=k[:2] and old[2:]!=k[2:]):t=0
        elif k==old:t=1
        elif old[:2]!=k[:2]:t=2
        else:t=3
        out.append((t<<6)|h)
        if t==0:out.extend(k)
        if t==2:out.extend(k[:2])
        if t==3:out.extend(k[2:])
        old=k
    return bytes(out)

def load(name):
    b=(BASE/name/'speech.hq').read_bytes()
    f,d=unpack_stream(b)
    test=decode(f,d,0)
    return b,f,d,test

if __name__=='__main__':
    import soundfile as sf
    from pystoi import stoi
    for n in CLIPS:
        b,f,d,x=load(n)
        y,sr=sf.read(REF/n/'hq.wav');ref,sr=sf.read(REF/n/'original.wav')
        got=np.maximum(0,np.minimum(255,np.rint(y*128+128))).astype(np.uint8)
        print(n,'frames',len(f),'length',len(b),'durs',np.unique(d,return_counts=True),'N',len(x),'repack',pack_stream(f,d)==b,
              'same with wav',np.array_equal(x,got),'diff',np.count_nonzero(x!=got), 'stoi',stoi(ref,(x.astype(np.float32)-128)/128,7500,extended=False))

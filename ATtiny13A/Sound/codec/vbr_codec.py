"""MiniLPC8-VBR native-only format (no legacy decoder).

Frame duration: 256 samples.  Frame layout:
  byte 0: pitch (0=noise; 255=loop marker, never inside data)
  byte 1: gain[0..3] | voice-profile[4..5] | type[6..7]
  type 0: 4 coefficient bytes (K1..K8)  [6 bytes total]
  type 1: no coefficient bytes        [2 bytes total]
  type 2: K1..K4 only (2 bytes)      [4 bytes total]
  type 3: K5..K8 only (2 bytes)      [4 bytes total]
Coefficients are 4-bit signed with offset +8. No compatibility with previous format.
"""
import numpy as np

def parse_fixed(src):
    if len(src)%6: raise ValueError('bad fixed stream')
    return np.frombuffer(src,dtype=np.uint8).reshape((-1,6)).copy()

def compress(fixed, modes):
    if len(modes)!=len(fixed) or int(modes[0])!=0: raise ValueError('first frame must be complete')
    b=bytearray()
    old=[0]*4
    for i,(fr,m) in enumerate(zip(fixed,modes)):
        m=int(m)
        b.extend([int(fr[0]),int(fr[1]) | (m<<6)])
        k=list(int(x) for x in fr[2:6]); desired=list(old)
        if m==0: b.extend(k); desired=k
        elif m==1: pass
        elif m==2: b.extend(k[:2]);desired[:2]=k[:2]
        elif m==3: b.extend(k[2:]);desired[2:]=k[2:]
        else: raise ValueError('invalid type')
        old=desired
    return bytes(b)

def expand(bitstream,frame_count=None):
    """Full six-byte parameter frames as decoded by the AVR, for exact Python model."""
    pos=0; out=[]; k=[0]*4
    while pos<len(bitstream):
        if pos+2>len(bitstream):raise ValueError('truncated header')
        pitch=bitstream[pos]; b=bitstream[pos+1];pos+=2
        if pitch==255:raise ValueError('unexpected loop marker in payload')
        mode=b>>6
        if mode==0:
            if pos+4>len(bitstream):raise ValueError('truncated full frame')
            k=list(bitstream[pos:pos+4]);pos+=4
        elif mode==2:
            if pos+2>len(bitstream):raise ValueError('truncated low partial')
            k[:2]=bitstream[pos:pos+2];pos+=2
        elif mode==3:
            if pos+2>len(bitstream):raise ValueError('truncated high partial')
            k[2:]=bitstream[pos:pos+2];pos+=2
        out.append([pitch,b&0x3f,*k])
    if frame_count is not None and len(out)!=frame_count:raise ValueError('wrong number of frames')
    return np.array(out,dtype=np.uint8)

def decoded_coeff(fixed,modes):
    return expand(compress(fixed,modes),len(fixed))

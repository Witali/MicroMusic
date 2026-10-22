"""Adaptive interpolation stream: bit6 of each pitch header encodes fast (1) / slow (0).
No extra frame bytes; silence packets 0xE1..0xFE and loop 0xFF remain unchanged.
The maximum voiced pitch period MUST be <32 for short records, avoiding silent-opcode collisions.
"""
import numpy as np

def pack(K,P,E,key,fast):
    out=bytearray();events=[];i=0
    while i<len(P):
        if E[i]==0:
            j=i+1
            while j<len(P) and E[j]==0 and j-i<30:j+=1
            out.append(0xe0+j-i);events.append(('silence',i,j-i));i=j;continue
        pitch=int(P[i]);gain=int(E[i]); assert 0<=pitch<32 and 1<=gain<=15
        mode=0x40 if fast[i] else 0
        if key[i]:
            k=K[i].astype(int);assert np.all((-7<=k)&(k<=7))
            out.extend([mode|pitch, ((k[0]+8)<<4)|gain, ((k[2]+8)<<4)|(k[1]+8),((k[4]+8)<<4)|(k[3]+8),((k[6]+8)<<4)|(k[5]+8),k[7]+8]);events.append(('key',i,int(fast[i])))
        else:
            out.extend([0x80|mode|pitch,gain]);events.append(('short',i,int(fast[i])))
        i+=1
    return bytes(out),events

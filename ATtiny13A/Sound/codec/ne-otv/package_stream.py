"""Keyframe LPC8 format: 6-byte spectral frame or 2-byte pitch+energy event.
For nonzero-energy frames:
  0x00..0x3f + [G|K0] [K2|K1] [K4|K3] [K6|K5] [K7] = full keyframe;
  0x80..0xbf + [G] = continue spectral target, update pitch and energy.
For silence: one 0xe1..0xfe byte encodes a run of 1..30 silent frames.
0xff: loop to first frame.
"""
import argparse
from pathlib import Path
import numpy as np

def pack(K,P,E,mask):
    stream=bytearray();i=0;events=[]
    while i<len(P):
        if E[i]==0:
            j=i
            while j<len(P) and E[j]==0 and j-i<30:j+=1
            stream.append(0xe0+j-i)
            events.append(('silence',i,j-i))
            i=j;continue
        k=K[i].astype(int);pi=int(P[i]);gain=int(E[i]);is_key=bool(mask[i])
        assert all(-7<=n<=7 for n in k) and 0<=pi<64 and 1<=gain<=15
        if is_key:
            stream.extend([pi,(gain&15)|((k[0]+8)<<4),((k[2]+8)<<4)|(k[1]+8),((k[4]+8)<<4)|(k[3]+8),((k[6]+8)<<4)|(k[5]+8),(k[7]+8)])
        else:
            stream.extend([0x80|pi,gain&15])
        events.append(('key' if is_key else 'predict',i,pi))
        i+=1
    return bytes(stream),events

if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('npz');a.add_argument('--keymask');a.add_argument('--out',default='voice_tinylpc.bin');args=a.parse_args()
 z=np.load(args.npz);P=z['P'];E=z['E'];K=z['K']
 mask=np.load(args.keymask) if args.keymask else np.ones(len(P),bool)
 b,events=pack(K,P,E,mask)
 Path(args.out).write_bytes(b)
 print('voice:',len(b),'bytes;',len(P),'frames;',sum(x[0]=='key' for x in events),'keyframes;',sum(x[0]=='predict' for x in events),'short events')

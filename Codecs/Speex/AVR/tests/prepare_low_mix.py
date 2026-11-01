#!/usr/bin/env python3
"""Make padded test records for mixed rates; real API calls use exact lengths."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

def sha(data):return hashlib.sha256(data).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--corpus',type=Path,required=True)
    p.add_argument('--previous-build',type=Path,required=True);p.add_argument('--oracle',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--frames',type=int,default=1024);args=p.parse_args()
    for wb in [0,1]:
        source=[]
        for label,width,bits in [('215',6,43),('595',15,119),('395',10,79)]:
            family=('wb'+{'215':'395','595':'775','395':'575'}[label]) if wb else 'nb'+label
            packet_width=(bits+36+7)//8 if wb else width
            path=args.corpus/family/'streams/ru_square_b.spxraw'
            source.append((path,packet_width,packet_width,bits+36 if wb else bits))
        for folder,width,bits in [('wb-corpus',25,160),('higher-corpus/wb128',32,220)]:
            path=args.previous_build/folder/'streams/ru_square_b.spxraw'
            source.append((path,width,width if wb else (bits+7)//8,bits+36 if wb else bits))
        payload=[];lengths=[];meaningful=[]
        for f in range(args.frames):
            path,stride,width,bits=source[f%5];raw=path.read_bytes()
            at=(f//5)%(len(raw)//stride);packet=raw[at*stride:at*stride+width]
            payload.append(packet.ljust(32,b'\0'));lengths.append(width);meaningful.append(bits)
        out=args.out/('wb' if wb else 'nb');out.mkdir(parents=True,exist_ok=True)
        raw=b''.join(payload);(out/'packets32.bin').write_bytes(raw)
        subprocess.run([str(args.oracle),str(wb),'32',str(out/'packets32.bin'),str(out/'oracle.pcm')],check=True)
        manifest=dict(wideband=bool(wb),frames=args.frames,packetLengths=lengths,meaningfulBits=meaningful,
            inputSha256=sha(raw),pcmSha256=sha((out/'oracle.pcm').read_bytes()),
            sourceSha256={str(i):sha(path.read_bytes()) for i,(path,*_) in enumerate(source)},
            scope='32-byte test storage only; each public API call receives its original exact byte count')
        (out/'input.json').write_bytes((json.dumps(manifest,indent=2)+'\n').encode())

if __name__=='__main__':main()

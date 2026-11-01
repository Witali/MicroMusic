#!/usr/bin/env python3
"""Add valid boundary/coverage and ignored-padding streams to the low-rate corpus."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from prepare_low_profiles import PROFILES

def digest(data):return hashlib.sha256(data).hexdigest()
def frame(mode,f,wide):
    code=f'{mode:05b}'+''.join(f'{v&63:06b}' for v in [f, f>>6, f*13+(f>>9)])
    code+=f'{f&127:07b}'
    if mode in [1,8]:code+=f'{(f>>7)&15:04b}'
    code+=f'{(f>>7)&31:05b}'
    if mode==1:code+='0000'
    for sub in range(4):
        if mode==2:
            code+=f'{(f*13+sub*7)&31:05b}'
            code+=''.join(f'{(f*7+sub*3+v*5)&15:04b}' for v in range(4))
        elif mode==8:
            code+=''.join(f'{(f*7+sub*3+v*5)&31:05b}' for v in range(2))
    assert len(code)=={1:43,2:119,8:79}[mode]
    if wide:
        code+='1001'+f'{f&63:06b}'+f'{(f>>6)&63:06b}'
        code+=''.join(f'{(f*3+sub*11)&31:05b}' for sub in range(4))
    return code

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--corpus',type=Path,required=True)
    p.add_argument('--oracle',type=Path,required=True);args=p.parse_args()
    path=args.corpus/'manifest.json';manifest=json.loads(path.read_text());rows=[]
    for label,hz,rate,mode,bits in PROFILES:
        for name,frames in [('coverage4096',4096),('padding64',64)]:
            raw=[]
            for f in range(frames):
                code=frame(mode,f,hz==16000);assert len(code)==bits
                code+=('1' if name=='padding64' else '0')*((-bits)%8)
                raw.append(int(code,2).to_bytes(len(code)//8,'big'))
            payload=b''.join(raw);folder=args.corpus/label
            stream=folder/'streams'/(name+'.spxraw');oracle=folder/'oracle'/(name+'.pcm')
            stream.write_bytes(payload)
            subprocess.run([str(args.oracle),'1' if hz==16000 else '0',str((bits+7)//8),str(stream),str(oracle)],check=True)
            expected=oracle.read_bytes();assert len(expected)==frames*(640 if hz==16000 else 320)
            if name=='padding64':
                assert expected==(folder/'oracle/coverage4096.pcm').read_bytes()[:len(expected)]
            row=dict(profile=label,stream=name+'.spxraw',sampleRate=hz,bitrate=rate,
                nbSubmode=mode,packetBytes=(bits+7)//8,meaningfulBits=bits,frames=frames,
                inputSha256=digest(payload),pcmSha256=digest(expected),natural=False,
                coverage='All pitch/global-energy pairs; forced pitch/gain pairs; 4096 HB LSP pairs; innovation/gain extremes' if frames==4096 else 'Ignored padding bits flipped')
            rows.append(row);print('Prepared',label,name,frames,'frames',flush=True)
    manifest['streams']=[r for r in manifest['streams'] if r.get('stream') not in ['coverage4096.spxraw','padding64.spxraw']]+rows
    path.write_bytes((json.dumps(manifest,indent=2)+'\n').encode())

if __name__=='__main__':main()

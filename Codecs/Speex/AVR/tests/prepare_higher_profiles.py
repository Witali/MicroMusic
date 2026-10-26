#!/usr/bin/env python3
"""Encode retained speech at NB11/WB12.8 and bind it to independent Xiph PCM."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build,build_wb
from prepare_real_speech import packets
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def bits(data):return ''.join(f'{v:08b}' for v in data)
def pack(s):return bytes(int(s[i:i+8],2) for i in range(0,len(s),8))
def nb4(old,seed):
    s=bits(old);assert len(s)==160 and s[:5]=='00011';out='00100'+s[5:28]
    for sub in range(4):
        out+=s[28+33*sub:41+33*sub]
        out+=''.join(f'{(seed*37+sub*11+j*29)&127:07b}' for j in range(5))
    assert len(out)==220;return out
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cc',required=True);p.add_argument('--ffmpeg',default='ffmpeg')
    p.add_argument('--out',type=Path,default=ROOT/'build/higher-corpus');p.add_argument('--filter',default='.')
    args=p.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    for family in ['nb4','wb128']:
        for sub in ['streams','oracle','actual']:(out/family/sub).mkdir(parents=True,exist_ok=True)
    build.host(args.cc,'reference');build.host(args.cc,'profile',enable_nb4=True)
    nb=out/'nb-native.exe';shutil.copyfile(ROOT/'build/profile/decode.exe',nb)
    build_wb.host(args.cc,enable_nb4=True);build_wb.oracle(args.cc)
    wb=out/'wb-native.exe';shutil.copyfile(ROOT/'build/wb-native/decode.exe',wb)
    manifest=json.loads((ROOT/'build/real-speech/corpus.json').read_text(encoding='utf-8'));rows=[]
    def verify(family,name,raw,natural=False,source=None):
        folder=out/family;packetBytes=28 if family=='nb4' else 32
        path=folder/'streams'/(name+'.spxraw');path.write_bytes(raw)
        oracle=folder/'oracle'/(name+'.pcm');actual=folder/'actual'/(name+'.pcm')
        subprocess.run([ROOT/'build/wb-reference/decode.exe','0' if family=='nb4' else '1',str(packetBytes),path,oracle],check=True)
        subprocess.run([nb if family=='nb4' else wb,path,actual,str(packetBytes)],check=True)
        assert actual.read_bytes()==oracle.read_bytes(),(family,name,'PCM mismatch')
        row=dict(family=family,stream=name+'.spxraw',frames=len(raw)//packetBytes,packetBytes=packetBytes,
            bitrate=11000 if family=='nb4' else 12800,sampleRate=8000 if family=='nb4' else 16000,natural=natural,
            inputSha256=digest(path),pcmSha256=digest(oracle),source=source,pcmExact=True)
        rows.append(row);print('PASS',family,name,row['frames'],'exact frames',flush=True)
    for clip in manifest['clips']:
        if clip['condition']!='natural' or not re.search(args.filter,clip['id']):continue
        original=ROOT/'build/real-speech/clips'/clip['id']/'16000/input.wav';assert original.exists()
        for family,rate,bitrate,size in [('nb4',8000,11000,28),('wb128',16000,12800,32)]:
            ogg=out/(clip['id']+'-'+family+'.ogg')
            subprocess.run([args.ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-y','-i',original,'-af','apad=pad_dur=0.08',
                '-c:a','libspeex','-ar',str(rate),'-b:a',str(bitrate),'-abr','0','-vad','0','-dtx','0','-frames_per_packet','1','-f','ogg',ogg],check=True)
            frames=list(packets(ogg.read_bytes()))[2:];assert frames and all(len(f)==size and f[0]>>3==4 for f in frames)
            if family=='wb128':assert all((f[27]&15)==9 for f in frames)
            verify(family,clip['id'],b''.join(frames),True,dict(file=str(original),sha256=digest(original),language=clip['language']))
    for label,folder in [('pitch','pitch-cases'),('zero','zero-pitch-cases')]:
        for path in sorted((ROOT/'build'/folder/'streams').glob('*.spxraw')):
            data=path.read_bytes();assert len(data)%20==0
            raw=b''.join(pack(nb4(data[i:i+20],i//20)+'0000') for i in range(0,len(data),20))
            verify('nb4',label+'-'+path.stem,raw,source=dict(file=str(path),sha256=digest(path)))
    path=ROOT/'build/wb-corpus/streams/coverage_lsp4096.spxraw';data=path.read_bytes();assert len(data)==4096*25
    raw=b''.join(pack(nb4(data[i:i+20],i//25)+bits(data[i+20:i+25])[:36]) for i in range(0,len(data),25))
    verify('wb128','coverage_lsp4096',raw,source=dict(file=str(path),sha256=digest(path)))
    result=dict(scope='Retained speech, exact NB4 Xiph / HB1 compact-QMF oracle; no AVR timing claim',
        encoderVersion=subprocess.check_output([args.ffmpeg,'-version'],text=True).splitlines()[0],
        streams=rows,sourceSha256={p.relative_to(ROOT).as_posix():digest(p) for p in sorted((ROOT/'src').iterdir()) if p.is_file()},
        physicalBoardTested=False)
    (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('PASS: higher-bitrate corpus and independent native PCM prepared',flush=True)
if __name__=='__main__':main()

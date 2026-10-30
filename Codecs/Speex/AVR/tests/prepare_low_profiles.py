#!/usr/bin/env python3
"""Encode retained speech at lower rates; decode with independent Xiph oracle."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from prepare_real_speech import packets
PROFILES=[('nb595',8000,5950,2,119),('wb775',16000,7750,2,155),
          ('nb395',8000,3950,8,79),('wb575',16000,5750,8,115),
          ('nb215',8000,2150,1,43),('wb395',16000,3950,1,79)]

def sha(data):return hashlib.sha256(data).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--speech-root',type=Path,required=True)
    p.add_argument('--oracle',type=Path,required=True)
    p.add_argument('--ffmpeg',default='ffmpeg');p.add_argument('--filter',default='^(ru_|en_)')
    p.add_argument('--profiles',default=','.join(x[0] for x in PROFILES))
    p.add_argument('--frames',type=int,default=0,help='0 keeps each complete recording')
    p.add_argument('--out',type=Path,default=ROOT/'build/low-corpus');args=p.parse_args()
    names=sorted(d.name for d in args.speech_root.iterdir()
                 if d.is_dir() and re.search(args.filter,d.name) and (d/'16000/input.wav').is_file())
    if not names:p.error('No retained voice clips')
    rows=[]
    for label,hz,rate,mode,meaningful in PROFILES:
        if label not in args.profiles.split(','):continue
        folder=args.out/label
        for sub in ['streams','oracle']:(folder/sub).mkdir(parents=True,exist_ok=True)
        width=(meaningful+7)//8
        for name in names:
            original=args.speech_root/name/'16000/input.wav';ogg=folder/(name+'.ogg')
            subprocess.run([args.ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-y','-i',str(original),
                '-af','apad=pad_dur=0.08','-c:a','libspeex','-ar',str(hz),'-b:a',str(rate),
                '-abr','0','-vad','0','-dtx','0','-frames_per_packet','1','-f','ogg',str(ogg)],check=True)
            encoded=list(packets(ogg.read_bytes()))[2:]
            assert encoded and all(len(f)==width and f[0]>>3==mode for f in encoded),(label,name)
            if args.frames:encoded=encoded[:args.frames]
            raw=b''.join(encoded);path=folder/'streams'/(name+'.spxraw');path.write_bytes(raw)
            output=folder/'oracle'/(name+'.pcm')
            subprocess.run([str(args.oracle),'1' if hz==16000 else '0',str(width),str(path),str(output)],check=True)
            assert output.stat().st_size==len(encoded)*(640 if hz==16000 else 320)
            rows.append(dict(profile=label,stream=name+'.spxraw',sampleRate=hz,bitrate=rate,
                nbSubmode=mode,packetBytes=width,meaningfulBits=meaningful,frames=len(encoded),
                inputSha256=sha(raw),pcmSha256=sha(output.read_bytes()),
                source=dict(clip=name,sha256=sha(original.read_bytes())),completeRecording=not args.frames))
            print('Prepared',label,name,len(encoded),'frames',flush=True)
    report=dict(scope='Untouched Xiph NB / established compact-QMF WB oracle, not target timing',
        oracleSha256=sha(args.oracle.read_bytes()),streams=rows)
    (args.out/'manifest.json').write_bytes((json.dumps(report,indent=2)+'\n').encode())

if __name__=='__main__':main()

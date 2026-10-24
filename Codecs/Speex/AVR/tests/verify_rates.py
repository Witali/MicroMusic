#!/usr/bin/env python3
"""Compare native WB/UWB low-memory experiments to unmodified Xiph PCM.

Run prepare_real_speech.py and both build_rates.py variants first.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import wave
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from prepare_real_speech import packets

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ffmpeg',default='ffmpeg')
    args=parser.parse_args()
    corpus=ROOT/'build/real-speech'
    manifest=json.loads((corpus/'corpus.json').read_text(encoding='utf-8'))
    rows=[]
    for clip in manifest['clips']:
        if clip['condition']!='natural': continue
        for mode,rate,bitrate,packetbytes in [(1,16000,9800,25),(2,32000,11600,29)]:
            folder=corpus/'clips'/clip['id']/str(rate)
            folder.mkdir(exist_ok=True)
            subprocess.run([args.ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-y',
                            '-i',folder.parent/'original.wav','-ar',str(rate),'-c:a','pcm_s16le',folder/'input.wav'],check=True)
            subprocess.run([args.ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-y',
                            '-i',folder/'input.wav','-af','apad=pad_dur=0.08','-c:a','libspeex',
                            '-ar',str(rate),'-b:a',str(bitrate),'-abr','0','-vad','0','-dtx','0',
                            '-frames_per_packet','1','-f','ogg',folder/'encoded.ogg'],check=True)
            iterator=iter(packets((folder/'encoded.ogg').read_bytes()))
            header=next(iterator)
            fields=struct.unpack_from('<9i',header,36)
            assert fields==(rate,mode,4,1,bitrate,rate//50,0,1,0),fields
            next(iterator)
            frames=list(iterator)
            assert frames and all(len(f)==packetbytes and f[0]>>3==3 for f in frames)
            raw=b''.join(frames)
            (folder/'encoded.spxraw').write_bytes(raw)
            for variant,name in [('rates-reference','reference.pcm'),('rates-memory','memory.pcm')]:
                subprocess.run([ROOT/'build'/variant/'decode.exe',str(mode),str(packetbytes),
                                folder/'encoded.spxraw',folder/name],check=True)
            pcm=(folder/'reference.pcm').read_bytes()
            assert pcm==(folder/'memory.pcm').read_bytes(),(clip['id'],rate,'PCM differs')
            with wave.open(str(folder/'decoded.wav'),'wb') as wav:
                wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(rate); wav.writeframes(pcm)
            rows.append({'clip':clip['id'],'rate':rate,'bitrate':bitrate,'frames':len(frames),
                         'samples':len(pcm)//2,'pcmExact':True,'sha256':hashlib.sha256(pcm).hexdigest()})
            print('PASS',clip['id'],rate,len(frames),'frames',flush=True)
    report={'scope':'PC experiment; not a real-time AVR player','physicalBoardTested':False,
            'frames':sum(r['frames'] for r in rows),'samples':sum(r['samples'] for r in rows),'streams':rows}
    (corpus/'rates-verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__': main()

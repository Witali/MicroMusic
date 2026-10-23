#!/usr/bin/env python3
"""Generate a synthetic (non-copyrighted) voice example and compile AVR firmware.
Requires AVR-capable clang/llvm-objcopy. Does not use cartoon audio files.
"""
from pathlib import Path
import subprocess,hashlib
import numpy as np,soundfile as sf
from codec import encode_stream
from model import decode
ROOT=Path(__file__).resolve().parent

def main():
    dest=ROOT/'synthetic_demo';dest.mkdir(exist_ok=True)
    frames=[];durations=[]
    for i in range(38):
        # Slowly evolving formants/intonation with noise/silent sections.
        pitch=0 if i in (0,1,9,10,26,27,37) else int(22+5*np.sin(i*.37))
        gain=int(6+3*np.sin(i*.26)) if pitch else (3 if i not in (0,37) else 0)
        mode=i%4
        k=[-4+int(np.sin(i*.11)),2,-2,1,-1,1,0,0]
        packed=[(k[j]+8)|((k[j+1]+8)<<4) for j in (0,2,4,6)]
        frames.append([pitch,(mode<<4)|gain,*packed]);durations.append(256)
    f=np.asarray(frames,dtype=np.uint8);d=np.asarray(durations,dtype=np.uint16)
    stream=encode_stream(f,d);(dest/'speech.hq').write_bytes(stream[:-1])
    source=(ROOT/'firmware_template.S').read_text()
    (dest/'firmware.S').write_text(source)
    subprocess.run(['clang','-target','avr','-mmcu=attiny13','-c','firmware.S','-o','fw.o'],cwd=dest,check=True)
    subprocess.run(['llvm-objcopy','-O','binary','fw.o','firmware.bin'],cwd=dest,check=True)
    b=(dest/'firmware.bin').read_bytes();assert len(b)<=1024 and b.endswith(stream)
    y=decode(f,d)
    (dest/'expected.raw').write_bytes(y.tobytes())
    sf.write(dest/'synthetic_reference.wav',(y.astype(np.float32)-128)/128,7500,subtype='PCM_16')
    print('Synthetic demo compiled:',len(b),'bytes Flash,',len(y),'samples')
    return dest
if __name__=='__main__':main()

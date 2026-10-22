#!/usr/bin/env python3
"""Rebuild/check 3x3 native MiniLPC-HQ4 firmware variants.

The three profiles use identical AVR decoding machine code. This release changes
only compressed speech parameters after closed-loop optimization.
Requirements: clang AVR target, llvm-objcopy, NumPy, Numba, pystoi, soundfile, Node.js.
"""
from pathlib import Path
import sys,subprocess,hashlib,csv,json,shutil
import numpy as np,soundfile as sf
ROOT=Path(__file__).resolve().parent
SRC=ROOT/'baseline'
HQ3=ROOT/'references'
sys.path.insert(0,str(ROOT)); 
from hq4_codec import unpack,encode
from model import decode
from quality import Compare
PHRASES=['chego','otvechaesh','vinni']
LABELS={'chego':'Чего тебе нужно?','otvechaesh':'Что ж ты не отвечаешь?','vinni':'Сова! Открывай! Медведь пришёл!'}


def makehex(data):
    lines=[]
    for p in range(0,len(data),16):
        chunk=data[p:p+16]; rec=[len(chunk),p>>8&255,p&255,0,*chunk]
        rec.append(-sum(rec)&255)
        lines.append(':'+''.join(f'{v:02X}' for v in rec))
    return '\n'.join(lines+[':00000001FF'])+'\n'

def build():
    out=ROOT/'release';out.mkdir(exist_ok=True)
    rows=[];manifest={}
    for name in PHRASES:
        root=out/name;root.mkdir(exist_ok=True)
        for typ in ['original','lpx3']:
            shutil.copy2(HQ3/name/(typ+'.wav'),root/(typ+'.wav'))
        ref,sr=sf.read(root/'original.wav')
        assert sr==7500
        comp=Compare(ref)
        variant_data={
            'hq3':(SRC/name/'speech.hq').read_bytes(),
            'stoi':(ROOT/name/'speech.hq').read_bytes() if (ROOT/name/'speech.hq').exists() else (SRC/name/'speech.hq').read_bytes(),
            'timbre':(ROOT/name/'timbre_speech.hq').read_bytes() if (ROOT/name/'timbre_speech.hq').exists() else (SRC/name/'speech.hq').read_bytes(),
        }
        for typ,data in variant_data.items():
            d=root/typ;d.mkdir(exist_ok=True)
            (d/'speech.hq').write_bytes(data)
            shutil.copy2(SRC/name/'firmware.S',d/'firmware.S')
            subprocess.run(['clang','-target','avr','-mmcu=attiny13','-c','firmware.S','-o','firmware.o'],cwd=d,check=True,capture_output=True)
            subprocess.run(['llvm-objcopy','-O','binary','firmware.o','firmware.bin'],cwd=d,check=True,capture_output=True)
            fw=(d/'firmware.bin').read_bytes()
            assert len(fw)<=1024,(name,typ,len(fw))
            assert fw[406:406+len(data)]==data,(name,typ,'stream misplaced')
            assert fw[-1]==255
            (d/'firmware.hex').write_text(makehex(fw))
            frames,durs,_=unpack(data+b'\xff'); PCM=decode(frames,durs)
            length=len(PCM); assert length in [9216,7936,22272], (name,typ,length)
            (d/'pcm.u8').write_bytes(PCM.tobytes())
            sf.write(d/'preview.wav',(PCM.astype(np.float32)-128)/128,7500,subtype='PCM_16')
            metrics=comp.scores(PCM)
            row={'phrase':name,'codec':typ,'stoi':round(metrics[0],7),'spectral_error':round(metrics[1],5),'clicks48':int(metrics[2]),
                 'flash_bytes':len(fw),'decoder_bytes':406,'speech_bytes':len(data),'samples':length,'sha256':hashlib.sha256(fw).hexdigest()}
            print('BUILT',name,typ,'STOI',row['stoi'],'spec',row['spectral_error'],'Flash',len(fw),flush=True)
            rows.append(row)
            manifest[name+'_'+typ]=dict(row,hex_path=str(d.relative_to(out) /'firmware.hex'))
    (out/'report.json').write_text(json.dumps(rows,indent=2,ensure_ascii=False))
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False))
    with (out/'report.csv').open('w',newline='') as fi:
        w=csv.DictWriter(fi,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    shutil.copy2(SRC/'avr_emulator.js',out/'avr_emulator.js')
    return rows
if __name__=='__main__':build()

#!/usr/bin/env python3
"""Compile MiniLPC HQ4 voice streams, cycle-verify actual ATtiny13 AVR output.
Requires: clang AVR target, llvm-objcopy, node, numpy, pystoi, scipy, soundfile.
"""
import sys,shutil,hashlib,json,subprocess,base64,os,wave,io
from pathlib import Path
import numpy as np,soundfile as sf
from pystoi import stoi
from hq4_core import REF,BASE,CLIPS,load,decode,pack_stream
from optimize_hq4 import spec,clicks

ROOT=Path(__file__).resolve().parent
DEST=ROOT/'release';DEST.mkdir(exist_ok=True)
REPORT={}

def run(args,cwd=None):
    p=subprocess.run(args,cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if p.returncode:raise RuntimeError(str(args)+' failed:\n'+p.stdout+'\n'+p.stderr)
    return p.stdout

def intelhex(data):
    rows=[]
    for i in range(0,len(data),16):
        part=data[i:i+16];r=[len(part),(i>>8)&255,i&255,0,*part]
        r.append((-sum(r))&255)
        rows.append(':'+''.join(f'{v:02X}' for v in r))
    return '\n'.join(rows+[':00000001FF'])+'\n'

def wav_bytes(x,sr=7500):
    b=io.BytesIO()
    with wave.open(b,'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(sr)
        w.writeframes((np.clip(np.asarray(x,dtype=np.float64),-1,1)*32767).astype('<i2').tobytes())
    return b.getvalue()

def build():
    for n in CLIPS:
        src=BASE/n;dest=DEST/n;dest.mkdir(exist_ok=True)
        npz=np.load(ROOT/'trained'/n/'best.npz')
        f=npz['frames'];d=npz['durations'];stream=pack_stream(f,d)
        assert len(decode(f,d))=={'chego':9216,'otvechaesh':7936,'vinni':22272}[n]
        (dest/'speech.hq').write_bytes(stream)
        shutil.copy2(src/'firmware.S',dest/'firmware.S')
        # All builds use the same decoder; its fixed point of entry is 0x196 = 406 bytes.
        assert '.set VOICE_ADDR,0x196' in (dest/'firmware.S').read_text()
        run(['clang','-target','avr','-mmcu=attiny13','-c','firmware.S','-o','firmware.o'],cwd=dest)
        run(['llvm-objcopy','-O','binary','firmware.o','firmware.bin'],cwd=dest)
        binfile=(dest/'firmware.bin').read_bytes()
        assert len(binfile)<=1024,(n,len(binfile))
        assert binfile[406:406+len(stream)]==stream
        assert binfile[406+len(stream):]==b'\xff',(n,'terminator')
        (dest/'firmware.hex').write_text(intelhex(binfile))
        x=decode(f,d,0);(dest/'expected.raw').write_bytes(x.tobytes())
        ref,sr=sf.read(REF/n/'original.wav');assert sr==7500
        assert len(x)==len(ref)
        m_st=stoi(ref,(x.astype(np.float32)-128)/128,7500,extended=False)
        me={'name':n,'stoi':float(m_st),'spec':spec(ref,x),'clicks_48':clicks(x),
            'code_bytes':406,'speech_bytes':len(stream),'flash_bytes':len(binfile),
            'free_flash':1024-len(binfile),'samples':len(x),'sha256':hashlib.sha256(binfile).hexdigest()}
        REPORT[n]=me
        (dest/'hq4.wav').write_bytes(wav_bytes((x.astype(float)-128)/128))
        # Reference data for PRIVATE A/B use only.
        for filename,srcname in [('original.wav','original.wav'),('lpx3.wav','lpx3.wav'),('hq3.wav','hq.wav')]:
            shutil.copy2(REF/n/srcname,dest/filename)
        print(n,me,flush=True)
    # Node emulator verifies actual machine code for every output sample.
    shutil.copy2(BASE/'avr_emulator.js',DEST/'avr_emulator.js')
    v=Path(__file__).parent/'verify_hq4.js'
    shutil.copy2(v,DEST/'verify_hq4.js')
    out=run(['node','verify_hq4.js'],cwd=DEST)
    print(out,flush=True)
    checks=json.loads(out.split('AUDIT_JSON=')[-1])
    for name,a in checks.items():
        REPORT[name]['avr_mismatches']=a['mismatches']
        REPORT[name]['timer_misses']=a['timer_misses']
        REPORT[name]['avr_max_isr_cycles']=a['max_isr']
        assert a['mismatches']==0 and a['timer_misses']==0
    (DEST/'report.json').write_text(json.dumps(REPORT,indent=2,ensure_ascii=False))
    import csv
    with (DEST/'report.csv').open('w',newline='') as fh:
        wr=csv.DictWriter(fh,fieldnames=list(REPORT['chego']));wr.writeheader();wr.writerows(REPORT.values())
    return REPORT

if __name__=='__main__': build()

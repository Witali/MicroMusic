#!/usr/bin/env python3
"""Build MiniLPC-HQ for ATtiny13A. New-only bitstream, 64/128/256-sample frames.

A 0x7F escape introduces a 64-sample frame (followed by normal 7-bit pitch).
0x80 in ordinary pitch byte means 128 samples; no flag means 256 samples.
0xFF marks end/loop; payload formant packing unchanged from native VBR2.
"""
import re,sys,json,hashlib,subprocess
from pathlib import Path
import numpy as np
from model import decode
ROOT=Path(__file__).resolve().parent
BASE=ROOT/'baselines'

def encode(f,d):
    assert len(f)==len(d) and np.isin(d,[64,128,256]).all()
    out=bytearray(); old=[0]*4; kinds=[]
    for i,(row,length) in enumerate(zip(f,d)):
        pitch=int(row[0]);assert 0<=pitch<=126
        coeff=list(map(int,row[2:6])); head=int(row[1])&63
        if i==0 or (coeff[:2]!=old[:2] and coeff[2:]!=old[2:]): kind=0
        elif coeff==old:kind=1
        elif coeff[:2]!=old[:2]:kind=2
        else:kind=3
        kinds.append(kind)
        if length==64:out.extend([127,pitch])
        else:out.append(pitch|(128 if length==128 else 0))
        out.append(head|(kind<<6))
        if kind==0:out.extend(coeff)
        elif kind==2:out.extend(coeff[:2])
        elif kind==3:out.extend(coeff[2:])
        old=coeff
    return bytes(out),np.array(kinds,np.uint8)

def unpack(b):
    pos=0;f=[];d=[]; old=[0]*4
    while pos<len(b):
        p=b[pos];pos+=1
        if p==127:
            length=64;p=b[pos];pos+=1
        else:length=128 if p&128 else 256; p&=127
        h=b[pos];pos+=1;kind=h>>6
        if kind==0:old=list(b[pos:pos+4]);pos+=4
        elif kind==2:old[:2]=b[pos:pos+2];pos+=2
        elif kind==3:old[2:]=b[pos:pos+2];pos+=2
        f.append([p,h&63,*old]);d.append(length)
    if pos!=len(b):raise RuntimeError('stream length mismatch')
    return np.asarray(f,np.uint8),np.asarray(d,np.uint16)

def src_template():
    original=(BASE/'chego_base.S').read_text()
    original=re.sub(r'\.set VOICE_ADDR,0x[\da-fA-F]+','.set VOICE_ADDR,0x200',original)
    start=''' inc r5
 breq next_frame
 sbrs r10,7
 rjmp current_frame
 mov r16,r5
 cpi r16,128
 brne current_frame
next_frame:
 clr r5
 rcall read_frame
current_frame:'''
    replacement=''' inc r5
 cp r5,r10
 brne current_frame
 clr r5
 rcall read_frame
current_frame:'''
    assert start in original
    original=original.replace(start,replacement)
    start='''vbr_pitch:
 mov r10,r16
 andi r16,127
 mov r4,r16'''
    replacement='''vbr_pitch:
 cpi r16,127
 brne vbr_normal
 ldi r17,64
 mov r10,r17
 lpm r16,Z+
 rjmp vbr_setpitch
vbr_normal:
 mov r10,r16
 ldi r17,128
 and r10,r17
 andi r16,127
vbr_setpitch:
 mov r4,r16'''
    assert start in original
    original=original.replace(start,replacement)
    original=original.replace('.incbin "speech.vbr2"','.incbin "speech.hq"')
    return original

def symbol(obj,name):
    result=subprocess.run(['llvm-objdump','-t',str(obj)],capture_output=True,text=True,check=True)
    for row in result.stdout.splitlines():
        parts=row.split()
        if parts and parts[-1]==name:return int(parts[0],16)
    raise RuntimeError('symbol not found '+name)

def compile_one(name,frames,durs,verbose=False):
    dest=ROOT/'samples'/name;dest.mkdir(parents=True,exist_ok=True)
    stream,types=encode(frames,durs)
    ff,dd=unpack(stream)
    assert np.array_equal(ff,frames) and np.array_equal(dd,durs)
    text=src_template()
    (dest/'speech.hq').write_bytes(stream)
    (dest/'firmware.S').write_text(text)
    def assemble():
        subprocess.run(['clang','-target','avr','-mmcu=attiny13','-c','firmware.S','-o','fw.o'],cwd=dest,check=True,capture_output=True)
    assemble()
    code_size=symbol(dest/'fw.o','code_end')
    text=text.replace('.set VOICE_ADDR,0x200',f'.set VOICE_ADDR,0x{code_size:03x}')
    (dest/'firmware.S').write_text(text)
    assemble()
    subprocess.run(['llvm-objcopy','-O','binary','fw.o','firmware.bin'],cwd=dest,check=True,capture_output=True)
    data=(dest/'firmware.bin').read_bytes()
    if len(data)>1024: raise ValueError(f'{name}: {len(data)} bytes > ATtiny13A Flash 1024')
    assert data[code_size:code_size+len(stream)]==stream
    assert data[-1]==255
    record=[]
    for i in range(0,len(data),16):
        block=data[i:i+16];header=[len(block),i>>8&255,i&255,0];raw=header+list(block);raw.append(-sum(raw)&255)
        record.append(':'+''.join(f'{x:02X}' for x in raw))
    (dest/'firmware.hex').write_text('\n'.join(record+[':00000001FF'])+'\n')
    out=decode(frames,durs,0)
    (dest/'expected_pcm.raw').write_bytes(out.tobytes())
    record={'code_bytes':code_size,'speech_bytes':len(stream),'flash_bytes':len(data), 'frames':len(frames),'short_64':int(sum(durs==64)),'short_128':int(sum(durs==128)), 'samples':len(out),'sha256':hashlib.sha256(data).hexdigest()}
    if verbose: print(name,record,flush=True)
    return record

if __name__=='__main__':
    manifest={}
    for n in sys.argv[1:] or ['chego','otvechaesh','vinni']:
        src=ROOT/'samples'/n/'trained.npz'
        if src.exists():
            x=np.load(src);f=x['frames'];d=x['durations']
        else:
            x=np.load(BASE/f'{n}_refined.npz');f=x['frames'];d=x['dur']
        manifest[n]=compile_one(n,f,d,True)
    (ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False))

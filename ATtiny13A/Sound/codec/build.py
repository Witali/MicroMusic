#!/usr/bin/env python3
"""Rebuild the new-format-only MiniLPC8 pulse-profile firmware.

No old-format parser, transcoding or legacy fallback is included in the AVR.
Each samples/<voice> directory contains one firmware.S and one speech.bin.
Requires clang with AVR backend + llvm-objcopy; no Python packages needed.
"""
from pathlib import Path
import hashlib,json,subprocess
ROOT=Path(__file__).resolve().parent
VOICE_ADDR=0x16c
VOICES=('chego','otvechaesh','vinni')
report={}
for name in VOICES:
    d=ROOT/'samples'/name
    source=(d/'firmware.S').read_text()
    assert f'.set VOICE_ADDR,0x{VOICE_ADDR:x}' in source
    assert 'sbrc r22,4' in source and 'sbrc r22,5' in source
    assert 'sbrc r22,0' not in source and 'sbrc r22,1' not in source
    speech=(d/'speech.bin').read_bytes()
    assert len(speech)%6==0 and all((speech[i+1]&0xc0)==0 for i in range(0,len(speech),6))
    subprocess.run(['clang','-target','avr','-mmcu=attiny13','-c','firmware.S','-o','fw.o'],cwd=d,check=True)
    subprocess.run(['llvm-objcopy','-O','binary','fw.o','firmware.bin'],cwd=d,check=True)
    binary=(d/'firmware.bin').read_bytes()
    assert len(binary)==VOICE_ADDR+len(speech)+1, f'Unexpected gap: {name}, {len(binary)}'
    assert binary[VOICE_ADDR:VOICE_ADDR+len(speech)]==speech
    assert len(binary)<=1024
    rows=[]
    for addr in range(0,len(binary),16):
        block=binary[addr:addr+16]
        vals=[len(block),addr>>8,addr&255,0,*block]
        rows.append(':'+''.join(f'{v:02X}' for v in [*vals,(-sum(vals))&255]))
    (d/'firmware.hex').write_text('\n'.join(rows+[':00000001FF'])+'\n')
    report[name]={'flash_bytes':len(binary),'code_bytes':VOICE_ADDR,'speech_bytes':len(speech),
       'frames':len(speech)//6,'sha256':hashlib.sha256(binary).hexdigest()}
(ROOT/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))

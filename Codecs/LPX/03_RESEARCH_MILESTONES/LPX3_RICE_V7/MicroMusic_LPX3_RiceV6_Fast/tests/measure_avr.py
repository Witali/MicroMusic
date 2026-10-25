#!/usr/bin/env python3
from pathlib import Path
import subprocess,re,json
P=Path(__file__).resolve().parents[1]
BASE=['clang++','-target','avr','-mmcu=atmega328p','-Os','-ffunction-sections','-fdata-sections','-fno-exceptions','-fno-rtti','-nostdlib','-I'+str(P/'tests/avr_stub'),'-c']
ret={}
for n,path in [('v5',P/'reference_v5/Lpx3AvrCore.cpp'),('current',P/'src/Lpx3AvrCore.cpp')]:
    obj=P/'reports'/f'{n}.avr.o'
    subprocess.run(BASE+[str(path),'-o',str(obj)],check=True)
    output=subprocess.run(['llvm-objdump','-h',str(obj)],check=True,capture_output=True,text=True).stdout
    sec={}
    for line in output.splitlines():
        a=line.strip().split()
        if len(a)>3 and a[0].isdigit() and a[1].startswith(('.text','.progmem.data')):
            sec[a[1]]=int(a[2],16)
    ret[n]={'text_object_bytes':sum(v for k,v in sec.items() if k.startswith('.text')),
            'tables_object_bytes':sec.get('.progmem.data',0),
            'next_bytes':sum(v for k,v in sec.items() if '4next' in k),
            'readBlock_bytes':sum(v for k,v in sec.items() if '9readBlock' in k),
            'decodeCode_bytes':sum(v for k,v in sec.items() if '10decodeCode' in k)}
ret['warning']='Object sections only; not linked ELF, timing or real-time guarantee.'
(P/'reports'/'avr_size_comparison.json').write_text(json.dumps(ret,indent=2))
print(json.dumps(ret,indent=2))

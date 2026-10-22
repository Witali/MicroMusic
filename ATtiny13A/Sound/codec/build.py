#!/usr/bin/env python3
from pathlib import Path
import subprocess,json,hashlib
from vbr_codec import parse_fixed,expand
ROOT=Path(__file__).resolve().parent
NAMES=['chego','otvechaesh','vinni']
records={}
for name in NAMES:
 d=ROOT/'samples'/name
 asm=(d/'firmware.S').read_text()
 # The assembly template sets the exact offset of speech_data, with no gap after the code.
 import re
 code_len=int(re.search(r'\.set VOICE_ADDR,0x([0-9a-fA-F]+)',asm).group(1),16)
 data=(d/'speech.vbr').read_bytes()
 assert len(expand(data))==len(parse_fixed((d/'speech_full.bin').read_bytes()))
 subprocess.run(['clang','-target','avr','-mmcu=attiny13','-c','firmware.S','-o','fw.o'],cwd=d,check=True,stdout=subprocess.PIPE)
 subprocess.run(['llvm-objcopy','-O','binary','fw.o','firmware.bin'],cwd=d,check=True,stdout=subprocess.PIPE)
 b=(d/'firmware.bin').read_bytes()
 assert b[code_len:code_len+len(data)]==data, f'speech mismatch {name}'
 assert len(b)==code_len+len(data)+1
 assert len(b)<=1024, f'Flash overflow {name}: {len(b)}'
 lines=[]
 for i in range(0,len(b),16):
  part=b[i:i+16];items=[len(part),(i>>8)&255,i&255,0,*part]
  lines.append(':'+''.join(f'{x:02X}' for x in [*items,(-sum(items))&255]))
 (d/'firmware.hex').write_text('\n'.join(lines+[':00000001FF'])+'\n')
 records[name]={'code':code_len,'speech':len(data),'flash':len(b),'frames':len(expand(data)),'sha256':hashlib.sha256(b).hexdigest()}
(ROOT/'manifest.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
print(json.dumps(records,ensure_ascii=False,indent=2))

from pathlib import Path
import subprocess
p=Path(__file__).resolve().parent
subprocess.run(['clang','-target','avr','-mmcu=attiny13','-c','firmware.S','-o','firmware.o'],cwd=p,check=True)
subprocess.run(['llvm-objcopy','-O','binary','firmware.o','firmware.bin'],cwd=p,check=True)
b=(p/'firmware.bin').read_bytes()
assert b[0x16c:0x16c+len((p/'speech.bin').read_bytes())]==(p/'speech.bin').read_bytes()
assert len(b)<=1024
lines=[]
for off in range(0,len(b),16):
    data=list(b[off:off+16]);r=[len(data),off>>8,off&255,0,*data];r.append((-sum(r))&255)
    lines.append(':'+''.join(f'{x:02X}' for x in r))
(p/'demo.hex').write_text('\n'.join(lines+[':00000001FF'])+'\n')
print('Demo firmware flash:',len(b),'bytes')

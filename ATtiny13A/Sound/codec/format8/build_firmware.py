#!/usr/bin/env python3
"""Reproducible relocation-free bare-metal ATtiny13A firmware build.
Requires Clang with AVR backend and llvm-objcopy (or adapt to avr-as/avr-objcopy).
"""
import pathlib, shutil, subprocess
P = pathlib.Path(__file__).resolve().parent

def run(args):
    print('+', ' '.join(map(str,args)))
    subprocess.run(args, cwd=P, check=True)

clang=shutil.which('clang')
objcopy=shutil.which('llvm-objcopy') or shutil.which('avr-objcopy')
objdump=shutil.which('llvm-objdump')
if not clang or not objcopy:
    raise SystemExit('Clang with AVR target and llvm-objcopy are needed')
run([clang,'-target','avr','-mmcu=attiny13','-c','tinylpc.S','-o','tinylpc.o'])
if objdump:
    relocs=subprocess.check_output([objdump,'-r','tinylpc.o'],cwd=P,text=True)
    if 'R_AVR_' in relocs:
        raise SystemExit('Unresolved AVR relocations: this build cannot safely emit raw binary\n'+relocs)
run([objcopy,'-O','binary','tinylpc.o','tinylpc.bin'])
data=(P/'tinylpc.bin').read_bytes()
if len(data)>1024:
    raise SystemExit(f'ATtiny13A Flash exceeded: {len(data)} > 1024 bytes')
rows=[]
for a in range(0,len(data),16):
    part=data[a:a+16]
    row=bytearray([len(part),a>>8,a&255,0])+part
    rows.append(':'+row.hex().upper()+f'{(-sum(row))&255:02X}')
rows.append(':00000001FF')
(P/'tinylpc.hex').write_text('\n'.join(rows)+'\n')
print(f'Flash: {len(data)}/1024 B, free {1024-len(data)} B; '
      f'speech: {(P/"voice_tinylpc.bin").stat().st_size} B')

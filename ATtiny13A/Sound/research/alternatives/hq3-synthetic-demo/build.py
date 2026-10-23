#!/usr/bin/env python3
import subprocess
from pathlib import Path
p=Path(__file__).resolve().parent
for command in [
 ["clang","-target","avr","-mmcu=attiny13","-c","firmware.S","-o","firmware.o"],
 ["llvm-objcopy","-O","binary","firmware.o","firmware.bin"],
 ["llvm-objcopy","-O","ihex","firmware.o","firmware.hex"]]:
 subprocess.run(command,cwd=p,check=True)
b=(p/"firmware.bin").read_bytes();assert len(b)<=1024
print('Decoder = 388 B; full synthetic firmware =',len(b),'B')

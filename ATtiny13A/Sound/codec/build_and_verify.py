from pathlib import Path
import hashlib,subprocess
root=Path(__file__).resolve().parent
for name in ['chego','otvechaesh','vinni']:
 d=root/name
 subprocess.run(['clang','-target','avr','-mmcu=attiny13','-c','firmware.S','-o','firmware.o'],cwd=d,check=True)
 subprocess.run(['llvm-objcopy','-O','binary','firmware.o','rebuild.bin'],cwd=d,check=True)
 assert (d/'rebuild.bin').read_bytes()==(d/'firmware.bin').read_bytes(), name
 print(name, 'verified',len((d/'firmware.bin').read_bytes()),'bytes')
 (d/'rebuild.bin').unlink();(d/'firmware.o').unlink()
subprocess.run(['node','verify_samples.js'],cwd=root,check=True)

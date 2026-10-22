#!/usr/bin/env python3
"""Public-domain synthetic signal test; does not contain any sample from cartoons."""
import subprocess
from pathlib import Path
import numpy as np
from refine_and_build import pack
R=Path(__file__).resolve().parent
p=R/'demo';p.mkdir(exist_ok=True)
# Eight repetitions of a simple voiced synthetic pulse with flat vocal-filter response.
frames=np.asarray([[24,8,0x88,0x88,0x88,0x88]]*8,dtype=np.uint8)
durations=np.asarray([256]*8,dtype=np.uint16)
(p/'speech.hq').write_bytes(pack(frames,durations))
(p/'firmware.S').write_text((R/'firmware_template.S').read_text())
subprocess.run(['clang','-target','avr','-mmcu=attiny13','-c','firmware.S','-o','firmware.o'],cwd=p,check=True)
subprocess.run(['llvm-objcopy','-O','binary','firmware.o','firmware.bin'],cwd=p,check=True)
assert len((p/'firmware.bin').read_bytes())<=1024
print('Synthetic example:',len((p/'firmware.bin').read_bytes()),'Flash bytes')

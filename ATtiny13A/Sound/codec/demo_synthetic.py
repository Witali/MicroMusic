#!/usr/bin/env python3
"""Generate a public-domain synthetic AVR speech-like audio test (not any cartoon audio)."""
from pathlib import Path
import shutil,subprocess,json
import numpy as np,soundfile as sf
from hq4_codec import encode
from model import decode
ROOT=Path(__file__).resolve().parent
DST=ROOT/'demo_synthetic';DST.mkdir(exist_ok=True)
frames=np.asarray([
  [30,0x27,0x87,0x98,0x88,0x88],
  [27,0x18,0x87,0x98,0x88,0x88],
  [24,0x35,0x97,0x87,0x88,0x88],
  [0,0x04,0x88,0x88,0x88,0x88],
  [25,0x17,0x78,0x89,0x88,0x88],
],dtype=np.uint8)
durs=np.asarray([256,256,128,256,128],dtype=np.int32)
raw=encode(frames,durs)
(DST/'speech.hq').write_bytes(raw)
shutil.copy2(ROOT/'baseline'/'chego'/'firmware.S',DST/'firmware.S')
subprocess.run(['clang','-target','avr','-mmcu=attiny13','-c','firmware.S','-o','demo.o'],cwd=DST,check=True)
subprocess.run(['llvm-objcopy','-O','binary','demo.o','demo.bin'],cwd=DST,check=True)
fw=(DST/'demo.bin').read_bytes()
assert fw[406:406+len(raw)]==raw and fw[-1]==255 and len(fw)<=1024
signal=decode(frames,durs)
(DST/'expected.pcm.u8').write_bytes(signal.tobytes())
sf.write(DST/'demo.wav',(signal.astype(np.float32)-128)/128,7500,subtype='PCM_16')
(DST/'result.json').write_text(json.dumps({'flash_bytes':len(fw),'speech_bytes':len(raw),'samples':len(signal)},indent=2))
print(f'Synthetic demo: {len(fw)}/1024 Flash bytes; {len(raw)} byte speech data; {len(signal)} PCM samples.')

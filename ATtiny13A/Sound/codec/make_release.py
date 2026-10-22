from pathlib import Path
import zipfile, shutil
import numpy as np
import soundfile as sf
ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent
PRIVATE=BASE/'MicroMusic_MiniLPC_VBR_private.zip'
PUBLIC=BASE/'MicroMusic_MiniLPC_VBR_source_only.zip'
HTML=BASE/'MicroMusic_MiniLPC_VBR.html'
shutil.copy2(ROOT/'index.html',HTML)
for name in ('chego','otvechaesh','vinni'):
 d=ROOT/'samples'/name
 orig,sr=sf.read(ROOT/'references'/name/'original.wav',dtype='float32')
 old=np.frombuffer((d/'reference_pcm.raw').read_bytes(),dtype=np.uint8).astype(np.float32)
 new=np.frombuffer((d/'avr_pcm.raw').read_bytes(),dtype=np.uint8).astype(np.float32)
 old=(old-128)/128;new=(new-128)/128
 silence=np.zeros(int(7500*.25),dtype=np.float32)
 def norm(x):
  rm=np.sqrt(np.mean(x*x));g=min(2.5,0.16/max(rm,.001));mx=np.max(abs(x*g));return x*g*min(1,.95/max(mx,.001))
 full=np.concatenate([norm(orig),silence,norm(old),silence,norm(orig),silence,norm(new)])
 sf.write(ROOT/f'AB_{name}.wav',full,7500,subtype='PCM_16')
# Full private project: include original/copyrighted examples for evaluation only.
with zipfile.ZipFile(PRIVATE,'w',zipfile.ZIP_DEFLATED,compresslevel=8) as z:
 for p in sorted(ROOT.rglob('*')):
  if not p.is_file():continue
  if p.name.endswith('.pyc') or '__pycache__' in p.parts or p.name.endswith('.o'):continue
  if p.name in ('mobile_preview.png',):continue
  z.write(p,'MicroMusic_MiniLPC_VBR/'+str(p.relative_to(ROOT)))
# Clean-room test/source package, no copyrighted voice samples or bitstreams.
files=['vbr_codec.py','reference_model.py','avr_emulator.js','build_demo.py','verify_demo.js','requirements.txt']
text='''# MicroMusic MiniLPC8-VBR · source-only / synthetic demonstration

This archive deliberately contains **no** voice recordings, cartoon audio,
LPX3 derivatives, compressed speech from the three real examples or the
original HTML page (which embeds those clips). It demonstrates exactly the
same **new-only** AVR decoder on synthetic generated data.

The 388-byte firmware implements only the 2/4/6 byte VBR frame layout:
`pitch; gain/profile/type; optional 0, 2 or 4 packed coefficient bytes`.
Types: 00=full, 01=repeat, 10=K1–K4, 11=K5–K8.

Requirements: Clang with AVR target, llvm-objcopy, Node.js, Python and
`pip install -r requirements.txt` for the reference arithmetic model.

    python3 build_demo.py
    node verify_demo.js

After this, `synthetic/firmware.hex` is the flashable synthetic-signal demo.
The AVR model compares every sample with the independent fixed-point
reference; it is not a physical-hardware test.

To train a real voice in your own private workspace, use `optimize_vbr.py`
from the private research bundle with a local reference WAV at 7500 Hz.
For public distribution do not include copyrighted audio or derivative
speech streams without permission.
'''
with zipfile.ZipFile(PUBLIC,'w',zipfile.ZIP_DEFLATED,compresslevel=8) as z:
 z.writestr('MiniLPC8_VBR_Source/README.md',text)
 for f in files:z.write(ROOT/f,'MiniLPC8_VBR_Source/'+f)
 z.write(ROOT/'synthetic/firmware.S','MiniLPC8_VBR_Source/synthetic/firmware.S')
print(PRIVATE,PRIVATE.stat().st_size,PUBLIC,PUBLIC.stat().st_size,HTML,HTML.stat().st_size)

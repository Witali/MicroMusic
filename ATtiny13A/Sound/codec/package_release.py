#!/usr/bin/env python3
"""Prepare private reproducibility archive and source-only public demo archive."""
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
import json
ROOT=Path(__file__).resolve().parent
DEST=ROOT.parent
STEM='MicroMusic_MiniLPC_HQ2'
FULL=DEST/(STEM+'_Private.zip')
PUBLIC=DEST/(STEM+'_Source.zip')
code_files=['README.md','README_PUBLIC.md','requirements.txt','model.py','quality.py',
  'build_hq.py','train_hq.py','refine_hq.py','joint_opt.py','pulse_lab.py','noise_lab.py',
  'convert_audio.py','run_all.py','package_release.py','avr_emulator.js',
  'verify.js','make_player.py','browser_test.py','ui_smoke.js',
  'build_demo.py','demo_verify.js','baselines/chego_base.S']
for name,path in [('private',FULL),('public',PUBLIC)]:
  with ZipFile(path,'w',ZIP_DEFLATED,compresslevel=8) as z:
    if name=='private':
      for f in sorted(ROOT.rglob('*')):
        if not f.is_file():continue
        rel=f.relative_to(ROOT)
        if '__pycache__' in rel.parts or f.suffix in ('.log','.o','.pyc') or f.name.startswith('test_convert'):continue
        if f.name=='offline_player_check.js':continue
        z.write(f,arcname=f'{STEM}/{rel.as_posix()}')
    else:
      for rel in code_files:
        f=ROOT/rel
        if f.exists():z.write(f,arcname=f'{STEM}/{rel}')
      for rel in ['samples/demo/firmware.S','samples/demo/firmware.hex','samples/demo/firmware.bin','samples/demo/expected_pcm.raw','samples/demo/speech.hq']:
        f=ROOT/rel
        if f.exists():z.write(f,arcname=f'{STEM}/{rel}')
  with ZipFile(path) as z:
    assert z.testzip() is None
    print(name,path,'files',len(z.namelist()),'bytes',path.stat().st_size)
if __name__=='__main__':
  pass

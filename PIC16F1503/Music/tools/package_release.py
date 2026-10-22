#!/usr/bin/env python3
"""Create a reproducible, handoff-friendly ZIP, hashing all included files."""
from pathlib import Path
import hashlib,json,zipfile
root=Path(__file__).resolve().parents[1]
out=Path('/mnt/data/MicroMusic_PIC16F1503_port_emulator.zip')
exclude={'output/','tests/host_reference','tests/player_inline_check.js','reports/host_reference_120k.raw'}
files=[]
for p in root.rglob('*'):
    if not p.is_file():continue
    relative=p.relative_to(root).as_posix()
    if relative in exclude or relative.startswith('output/') or '__pycache__' in relative:continue
    files.append(p)
files.sort()
manifest={'project':'Witali/MicroMusic → PIC16F1503', 'status':'C sound port uncompiled by XC8; PIC diagnostic HEX executed and tested in cycle emulator', 'source':'https://github.com/Witali/MicroMusic','datasheet':'Microchip DS40001607D','files':[{ 'name':p.relative_to(root).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}for p in files]}
manifest_file=root/'SHA256_MANIFEST.json'
manifest_file.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
files.append(manifest_file)
with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=8) as z:
  for f in files:z.write(f,arcname=f.relative_to(root).as_posix())
with zipfile.ZipFile(out) as z:
 bad=z.testzip()
 assert bad is None,bad
 names=z.namelist()
 assert 'web/player.html' in names
 assert 'firmware/main.c' in names
 assert 'firmware/diagnostic_pwm_irq.hex' in names
 assert 'README.md' in names
 assert 'tests/check_c_js_parity.mjs' in names
print('ZIP',out,'files',len(files),'bytes',out.stat().st_size,'SHA256',hashlib.sha256(out.read_bytes()).hexdigest())

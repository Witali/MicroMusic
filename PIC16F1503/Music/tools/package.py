#!/usr/bin/env python3
"""Reproducible handoff archive, includes all sources, emulator and diagnostics."""
from pathlib import Path
import hashlib,zipfile,json
root=Path(__file__).resolve().parents[1]
out=root.parent/'MicroMusic_PIC16F1503_assembly_complete.zip'
files=sorted(f for f in root.rglob('*') if f.is_file() and '__pycache__' not in f.parts and f.name not in ('.DS_Store','MANIFEST_SHA256.txt'))
manifest=''.join(f'{hashlib.sha256(f.read_bytes()).hexdigest()}  {f.relative_to(root)}\n' for f in files)
(root/'MANIFEST_SHA256.txt').write_text(manifest)
files.append(root/'MANIFEST_SHA256.txt')
with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for file in files:z.write(file,arcname=f'MicroMusic_PIC16F1503_ASM/{file.relative_to(root)}')
with zipfile.ZipFile(out) as z:
 assert z.testzip() is None
 assert len(z.namelist())==len(files)
print(f'{out}: {out.stat().st_size:,} bytes, {len(files)} files')

"""Refresh the CRC collection's byte-level integrity manifest after reviewed edits."""
from pathlib import Path
import hashlib

root = Path(__file__).resolve().parent.parent
paths = sorted(p for p in root.rglob('*') if p.is_file()
               and '__pycache__' not in p.parts and p.suffix != '.pyc'
               and p != root / 'SHA256SUMS.txt')
for path in paths:
    assert path.suffix.lower() not in ('.mid', '.midi', '.smf')
lines = [hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.relative_to(root).as_posix() for p in paths]
(root / 'SHA256SUMS.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
print(f'Updated integrity manifest: {len(paths)} files')

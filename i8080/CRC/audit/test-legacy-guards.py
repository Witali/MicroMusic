"""Legacy subset emulators must reject DAA instead of using an incorrect shortcut."""
from pathlib import Path
import importlib.util
import json
import sys

sys.dont_write_bytecode = True

root = Path(__file__).resolve().parent.parent
rows = json.loads((root / 'SOURCES.json').read_text(encoding='utf-8'))['files']
tested = 0
for row in rows:
    if 'reject DAA' not in row.get('local_changes', ''):
        continue
    path = root / row['path']
    spec = importlib.util.spec_from_file_location('legacy_' + str(tested), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rom = bytearray(65536)
    # XRA A; SBB A; DAA; HLT. Real 8080 has AC=1 after SBB A, giving A=06.
    rom[:4] = bytes([0xAF, 0x9F, 0x27, 0x76])
    try:
        module.emulate(rom)
    except NotImplementedError as error:
        assert 'AC' in str(error)
    else:
        raise AssertionError(f'{path}: inaccurate DAA silently accepted')
    tested += 1
assert tested > 0
print(f'PASS: {tested} legacy CPU subsets explicitly reject unsupported DAA')

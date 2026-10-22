#!/usr/bin/env python3
"""Best-effort parser for Microchip MDB Print output. Requires real MDB log.
If log output format differs, compare register snapshots in reference_our_emulator.json manually.
"""
import json,re
from pathlib import Path
root=Path(__file__).resolve().parent
logpath=root/'mdb_official_output.log'
if not logpath.exists():raise SystemExit('No official MDB log. Run prepare_mdb.py --mdb /path/to/mdb.sh first.')
text=logpath.read_text(errors='replace')
checks=json.loads((root/'reference_our_emulator.json').read_text())['checkpoints']
chunks=re.split(r'CHECKPOINT_(\d+)',text,flags=re.IGNORECASE)
by_point={int(chunks[i]):chunks[i+1] for i in range(1,len(chunks)-1,2)}
errors=[];ok=0;unknown=0
for snap in checks:
    n=snap['instructionCount'];body=by_point.get(n,'')
    if not body:errors.append(f'Checkpoint {n} missing in MDB output');continue
    for name,want in snap['registers'].items():
        # Accept e.g. "STATUS = 0x1c", "STATUS = 28", or "STATUS=1Ch".
        match=re.search(r'\b'+name+r'\s*(?:=|:)\s*((?:0x)?[0-9a-fA-F]+h?)\b',body,re.I)
        if not match:unknown+=1;continue
        s=match.group(1)
        try:
            got=int(s[:-1],16) if s.lower().endswith('h') else int(s,16 if s.lower().startswith('0x') else 10)
        except ValueError:unknown+=1;continue
        if got!=want:errors.append(f'Checkpoint {n} {name}: MPLAB={got:#x}, our emulator={want:#x}')
        else:ok+=1
print('Compared registers:',ok,'; unparsed:',unknown,'; mismatches:',len(errors))
for msg in errors[:120]:print('DIFF:',msg)
if unknown:print('MPLAB output format is not entirely parsed. Inspect official log manually.')
if not ok:print('No values compared: this does not constitute a successful cross-check.')
if errors:raise SystemExit(1)

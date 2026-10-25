#!/usr/bin/env python3
from pathlib import Path
import argparse
p=argparse.ArgumentParser();p.add_argument('input');p.add_argument('output');args=p.parse_args()
a=Path(args.input).read_bytes()
if not a.startswith(b'L3AV'):raise SystemExit('expected L3AV')
s='#pragma once\n#include <avr/pgmspace.h>\n/* Auto-generated AVR flash payload. */\nconst uint8_t g_voice_l3av[] PROGMEM={\n'
for i in range(0,len(a),16):s+='  '+', '.join('0x%02X'%x for x in a[i:i+16])+',\n'
s+='};\n'
Path(args.output).write_text(s)
print('generated',args.output,len(a),'bytes')

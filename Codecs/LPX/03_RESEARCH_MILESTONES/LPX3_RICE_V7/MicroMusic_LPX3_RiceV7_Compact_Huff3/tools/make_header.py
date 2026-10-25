#!/usr/bin/env python3
"""Create an AVR PROGMEM L3AV voice array; uses *binary* file as supplied."""
import sys
from pathlib import Path
if len(sys.argv)!=3:raise SystemExit('usage: make_header.py audio.v7.l3av voice_data.h')
data=Path(sys.argv[1]).read_bytes()
if len(data)<20 or data[:4]!=b'L3AV' or data[4]!=7:
    raise SystemExit('Expected verified L3AV v7 input')
if len(data)>30000:raise SystemExit('Stream too large for ATmega328P Flash; leave room for code')
lines=[ '#pragma once', '#include <avr/pgmspace.h>', '',
        f'const uint8_t g_voice_l3av[] PROGMEM = {{']
for i in range(0,len(data),16):
    lines.append('  '+', '.join(f'0x{b:02X}' for b in data[i:i+16])+',')
lines.append('};')
lines.append(f'const uint16_t g_voice_l3av_size={len(data)};')
Path(sys.argv[2]).write_text('\n'.join(lines)+'\n')

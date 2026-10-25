#!/usr/bin/env python3
"""Convert any finalized L4HY v2 stream into Arduino PROGMEM voice_data.h."""
import argparse
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('input',type=Path);p.add_argument('output',type=Path)
a=p.parse_args();raw=a.input.read_bytes()
if len(raw)<20 or raw[:5]!=b'L4HY\x02':raise SystemExit('Requires L4HY version 2')
if len(raw)>65535:raise SystemExit('16-bit PROGMEM stream length exceeded')
lines=['#pragma once','#include <stdint.h>','#include <avr/pgmspace.h>',
       'const uint8_t g_voice_l4hy[] PROGMEM = {']
for i in range(0,len(raw),16):lines.append('  '+', '.join(str(c) for c in raw[i:i+16])+',')
lines.extend(['};','const uint16_t g_voice_l4hy_size = sizeof(g_voice_l4hy);',''])
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text('\n'.join(lines))
print(a.output,'bytes',len(raw))

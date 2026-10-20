#!/usr/bin/env python3
"""Rebuild the precisely selected 56-byte measured wavetable ROM used by firmware.

Run after extract_instruments.py or by itself with tables.json in same folder.
The violin deliberately retains its previous tiny mathematical oscillator
(the harmonic comparison was already good and tables did not improve it).
"""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parent
DB=json.loads((ROOT/'tables.json').read_text())
files=[('piano',0,'sustain'),('piano',1,'sustain'),('piano',2,'sustain'),
       ('guitar',0,'sustain'),('guitar',1,'sustain'),('guitar',2,'sustain'),
       ('guitar',0,'attack')]
lines=['/* Generated from measured SoundFont sample spectra by build_tables_for_firmware.py.',
       ' * q4_signed = nibble-8; 16 phase samples = 8 bytes per wave; zero DC.',
       ' * Offsets: piano [0,8,16], guitar [24,32,40], low guitar attack [48].',
       ' * Reference MIDI pitches: piano C3/D4/A5; guitar G2/D4/A4.',
       ' * The violin remains the original mathematical oscillator.',
       ' */', '.section .text','instrument_waves:']
for ins,reg,stage in files:
    data=DB['waves'][f'{ins}.{reg}.{stage}']
    assert sum(data['q4signed'])==0,(ins,reg,stage)
    b=data['bytes']
    assert len(b)==8
    lines+=['/* %s %s %s */'%(ins,('low','mid','high')[reg],stage),
            ' .byte '+', '.join(f'0x{x:02x}' for x in b)]
tgt=ROOT/'firmware'/'waveforms.inc'
tgt.parent.mkdir(exist_ok=True)
tgt.write_text('\n'.join(lines)+'\n')
print('Generated:',tgt,'wavetable bytes:',len(files)*8)

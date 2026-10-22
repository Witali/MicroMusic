"""Generate adaptive slew AVR assembly from independently verified Keyframe LPC8 v1."""
from pathlib import Path
ROOT=Path(__file__).resolve().parent
original=(ROOT/'keyframe_reference.S').read_text()
assert original.count(' andi r16,3\n')==1
assert original.count(' mov r27,r4\n')==1
s=original.replace(' andi r16,3\n', ' and r16,r6\n',1)
s=s.replace(' mov r27,r4\n', ''' mov r27,r4
 /* Pitch header bit6: slow 8-sample spectral/gain slew by default,
  * fast 4-sample slew for significant phonetic transitions.
  * Bit7 continues to mean short event (no spectral coefficient update).
  * r6 is free from all 8-stage lattice and interrupt routines.
  */
 ldi r16,7
 sbrc r27,6
 ldi r16,3
 mov r6,r16
''',1)
s=s.replace(' * 5 bytes per 256-sample speech frame; all voice data in Flash.',
''' * Adaptive keyframe stream: fast/slow transition bit in pitch header,
 * spectral keyframes, short events, and RLE silence; Flash-resident data.''')
s=s.replace('.set VOICE_ADDR,0x0342','.set VOICE_ADDR,0x034a')
s=s.replace(' /* Linear-in-quantized-domain ramp: all eight lattice reflection',
            ' /* Per-frame adaptive quantized-domain slew: all eight lattice reflection')
(ROOT/'tinylpc.S').write_text(s)
print('adaptive firmware source',len(s),'chars')

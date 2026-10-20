#!/usr/bin/env python3
"""Recover editable GNU AVR syntax from the exact production image.
This decoder is intentionally restricted to opcodes present in synth.bin.
"""
from pathlib import Path
B=Path(__file__).resolve().parent
binary=(B/'synth.bin').read_bytes()
assert len(binary)==1024
code_end=0x2C0

names={
0x0000:'vectors',0x0014:'reset',0x002c:'clear_registers',0x0058:'idle',
0x005a:'audio_irq',0x006a:'music_tick',0x00c0:'read_event',
0x00d0:'note_off',0x00e2:'release_lead',0x00ea:'chord_event',
0x0110:'melodic_event',0x0146:'note_rest',0x014a:'next_section',
0x0170:'hold_sample',0x0174:'update_envelope',0x019c:'eeprom_wave',
0x01ac:'scale_wave',0x01ce:'render_sample',0x0202:'render_tone',
0x0266:'voice_silent',0x026c:'render_drum',0x02b8:'write_pwm',
0x02c0:'playlist',0x02cf:'durations',0x02d6:'note_steps',
0x02f0:'chord_steps',0x0304:'section_offsets',0x030a:'music_sections',
}

notes={
0x0014:'Initialize the stack and switch the internal RC from the factory /8 divider to 9.6 MHz.',
0x002c:'Clear oscillator and envelope registers without allocating SRAM. The ISR owns the register file.',
0x0032:'Initialize four sound channels, score cursor, and deterministic percussion noise.',
0x0044:'Configure hardware Fast PWM on OC0B/PB1, fixed TOP=255 at 37.5 kHz.',
0x005a:'Timer0 overflow. Even samples run the four-voice mixer; score events are decoded every 512 overflows.',
0x006a:'Advance envelopes at ~73.24 Hz. Flags in envelope bytes encode attack, sustain and release.',
0x008e:'Piano and guitar use one shared envelope function with different decay masks.',
0x009e:'Percussion decays on alternate ticks, retriggering in a four-beat rhythm.',
0x00c0:'Read packed score tokens. F0..FF are control events; E0..EF update accompaniment harmony.',
0x00d0:'NOTE-OFF bitmask: bit0 violin, bit1 piano, bit2 guitar, bit3 percussion. No oscillator resets.',
0x00e2:'Change lead from attack/sustain into release without resetting DDS phase.',
0x00ea:'Decode chord index; load two independent DDS frequencies and restart their envelopes.',
0x0110:'Decode compact note/duration; load 16-bit DDS increment or signal lead release.',
0x014a:'Follow the 15-entry playlist; repeated musical phrases point to one copy in Flash.',
0x0174:'Approximate piecewise linear envelopes via small integer increments, including note-off.',
0x019c:'Get a packed pair of 4-bit wave samples from EEPROM, with the documented read wait.',
0x01ac:'Scale signed sample by a four-bit envelope using shift-add, with no MUL instruction.',
0x01ce:'Accumulate three pitch oscillators with independent phases and envelopes.',
0x0202:'Choose register-dependent 16-step wavetable and blend attack to sustain over ~55 ms.',
0x026c:'Add bass drum or band-limited pseudo-random percussion; center the mix on PWM duty 128.',
0x02b8:'Apply the single +128 offset only after bipolar mixing, write OCR0B, restore timebase.',
0x02c0:'Compact playlist (15 indexes), duration codes, DDS steps, chord steps and unique note sections.',
}

def signed(v,n):return v-(1<<n) if v&(1<<(n-1)) else v

def dec(w,a):
    targets=[]
    if w==0:return 'nop',targets
    if w==0x94f8:return 'cli',targets
    if w==0x9478:return 'sei',targets
    if w==0x9518:return 'reti',targets
    if w==0x9508:return 'ret',targets
    if (w&0xf000) in (0xc000,0xd000):
        dest=a+2+2*signed(w&0xfff,12)
        targets=[dest]
        return ('rjmp' if (w&0xf000)==0xc000 else 'rcall')+f' .L{dest:03x}',targets
    if (w&0xfc00) in (0xf000,0xf400):
        bit=w&7; pos=(w&0xfc00)==0xf000
        if bit not in (0,1):raise ValueError((hex(a),hex(w)))
        op=({(1,True):'breq',(1,False):'brne',(0,True):'brcs',(0,False):'brcc'})[(bit,pos)]
        dest=a+2+2*signed((w>>3)&127,7)
        return f'{op} .L{dest:03x}',[dest]
    if (w&0xfe08) in (0xfc00,0xfe00):
        op='sbrc' if w&0xfe08==0xfc00 else 'sbrs'
        return f'{op} r{(w>>4)&31}, {w&7}',targets
    if (w&0xf000)==0xe000:
        return f'ldi r{16+((w>>4)&15)}, {((w>>4)&0xf0)|(w&15)}',targets
    if (w&0xf000) in (0x3000,0x5000,0x6000,0x7000):
        op={0x3000:'cpi',0x5000:'subi',0x6000:'ori',0x7000:'andi'}[w&0xf000]
        return f'{op} r{16+((w>>4)&15)}, {((w>>4)&0xf0)|(w&15)}',targets
    if (w&0xff00)==0x0100:
        return f'movw r{2*((w>>4)&15)}, r{2*(w&15)}',targets
    if (w&0xfc00) in (0x0c00,0x1c00,0x1800,0x2000,0x2400,0x2c00):
        d=(w>>4)&31;r=(w&15)|((w>>5)&16)
        op={0x0c00:'add',0x1c00:'adc',0x1800:'sub',0x2000:'and',0x2400:'eor',0x2c00:'mov'}[w&0xfc00]
        if op=='add' and d==r:return f'lsl r{d}',targets
        if op=='eor' and d==r:return f'clr r{d}',targets
        if op=='and' and d==r:return f'tst r{d}',targets
        return f'{op} r{d}, r{r}',targets
    if (w&0xfe0f) in (0x9403,0x940a,0x9400,0x9406,0x9405,0x9402):
        op={0x9403:'inc',0x940a:'dec',0x9400:'com',0x9406:'lsr',0x9405:'asr',0x9402:'swap'}[w&0xfe0f]
        return f'{op} r{(w>>4)&31}',targets
    if (w&0xf800) in (0xb000,0xb800):
        d=(w>>4)&31;io=((w>>5)&48)|(w&15)
        return (f'in r{d}, {io}' if (w&0xf800)==0xb000 else f'out {io}, r{d}'),targets
    if (w&0xff00)==0x9a00:
        return f'sbi {(w>>3)&31}, {w&7}',targets
    if (w&0xfe0f)==0x9201:
        return f'st Z+, r{(w>>4)&31}',targets
    if (w&0xfe0f) in (0x9004,0x9005):
        return f'lpm r{(w>>4)&31}, '+('Z+' if w&1 else 'Z'),targets
    raise ValueError(f'unknown {a:04x} {w:04x}')

instructions=[];tg=set()
for a in range(0,code_end,2):
 w=binary[a]|binary[a+1]<<8
 op,targets=dec(w,a)
 if any(x<0 or x>=code_end for x in targets):raise ValueError((hex(a),op,targets))
 instructions.append((a,op))
 tg.update(targets)

def label(a):
 if a in names: return names[a]
 return f'.L{a:03x}'

hdr='''/* ATtiny13A: 4-voice spectral DDS player, smoothed envelopes and per-voice note-off.
 * REPRODUCIBLE SOURCE: reconstructed as GNU AVR mnemonics from the 1KB
 * ATtiny13A release binary; running build.py reassembles and byte-compares it.
 * All addresses, and every opcode, are retained. A general purpose source
 * patcher can modify notes and wavetables using score/EEPROM utilities.
 *
 * Clock: 9.6MHz internal RC, CKDIV8 OFF (low fuse 0x7A).
 * PWM: OC0B/PB1, Timer0 Fast PWM 8 bit /1 = 37500Hz;
 * DDS outputs: 18750 samples/s (one new duty each two periods).
 * EEPROM: 64 bytes, packed 4-bit spectra selected by pitch and attack age.
 *
 * The interrupt owns the full register file and uses the hardware PC stack;
 * the foreground does not modify registers while interrupts are enabled.
 * This player intentionally depends on these register allocations.
 *
 * NOTES ABOUT THE RECOVERED SOURCE:
 * Instructions are genuine GNU AVR mnemonics (not opaque .word directives).
 * Numeric byte-address constants identify Flash data tables and can be
 * kept stable by the assembler; add or remove instructions only after
 * reviewing the absolute pointers and checking memory/timing.
 * Avoid blanket per-instruction commentary: headings describe algorithms.
 */
.section .text,"ax",@progbits
.global vectors
'''
lines=[hdr]
for a,op in instructions:
 if a in names or a in tg:
  lines.append(f'{label(a)}:')
 if a in notes:lines.append(f'  /* {notes[a]} */')
 # Use semantic symbol names in all rjmp/rcall/branch targets.
 import re
 op=re.sub(r'\.L([0-9a-f]{3})',lambda m:label(int(m.group(1),16)),op)
 lines.append(f'  {op:<28} /* {a:03x} */' if a%16==0 else f'  {op}')
lines.append('  /* The following bytes are data, never executed as AVR instructions. */')
for a in range(code_end,1024,16):
 for k,v in names.items():
  if a<=k<min(a+16,1024) and k!=a:
   pass
 pp=a
 while pp<min(a+16,1024):
  if pp in names:lines.append(names[pp]+':')
  nxt=min(a+16,1024)
  nxt=min([q for q in names if pp<q<nxt]+[nxt])
  vals=binary[pp:nxt]
  lines.append('  .byte '+', '.join('0x%02x'%x for x in vals))
  pp=nxt
(B/'synth.S').write_text('\n'.join(lines)+'\n')
print('decoded',len(instructions),'instructions,',len(tg),'flow targets, labels',len(names))

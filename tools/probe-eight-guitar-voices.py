"""Build an eight-oscillator AVR timing probe with two shared chord envelopes.

This is a static synthesis feasibility probe, not the MNC1 song decoder.
Every oscillator has its own 16-bit phase and DDS step. The two source
guitars can share a gain per chord because their on/off times are common.
"""
from pathlib import Path
import importlib.util
import json

ROOT = Path(__file__).resolve().parents[1]


def build():
    spec = importlib.util.spec_from_file_location('eight_assembler',ROOT/'tools/build-release-engine.py')
    assembler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(assembler)
    folder = ROOT/'build/eight-guitar-voices'
    folder.mkdir(parents=True,exist_ok=True)
    # A two-note melodic chord plus all six notes of the source rhythm guitar.
    pitches = [71,67,64,59,55,52,47,40]
    steps = [round(440*2**((p-69)/12)*65536/18750) for p in pitches]
    source = '''.section .text,"ax",@progbits
.global vectors
vectors:
  rjmp reset
  nop
  nop
  rjmp pwm_irq
reset:
  clr r27
  clr r29
  clr r31
  ldi r30, 96
  ldi r16, 128
fill_ring:
  st Z+, r16
  cpi r30, 112
  brne fill_ring
  ldi r26, 112
  ldi r30, lo8(note_steps)
  ldi r31, hi8(note_steps)
initialize:
  st X+, r29
  st X+, r29
  lpm r16, Z+
  st X+, r16
  lpm r16, Z+
  st X+, r16
  cpi r26, 144
  brne initialize
  ldi r16, 15
  mov r4, r16
  mov r5, r16
  ldi r18, 128
  mov r23, r18
  ldi r28, 96
  ldi r22, 110
  sbi 23, 1
  out 41, r18
  ldi r16, 35
  out 47, r16
  ldi r16, 1
  out 51, r16
  ldi r16, 2
  out 57, r16
  sei
idle:
  mov r16, r22
  sub r16, r28
  andi r16, 15
  cpi r16, 13
  brcc idle
render_sample:
  ldi r26, 112
  clr r21
voice_loop:
  ld r16, X+
  ld r17, X+
  ld r6, X+
  ld r7, X+
  add r16, r6
  adc r17, r7
  subi r26, 4
  st X+, r16
  st X+, r17
  subi r26, 254
  ldi r16, 0
  mov r25, r7
  cpi r25, 4
  brcs wave_register
  ori r16, 8
wave_register:
  swap r17
  andi r17, 15
  lsr r17
  or r16, r17
  out 30, r16
  sbi 28, 0
  in r17, 29
  brcc wave_nibble
  swap r17
wave_nibble:
  andi r17, 15
  subi r17, 8
  add r21, r17
  cpi r26, 120
  brne rhythm_group
  mov r25, r4
  rcall chord_gain
  mov r20, r17
  clr r21
rhythm_group:
  cpi r26, 144
  brne voice_loop
  mov r25, r5
  rcall chord_gain
  add r17, r20
write_pwm:
  subi r17, 128
  mov r16, r23
  add r16, r17
  ror r16
  mov r26, r22
  st X+, r16
  st X+, r17
  mov r22, r26
  andi r22, 111
  mov r23, r17
ring_published:
  rjmp idle
pwm_irq:
  out 41, r18
ring_read:
  ld r18, Y+
  sbrc r28, 4
  ldi r28, 96
  reti
chord_gain:
  /* Exact signed 16-bit sum*level, then /8; no hardware multiplier. */
  mov r16, r21
  clr r0
  sbrc r16, 7
  com r0
  clr r17
  clr r7
'''
    for bit in range(3,-1,-1):
        if bit!=3:
            source += '  lsl r17\n  adc r7, r7\n'
        source += f'  sbrs r25, {bit}\n  rjmp gain_bit_{bit}\n  add r17, r16\n  adc r7, r0\ngain_bit_{bit}:\n'
    source += '  asr r7\n  ror r17\n'*3+'gain_return:\n  ret\nnote_steps:\n.byte '
    source += ','.join(str(b) for step in steps for b in (step&255,step>>8))+'\n'
    (folder/'synth.S').write_text(source,encoding='utf-8',newline='\n')
    rom,labels = assembler.assemble_relaxed(folder/'synth.S')
    (folder/'synth.bin').write_bytes(rom)
    bank = json.loads((ROOT/'ATtiny13A/Music/instruments/bank.json').read_text(encoding='utf-8'))
    profile = bank['instruments']['acoustic-guitar-nylon']
    ep = bytearray(64)
    for index,register in enumerate(('low','high')):
        wave = profile['waves'][register]
        ep[index*8:index*8+8] = bytes((wave[n]+8)|((wave[n+1]+8)<<4) for n in range(0,16,2))
    (folder/'eeprom.bin').write_bytes(ep)
    report = dict(experimental=True,scope='Static eight-voice synthesis only; no score decoder or complete-song fit claim.',
                  cpuHz=9600000,pwmHz=37500,synthesisHz=18750,flashBytes=len(rom),
                  codeBytes=labels['note_steps'],eepromBytes=64,labels=labels,pitches=pitches,steps=steps,
                  voiceAddresses=list(range(112,144,4)),phaseStateBytes=32,pwmRingBytes=16,
                  sharedChordGainRegisters=[4,5],gainDivisor=8)
    (folder/'build-report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({k:report[k] for k in ('flashBytes','codeBytes','synthesisHz','phaseStateBytes')}))


if __name__=='__main__':
    build()

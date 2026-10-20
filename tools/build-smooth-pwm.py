"""Interpolate precomputed sample pairs in a flag-preserving short PWM ISR."""
from pathlib import Path
import importlib.util
import hashlib
import json
import shutil

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'ATtiny13A/Music/variants/natural-hat'
OUT=ROOT/'ATtiny13A/Music/variants/smooth-pwm'
spec=importlib.util.spec_from_file_location('assembler',ROOT/'tools/assemble-avr.py')
assembler=importlib.util.module_from_spec(spec);spec.loader.exec_module(assembler)


def ihex(raw):
    rows=[]
    for i in range(0,len(raw),16):
        b=bytes([len(raw[i:i+16]),i>>8,i&255,0])+raw[i:i+16]
        rows.append(':'+(b+bytes([-sum(b)&255])).hex().upper())
    return '\n'.join(rows+[':00000001FF',''])


def source():
    text=(BASE/'synth.S').read_text(encoding='utf-8')
    changes=[
        ('  out 41, r18\n  ldi r16, 35', '  out 41, r18\n  ldi r23, 1\n  ldi r16, 35'),
        ('  brne clear_registers\n', '  brne clear_registers\n  ldi r18, 128\n  ldi r30, 97\n  st Z+, r18\n  st Z+, r18\n  st Z+, r0\n'),
        ('  sbi 23, 1\n  ldi r18, 128\n', '  sbi 23, 1\n'),
        ('  out 41, r18\n  set\n  reti', '''  out 41, r18
  sbrc r23, 0
  lds r18, 97
  sbrs r23, 0
  lds r18, 98
  swap r23
  set
  reti'''),
        ('  com r23\n  breq music_tick\n  rjmp render_sample', '  lds r16, 99\n  com r16\n  sts 99, r16\n  breq music_tick\n  rjmp hold_sample'),
        ('  sbrc r15, 0\n  rjmp hold_sample', '  sbrs r15, 0\n  rjmp hold_sample'),
        ('  mov r0, r17\n  sbrc r17, 4', '  sbrc r17, 4'),
        ('  mov r18, r26\n  pop r25\n  ret', '''  lds r16, 98
  add r16, r26
  ror r16
publish_wait:
  /* The midpoint IRQ must first copy the old next point into R18. */
  sbrs r23, 0
  rjmp publish_wait
  sts 97, r16
  sts 98, r26
  pop r25
  ret'''),
    ]
    for before,after in changes:
        assert text.count(before)==1,(before,text.count(before));text=text.replace(before,after)
    start=text.index('  mov r27, r17\n',text.index('render_tone:'))
    end=text.index('  mov r16, r25\n  andi r16, 15\n  rjmp scale_wave',start)
    text=text[:start]+'.L25c:\n'+text[end:]
    # Each helper now has one caller site; inline once, saving calls for all voices.
    start=text.index('eeprom_wave:');end=text.index('scale_wave:',start)
    eeprom=text[start:end];eeprom=eeprom[eeprom.index('  swap r17'):eeprom.rindex('  ret')]
    text=text[:start]+text[end:];text=text.replace('  rcall eeprom_wave\n',eeprom,1)
    start=text.index('scale_wave:');end=text.index('render_tone:',start)
    scale=text[start:end];scale=scale[scale.index('  mov r0, r17'):scale.rindex('  rjmp envelope_return')]
    text=text[:start]+text[end:];text=text.replace('  rjmp scale_wave\n',scale+'  clr r0\n  ret\n',1)
    text=text.replace('  sbrc r17, 4\n  ori r25, 64\n','  mov r0, r17\n',1).replace('  sbrc r25, 6\n  swap r17','  sbrc r0, 4\n  swap r17',1)
    # Keep gain in R25 and use R0 for instrument tags before reusing it for phase.
    text=text.replace('  mov r25, r0\n','',1).replace('  sbrc r25, 4\n','  sbrc r0, 4\n',1).replace('  sbrc r25, 5\n','  sbrc r0, 5\n',1)
    text=text.replace('  mov r16, r25\n  andi r16, 15\n','  mov r16, r25\n',1)
    text=text.replace('  cpi r16, 4\n  brcs .L214\n  ldi r16, 8\n  rjmp .L216\n.L214:\n  clr r16\n.L216:',
                      '  cpi r16, 4\n  ldi r16, 0\n  brcs .L216\n  ldi r16, 8\n.L216:',1)
    text=text.replace('Even samples run the four-voice mixer;', 'Odd ticks produce new four-voice points;')
    text=text.replace('The foreground owns the register file.', 'R18/R23 are subsequently reserved for the ISR.')
    text=text.replace('Apply the single +128 offset only after bipolar mixing, commit R18, restore timebase. ISR writes OCR0B separately.',
                      'Convert the bipolar mix to unsigned PWM; publish the next pair after a safe handoff.')
    # Fit the whole envelope helper around the unused vectors; all returns are near.
    start=text.index('update_envelope:');end=text.index('render_tone:',start)
    text=text[:start]+text[end:]
    start=text.index('vectors:');end=text.index('reset:',start)
    text=text[:start]+'''vectors:
  rjmp reset
envelope_return:
  clr r0
  ret
  rjmp pwm_irq
update_envelope:
  mov r0, r17
  mov r17, r16
  andi r17, 15
  breq envelope_return
  sbrs r16, 7
  rjmp envelope_release
  cpi r17, 10
  brcc envelope_gate
  lsl r0
  inc r0
  cpi r17, 7
  brcc envelope_gate
  lsl r0
  inc r0
envelope_gate:
  mov r17, r24
  and r17, r0
  brne envelope_return
  dec r16
  rjmp envelope_return
envelope_release:
  dec r16
  breq envelope_return
  sbrc r0, 1
  dec r16
  rjmp envelope_return
'''+text[end:]
    text='''/* Smoothed PWM: two future points and their midpoint are prepared in foreground.
 * SRAM[0x60]=noise high, [0x61]=midpoint, [0x62]=next point, [0x63]=music divider.
 * R18 belongs to ISR; R23 swaps 0x01/0x10 without changing arithmetic flags.
 * Sound generation 18.75 kHz; distinct interpolated output values 37.5 kHz.
 * Piano/guitar use soft sustain spectra with their measured envelopes.
 * Per-sample attack/sustain spectral crossfade omitted to fit 1 KB Flash.
 */
'''+text[text.index('.section .text'):]
    return text


def main():
    assembler.verify_originals(ROOT);OUT.mkdir(parents=True,exist_ok=True)
    for name in ['config.inc','score.inc','score.json','waveforms.json','eeprom.bin','eeprom.hex','FluidR3-MIT.txt']:
        shutil.copyfile(BASE/name,OUT/name)
    (OUT/'synth.S').write_text(source(),encoding='utf-8',newline='\n')
    rom,labels=assembler.assemble(OUT/'synth.S');assert len(rom)<=1024,len(rom)
    (OUT/'synth.bin').write_bytes(rom);(OUT/'synth.hex').write_text(ihex(rom),encoding='utf-8',newline='\n')
    core=(BASE/'avr_core.js').read_text(encoding='utf-8')
    core=core.replace('[0x9403,0x940a,0x9400,0x9406,0x9405,0x9402]','[0x9403,0x940a,0x9400,0x9406,0x9405,0x9407,0x9402]')
    core=core.replace('else if(op===0x9405)', 'else if(op===0x9407){rr[d]=(x>>1)|(this.c<<7);this.z=Number(rr[d]===0);this.c=x&1}\n      else if(op===0x9405)')
    core=core.replace("if(z>=32)throw new Error('Register file write out of range');\n      rr[z]=rr[r];", "if(z>=96&&z<160)this.ram[z-96]=rr[r];else if(z<32)rr[z]=rr[r];else throw new Error('Data write out of range');")
    assert 'op===0x9407' in core and 'this.ram[z-96]=rr[r]' in core
    (OUT/'avr_core.js').write_text(core.rstrip()+'\n',encoding='utf-8',newline='\n')
    template=(ROOT/'ATtiny13A/Music/final/attiny13a_synth_release/player_template.html').read_text(encoding='utf-8')
    html=template.replace('/*AVR_CORE*/',core).replace('/*FIRMWARE_HEX*/',ihex(rom)).replace('/*EEPROM_HEX*/',(OUT/'eeprom.hex').read_text(encoding='utf-8'))
    html=html.replace('ATtiny13A — проигрыватель AVR-прошивки','ATtiny13A — плавный PWM')
    html=html.replace('hp.frequency.value=35;','hp.frequency.value=35;hp.Q.value=20*Math.log10(.5);').replace('lp.frequency.value=9000;','lp.frequency.value=4000;lp.Q.value=20*Math.log10(.5);')
    (OUT/'player.html').write_text(html,encoding='utf-8',newline='\n')
    report=dict(parent='natural-hat',flashBytes=len(rom),codeBytes=labels['playlist'],tableBytes=len(rom)-labels['playlist'],eepromBytes=64,labels=labels,
                flashSha256=hashlib.sha256(rom).hexdigest(),eepromSha256=hashlib.sha256((OUT/'eeprom.bin').read_bytes()).hexdigest(),
                outputHz=37500,synthesisHz=18750,output='A, floor((A+B)/2), B',sramBytes=4,readyPoints=2,
                change='Piano/guitar sustain tables with original volume envelopes; attack spectral crossfade removed')
    (OUT/'build-report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print('Smooth PWM:',len(rom),'Flash; 64 EEPROM; four SRAM bytes')


if __name__=='__main__':main()

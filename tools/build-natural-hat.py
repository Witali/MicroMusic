"""Build a long-period percussion variant of the foreground synth."""
from pathlib import Path
import importlib.util
import hashlib
import json
import shutil

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'ATtiny13A/Music/variants/foreground-pwm'
OUT=ROOT/'ATtiny13A/Music/variants/natural-hat'
spec=importlib.util.spec_from_file_location('assembler',ROOT/'tools/assemble-avr.py')
assembler=importlib.util.module_from_spec(spec);spec.loader.exec_module(assembler)


def ihex(raw):
    rows=[]
    for i in range(0,len(raw),16):
        b=bytes([len(raw[i:i+16]),i>>8,i&255,0])+raw[i:i+16]
        rows.append(':'+(b+bytes([-sum(b)&255])).hex().upper())
    return '\n'.join(rows+[':00000001FF',''])


def source(tap=45):
    text=(BASE/'synth.S').read_text(encoding='utf-8')
    changes=[
        ('  clr r1\n','  clr r1\n  sts 96, r0\n'),
        ('  mov r17, r29\n  andi r17, 3\n  breq .L280\n  cpi r17, 2\n  breq .L298\n  rjmp .L298',
         '  tst r29\n  breq .L280\n  rjmp .L298'),
        ('  sbrc r15, 0\n  rjmp .L28a\n',''),
        ('  lsl r14\n  brcc .L2a0\n  ldi r17, 169\n  eor r14, r17\n.L2a0:',
         f'  lds r27, 96\n  lsl r14\n  adc r27, r27\n  brcc .L2a0\n  ldi r17, {tap}\n  eor r14, r17\n.L2a0:\n  sts 96, r27'),
        ('  rcall scale_wave\n  ret\nvoice_silent:', '  rjmp scale_wave\nvoice_silent:'),
        ('  mov r25, r0\n  clr r0\n', '  mov r25, r0\n'),
        ('  clr r0\n  ret\nrender_sample:', '  rjmp envelope_return\nrender_sample:'),
        ('note_rest:\n  rcall release_lead\n  rjmp hold_sample', 'note_rest:\n  rjmp release_lead'),
        ('  cli\n', ''),
        ('  mov r17, r14\n  lsr r17\n  sbrc r29, 0\n  eor r17, r14\n  andi r17, 63\n  subi r17, 32\n  asr r17',
         '  mov r17, r14\n  lsr r17\n  andi r17, 63\n  mov r27, r14\n  andi r27, 63\n  sbrc r29, 0\n  sub r17, r27\n  sbrs r29, 0\n  subi r17, 32\n  asr r17\n  sbrc r29, 0\n  asr r17'),
        ('The ISR owns the register file.', 'The foreground owns the register file.'),
        ('Source: soft FluidR3 instruments, unchanged EEPROM and score.',
         'Source: foreground FluidR3 instruments; 16-bit noise, one SRAM byte at 0x60.\n * Low noise byte is R14; high byte stays separate from the downward hardware stack.'),
    ]
    for before,after in changes:
        assert text.count(before)==1,(before,text.count(before));text=text.replace(before,after)
    # Place the helper before its caller so the mixer can fall through into drums.
    start=text.index('render_tone:');end=text.index('render_drum:')
    helper=text[start:end];text=text[:start]+text[end:]
    text=text.replace('render_sample:',helper+'render_sample:',1).replace('  rjmp render_drum\n','',1)
    return text


def reference_core():
    core=(BASE/'avr_core.js').read_text(encoding='utf-8')
    changes=[
        ('this.io = new Uint8Array(64);','this.io = new Uint8Array(64); this.ram = new Uint8Array(64);'),
        ("if([0x940c,0x940e,0x9000,0x9200].includes(next&0xfe0e))throw new Error('Skipped 2-word opcode');\n        this.pc++;n=2;",
         'let words=[0x940c,0x940e,0x9000,0x9200].includes(next&0xfe0e)?2:1;\n        this.pc+=words;n=1+words;'),
        ('    else if((w&0xf800)===0xb000)', '''    else if((w&0xfe0f)===0x9000 || (w&0xfe0f)===0x9200){
      let d=(w>>4)&31,a=this.rom[p+2]|this.rom[p+3]<<8;
      if(a<96||a>=160)throw new Error('SRAM address out of range');
      if((w&0xfe0f)===0x9000)rr[d]=this.ram[a-96];else this.ram[a-96]=rr[d];
      this.pc++;n=2;
    }
    else if((w&0xf800)===0xb000)'''),
    ]
    for before,after in changes:
        assert core.count(before)==1,(before,core.count(before));core=core.replace(before,after)
    return core.rstrip()+'\n'


def main():
    assembler.verify_originals(ROOT)
    OUT.mkdir(parents=True,exist_ok=True)
    for name in ['config.inc','score.inc','score.json','waveforms.json','eeprom.bin','eeprom.hex','FluidR3-MIT.txt']:
        shutil.copyfile(BASE/name,OUT/name)
    (OUT/'synth.S').write_text(source(),encoding='utf-8',newline='\n')
    rom,labels=assembler.assemble(OUT/'synth.S');assert len(rom)<=1024,len(rom)
    (OUT/'synth.bin').write_bytes(rom);(OUT/'synth.hex').write_text(ihex(rom),encoding='utf-8',newline='\n')
    core=reference_core();(OUT/'avr_core.js').write_text(core,encoding='utf-8',newline='\n')
    template=(ROOT/'ATtiny13A/Music/final/attiny13a_synth_release/player_template.html').read_text(encoding='utf-8')
    html=template.replace('/*AVR_CORE*/',core).replace('/*FIRMWARE_HEX*/',ihex(rom)).replace('/*EEPROM_HEX*/',(OUT/'eeprom.hex').read_text(encoding='utf-8'))
    html=html.replace('ATtiny13A — проигрыватель AVR-прошивки','ATtiny13A — длинный шум тарелок')
    html=html.replace('hp.frequency.value=35;','hp.frequency.value=35;hp.Q.value=20*Math.log10(.5);').replace('lp.frequency.value=9000;','lp.frequency.value=4000;lp.Q.value=20*Math.log10(.5);')
    (OUT/'player.html').write_text(html,encoding='utf-8',newline='\n')
    report=dict(parent='foreground-pwm',flashBytes=len(rom),eepromBytes=64,labels=labels,
                flashSha256=hashlib.sha256(rom).hexdigest(),eepromSha256=hashlib.sha256((OUT/'eeprom.bin').read_bytes()).hexdigest(),
                noise=dict(bits=16,polynomial=45,direction='left',periodSamples=65535,periodSeconds=65535/18750,sramAddress=96),
                expectedIsrCycles=12,unchangedScore=True,unchangedWaves=True)
    (OUT/'build-report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print('Natural hat:',len(rom),'Flash, 64 EEPROM; one SRAM byte; fixed 12-cycle ISR')


if __name__=='__main__': main()

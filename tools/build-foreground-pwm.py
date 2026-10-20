"""Move synthesis into the foreground; ISR only outputs committed PWM and sets T."""
from pathlib import Path
import hashlib
import importlib.util
import json
import shutil
ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'ATtiny13A/Music/variants/fluid-instruments'
OUT=ROOT/'ATtiny13A/Music/variants/foreground-pwm'
spec=importlib.util.spec_from_file_location('assembler',ROOT/'tools/assemble-avr.py')
assembler=importlib.util.module_from_spec(spec);spec.loader.exec_module(assembler)


def ihex(raw):
    rows=[]
    for i in range(0,len(raw),16):
        data=raw[i:i+16];b=bytes([len(data),i>>8,i&255,0])+data
        rows.append(':'+(b+bytes([-sum(b)&255])).hex().upper())
    return '\n'.join(rows+[':00000001FF',''])


def main():
    assembler.verify_originals(ROOT)
    OUT.mkdir(parents=True,exist_ok=True)
    for name in ['config.inc','score.inc','score.json','waveforms.json','eeprom.bin','eeprom.hex','FluidR3-MIT.txt']:
        shutil.copyfile(PARENT/name,OUT/name)
    source=(PARENT/'synth.S').read_text(encoding='utf-8')
    source=source.replace('audio_irq','audio_step').replace('  rjmp audio_step','  rjmp pwm_irq',1)
    source=source.replace('idle:\n  rjmp idle','''idle:
  brtc idle
  clt
  rcall audio_step
  rjmp idle
pwm_irq:
  /* No arithmetic or temporary-register writes: foreground C/Z flags survive. */
  out 41, r18
  set
  reti''')
    old='hold_sample:\n  out 41, r18\n  reti'
    assert source.count(old)==1;source=source.replace(old,'hold_sample:\n  ret')
    source=source.replace('  mov r26, r25\n  clr r18','  push r25\n  clr r26')
    assert source.count('  add r18, r17')==4;source=source.replace('  add r18, r17','  add r26, r17')
    old='  subi r18, 128\n  out 41, r18\n  mov r25, r26\n  reti'
    assert source.count(old)==1;source=source.replace(old,'  subi r26, 128\n  mov r18, r26\n  pop r25\n  ret')
    source=source.replace('  nop\n','')
    source='''/* Foreground synthesis: R26 accumulates a sample; MOV atomically commits R18.
 * Timer0 ISR only OUTs R18, SETs SREG.T as a pending-tick flag, and RETIs.
 * T is otherwise untouched by this instruction subset; C/Z survive the ISR.
 * PUSH/POP saves the music counter while R26 is used as the accumulator.
 * All addresses are reassembled from labels with tools/assemble-avr.py.
 * Clock 9.6 MHz; Fast PWM OC0B/PB1 37.5 kHz; synthesis 18.75 kHz.
 * Source: soft FluidR3 instruments, unchanged EEPROM and score.
 */
'''+source[source.index('.section .text'):]
    source=source.replace('Timer0 overflow. Even samples run the four-voice mixer;', 'Foreground tick. Even samples run the four-voice mixer;')
    source=source.replace('write OCR0B, restore timebase.', 'commit R18, restore timebase. ISR writes OCR0B separately.')
    (OUT/'synth.S').write_text(source,encoding='utf-8',newline='\n')
    rom,labels=assembler.assemble(OUT/'synth.S');assert len(rom)<=1024
    assert labels['vectors']==0
    # Hardware Timer0 overflow vector must remain at byte 6.
    w=int.from_bytes(rom[6:8],'little');assert w&0xf000==0xc000 and (3+1+((w&4095)-4096 if w&2048 else w&4095))*2==labels['pwm_irq']
    (OUT/'synth.bin').write_bytes(rom);(OUT/'synth.hex').write_text(ihex(rom),encoding='utf-8',newline='\n')
    original=ROOT/'ATtiny13A/Music/final/attiny13a_synth_release'
    core=(original/'avr_core.js').read_text(encoding='utf-8')
    core=core.replace('this.c=0; this.i=0;','this.c=0; this.i=0; this.t=0; this.workLost=0;')
    core=core.replace('if(w===0){}',"if(w===0){}\n    else if(w===0x9468){if(this.t&&this.inIRQ)this.workLost++;this.t=1;}\n    else if(w===0x94e8)this.t=0;")
    core=core.replace("if(f>1)throw new Error('Unsupported branch flag');","if(f>1&&f!==6)throw new Error('Unsupported branch flag');")
    core=core.replace('let bit=f===0?this.c:this.z;','let bit=f===0?this.c:f===6?this.t:this.z;')
    assert 'this.t=0' in core and 'f===6?this.t' in core
    core=core.rstrip()+'\n'
    (OUT/'avr_core.js').write_text(core,encoding='utf-8',newline='\n')
    html=(original/'player_template.html').read_text(encoding='utf-8').replace('/*AVR_CORE*/',core).replace('/*FIRMWARE_HEX*/',ihex(rom)).replace('/*EEPROM_HEX*/',(OUT/'eeprom.hex').read_text(encoding='utf-8'))
    html=html.replace('ATtiny13A — проигрыватель AVR-прошивки','ATtiny13A — синтез в основном цикле')
    html=html.replace('hp.frequency.value=35;','hp.frequency.value=35;hp.Q.value=20*Math.log10(.5);').replace('lp.frequency.value=9000;','lp.frequency.value=4000;lp.Q.value=20*Math.log10(.5);')
    (OUT/'player.html').write_text(html,encoding='utf-8',newline='\n')
    report=dict(flashBytes=len(rom),eepromBytes=64,flashSha256=hashlib.sha256(rom).hexdigest(),eepromSha256=hashlib.sha256((OUT/'eeprom.bin').read_bytes()).hexdigest(),
                parent='fluid-instruments',architecture='Foreground synthesis, atomic R26 -> R18 commit, SREG.T pending tick, fixed OUT/SET/RETI ISR',
                timerOverflowCycles=256,newSampleCycles=512,expectedIsrCycles=12,labels=labels)
    (OUT/'build-report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print('Foreground firmware:',len(rom),'Flash, 64 EEPROM; fixed 12-cycle ISR including entry/vector')


if __name__=='__main__':main()

#!/usr/bin/env python3
"""Build musical PIC16F1503 application HEX and configuration-word image.
Configuration based on Microchip DS40001607D section 4.2 (CONFIG1, CONFIG2).
"""
from pathlib import Path
import subprocess,sys,json,hashlib
r=Path(__file__).resolve().parents[1]
subprocess.run([sys.executable,str(r/'tools/generate_tables.py')],check=True)
subprocess.run([sys.executable,str(r/'tools/assemble_pic.py')],check=True)

def record(addr,typ,b):
    x=[len(b),(addr>>8)&255,addr&255,typ,*b]
    return ':'+''.join(f'{v&255:02X}' for v in x+[(-sum(x))&255])
# CONFIG1: FOSC=INTOSC(00), WDTE=OFF(00), PWRTE=ON(0), MCLRE=ON,
# CLKOUTEN=1, BOREN=11, CP=1. Others remain 1. CONFIG2 all1 (LVP ON).
CONFIG1=0x3FC4
CONFIG2=0x3FFF
assert (CONFIG1&3)==0 and (CONFIG1&0x18)==0 and (CONFIG1&0x20)==0
assert CONFIG2&0x2000
conf='\n'.join([record(0,4,[0,1]), record(0x000E,0,[CONFIG1&255,CONFIG1>>8,CONFIG2&255,CONFIG2>>8]), record(0,1,[])])+'\n'
(r/'firmware/micromusic_config.hex').write_text(conf)
rom=(r/'firmware/micromusic.hex').read_text().splitlines()
assert rom[-1]==record(0,1,[])
(r/'firmware/micromusic_with_config.hex').write_text('\n'.join(rom[:-1]+conf.splitlines())+'\n')
rep=json.loads((r/'reports/assembly.json').read_text())
rep['config1_hex']=f'0x{CONFIG1:04X}'
rep['config2_hex']=f'0x{CONFIG2:04X}'
rep['clock_hz']=16000000
rep['pwm_carrier_hz']=62500
rep['audio_rate_hz']=12500
rep['timer2_pr2']=63
rep['timer2_t2con']='0x24'
rep['score_bytes']=216
rep['wave_table_words']=144
rep['multiply_table_words']=256
rep['note_step_sample_rate']=12500
rep['sha256_full_hex']=hashlib.sha256((r/'firmware/micromusic_with_config.hex').read_bytes()).hexdigest()
(r/'reports/assembly.json').write_text(json.dumps(rep,indent=2)+'\n')
print('CONFIG1',hex(CONFIG1),'CONFIG2',hex(CONFIG2),'full HEX ready')

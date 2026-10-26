"""Build a full-history RAM-input WB player, reusing production PWM/IRQ code."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import build,build_wb

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--avr-gcc',required=True)
    p.add_argument('--packet-bytes',type=int,choices=[25,32],default=32);p.add_argument('--frame-load-cycles',type=int,default=25600)
    p.add_argument('--out',type=Path);args=p.parse_args()
    if not 0<=args.frame_load_cycles<=320000:p.error('Frame load must be 0..320000')
    source=build_wb.prepare();out=(args.out or build.ROOT/('build/angle-wb-stream-'+str(args.packet_bytes))).resolve();out.mkdir(parents=True,exist_ok=True)
    (out/'sample.h').write_text('#define SPEEX_SAMPLE_PACKET_BYTES '+str(args.packet_bytes)+'\n#define SPEEX_SAMPLE_FRAMES 1\nstatic const uint8_t sample_data[1] PROGMEM={0};\n',encoding='utf-8')
    exe=out/'wb.elf';build.run([args.avr_gcc,*build_wb.flags(source,'asm',args.packet_bytes==32),'-Os','-flto','-mmcu=atmega328p','-mcall-prologues','-mrelax',
        '-ffunction-sections','-fdata-sections','-I'+str(out),'-DSPEEX_AVR_FRAME_LOAD_CYCLES='+str(args.frame_load_cycles),
        *build_wb.sources(source),*[build.ROOT/'src'/s for s in build.ASM_SOURCES+build_wb.ASM_SOURCES],build.ROOT/'tests/avr_wb_stream.c','-Wl,--gc-sections','-o',exe])
    prefix=str(Path(args.avr_gcc).with_name('avr-'));ext='.exe' if args.avr_gcc.endswith('.exe') else ''
    build.run([prefix+'objcopy'+ext,'-O','binary','-R','.eeprom',exe,out/'wb.bin'])
    symbols=subprocess.check_output([prefix+'nm'+ext,'-n',exe],text=True);(out/'symbols.txt').write_text(symbols,encoding='utf-8')
    assert 'speex_embedded_player_unused_main' not in symbols and ' sample_data' not in symbols,'Embedded dummy data must be discarded'
    (out/'backend.json').write_text(json.dumps(dict(backend='asm',packetBytes=args.packet_bytes,frameLoadCycles=args.frame_load_cycles,
        binarySha256=hashlib.sha256((out/'wb.bin').read_bytes()).hexdigest(),source='tests/avr_wb_stream.c includes the production player; host supplies ready RAM packets',
        productionPlayerSha256=hashlib.sha256((build.ROOT/'src/wb_player.c').read_bytes()).hexdigest()),indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()

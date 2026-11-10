#!/usr/bin/env python3
"""Reproduce only the isolated shared-fold size/ABI/IRQ experiment.

This ignored handoff runner builds ASM decoders and isolated C primitives.
It never executes a full C decoder. All generated data stays under build/.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
import apply_profile
import build
import build_wb


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--avr-gcc',required=True)
 p.add_argument('--before-wb-fold',type=Path,required=True)
 p.add_argument('--candidate-wb-fold',type=Path,required=True)
 p.add_argument('--out',type=Path,default=ROOT/'build/size-review/reproduced')
 p.add_argument('--node',help='Optional ISA observer executable; requires --screen-data')
 p.add_argument('--screen-data',type=Path,help='Four profile folders, each with streams/ and oracle/')
 p.add_argument('--feature-matrix',action='store_true')
 args=p.parse_args()
 if bool(args.node)!=bool(args.screen_data):p.error('--node and --screen-data must be supplied together')
 _,source=build.prepare('shared-fold-repro-source');apply_profile.apply(source)
 table=source/'libspeex/high_lsp_tables.c';text=table.read_text(encoding='utf-8')
 text,n=re.subn(r'(const signed char \w+\[512\])=',r'\1 AVR_TABLE=',text);assert n==2
 table.write_text('#include "avr_tables.h"\n'+text,encoding='utf-8')
 ext='.exe' if args.avr_gcc.endswith('.exe') else '';prefix=str(Path(args.avr_gcc).with_name('avr-'))
 args.out.mkdir(parents=True,exist_ok=True)
 records=[]
 for variant,fold in [('before',args.before_wb_fold),('after',args.candidate_wb_fold)]:
  src=args.out/variant/'src';shutil.copytree(ROOT/'src',src,dirs_exist_ok=True);shutil.copyfile(fold,src/'wb_fold.S')
  def emit(label,nb4,low,width,main,unit=False,load=None):
   folder=args.out/variant/label;folder.mkdir(parents=True,exist_ok=True)
   flags=build_wb.flags(source,'asm',nb4,low);flags=['-I'+str(src) if f=='-I'+str(ROOT/'src') else f for f in flags]
   if unit:
    units=[src/'wb_fold.c',src/'wb_fold.S',*[source/'libspeex'/n for n in ['exc_10_32_table.c','exc_8_128_table.c','exc_10_16_table.c','exc_20_32_table.c']]]
   else:units=[src/q.name if q.parent==ROOT/'src' else q for q in build_wb.sources(source)]+[src/n for n in build.ASM_SOURCES+build_wb.ASM_SOURCES]
   options=['-DSPEEX_TEST_PACKET_BYTES='+str(width)]
   if load is not None:
    (folder/'sample.h').write_text('#define SPEEX_SAMPLE_PACKET_BYTES '+str(width)+'\n#define SPEEX_SAMPLE_FRAMES 1\nstatic const uint8_t sample_data[1] PROGMEM={0};\n',encoding='utf-8')
    options+=['-I'+str(folder),'-DSPEEX_AVR_FRAME_LOAD_CYCLES='+str(load),'-DSPEEX_AVR_PWM_PIN=9']
   exe=folder/'wb.elf'
   command=[args.avr_gcc,*flags,'-Os','-flto','-mmcu=atmega328p','-mcall-prologues','-mrelax','-ffunction-sections','-fdata-sections',*options,*units,main,'-Wl,--gc-sections,-Map='+str(folder/'wb.map'),'-o',exe]
   with (folder/'build.log').open('w',encoding='utf-8') as log:subprocess.run(list(map(str,command)),stdout=log,stderr=subprocess.STDOUT,check=True)
   subprocess.run([prefix+'objcopy'+ext,'-O','binary','-R','.eeprom',exe,folder/'wb.bin'],check=True)
   (folder/'symbols.txt').write_text(subprocess.check_output([prefix+'nm'+ext,'-n',exe],text=True),encoding='utf-8')
   metadata=dict(backend='asm',packetBytes=width,nb4Enabled=nb4,lowRates=low,binarySha256=sha(folder/'wb.bin'))
   if load is not None:metadata.update(frameLoadCycles=load,pwmPin=9)
   (folder/'backend.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
   records.append(dict(variant=variant,label=label,flashBytes=(folder/'wb.bin').stat().st_size,**metadata))
   print('BUILT',variant,label,records[-1]['flashBytes'],flush=True)
   return folder
  emit('all',True,7,25,ROOT/'tests/wb_decode.c')
  unit=emit('unit',True,7,25,Path(__file__).parent/'unit.c',unit=True)
  if args.node:
   with (unit/'run.log').open('w',encoding='utf-8') as log:subprocess.run([args.node,Path(__file__).parent/'verify_unit.mjs',unit],stdout=log,stderr=subprocess.STDOUT,check=True)
  for name,width,load in [('wb575',15,9600),('wb775',20,9600),('wb98',25,25600),('wb128',32,25600)]:
   folder=emit('irq-'+name,True,7,width,ROOT/'tests/avr_wb_stream.c',load=load)
   if args.node:
    with (folder/'run.log').open('w',encoding='utf-8') as log:subprocess.run([args.node,ROOT/'tests/verify_wb_stream.mjs','--firmware',folder,'--streams',args.screen_data/name/'streams','--oracle',args.screen_data/name/'oracle'],stdout=log,stderr=subprocess.STDOUT,check=True)
  if args.feature_matrix:
   for name,nb4,low in [('minimal',False,0),('nb1',False,4),('nb4',True,0),('nb2',False,1),('nb8',False,2)]:emit(name,nb4,low,25,ROOT/'tests/wb_decode.c')
 (args.out/'images.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':main()

#!/usr/bin/env python3
"""Compare AVR object code sections; NOT a linked-ELF, cycle or SRAM runtime test."""
from pathlib import Path
import json,re,subprocess,shutil,sys,tempfile
BASE=Path(__file__).resolve().parents[1]
CLANG=shutil.which('clang++')
OBJDUMP=shutil.which('llvm-objdump')
if not CLANG or not OBJDUMP:raise SystemExit('Need clang++ with AVR backend and llvm-objdump')
ARG=['-target','avr','-mmcu=atmega328p','-Os','-ffunction-sections','-fdata-sections',
     '-fno-exceptions','-fno-rtti','-nostdlib','-I'+str(BASE/'tests/avr_stub'),'-c']

def build(src,dest):
 subprocess.run([CLANG,*ARG,str(src),'-o',str(dest)],check=True)
 text=subprocess.run([OBJDUMP,'-h',str(dest)],check=True,capture_output=True,text=True).stdout
 sections={}
 for line in text.splitlines():
  s=line.strip().split()
  if len(s)>3 and s[0].isdigit() and (s[1].startswith('.text') or s[1]=='.progmem.data'):
   sections[s[1]]=int(s[2],16)
 return sections

def buildram(src,dest):
 subprocess.run([CLANG,*ARG,str(src),'-o',str(dest)],check=True)
 hexdump=subprocess.run([OBJDUMP,'-s','-j','.rodata.coreSize',str(dest)],check=True,capture_output=True,text=True).stdout
 m=re.search(r'\n\s*0000\s+([0-9a-f]{4})',hexdump)
 if not m:raise ValueError('cannot read coreSize from AVR .o')
 return int.from_bytes(bytes.fromhex(m.group(1)),'little')

def run():
 out=BASE/'reports';out.mkdir(exist_ok=True)
 avs={}
 for tag,source in [('rice_v4_general',BASE/'reference_v4/Lpx3AvrCore.cpp'),('rice_v5',BASE/'src/Lpx3AvrCore.cpp')]:
  obj=out/(tag+'.avr.o');ss=build(source,obj)
  text=sum(n for k,n in ss.items() if k.startswith('.text'))
  tables=ss.get('.progmem.data',0)
  avs[tag]={'object_file':obj.name,'text_sections_bytes':text,'progmem_tables_bytes':tables,
            'unlinked_not_final_flash':True,
            'functions':{k.split('Core')[-1]:v for k,v in ss.items() if k.startswith('.text.')}}
  subprocess.run([OBJDUMP,'-d','-r','--triple=avr','--mcpu=atmega328p',str(obj)],check=True,
                 stdout=(out/(tag+'.avr.disasm')).open('w'))
 for tag,src in [('rice_v4_general', BASE/'reference_v4/Lpx3AvrCore.cpp'),('rice_v5', BASE/'src/Lpx3AvrCore.cpp')]:
  # Names must match the active project header. Copy an inline 4/5 size probe.
  with tempfile.TemporaryDirectory() as d:
   fp=Path(d)/'size.cpp'
   fp.write_text(f'#include "{(src.parent/"Lpx3AvrCore.h").as_posix()}"\nextern "C" __attribute__((used)) const unsigned short coreSize=sizeof(Lpx3AvrCore);\n')
   avs[tag]['sram_core_bytes']=buildram(fp,Path(d)/'sram.o')
 delta=avs['rice_v5']['text_sections_bytes']-avs['rice_v4_general']['text_sections_bytes']
 avs['comparison']={'delta_text_bytes':delta,'savings_text_percent':round(-100*delta/avs['rice_v4_general']['text_sections_bytes'],3),
                    'no_avr_elf_or_cycle_measurement':True,'compile_target':'avr-atmega328p','compiler':subprocess.run([CLANG,'--version'],capture_output=True,text=True).stdout.splitlines()[0]}
 (out/'avr_object_metrics.json').write_text(json.dumps(avs,indent=2,ensure_ascii=False))
 print(json.dumps(avs['comparison'],indent=2))
 return avs
if __name__=='__main__':run()

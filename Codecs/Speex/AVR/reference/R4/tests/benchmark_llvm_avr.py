#!/usr/bin/env python3
"""Reproducible *model* cycles for Clang AVR assembly, not physical hardware."""
from pathlib import Path
import argparse,subprocess,sys,re,csv,struct,statistics,tempfile
R=Path(__file__).resolve().parents[1];P=R/'src'
sys.path.insert(0,str(P))
from cycle_interpreter import tbl_bytes,parse_source,CPU

def run_c_program(source, asm_file, stream, n):
 cmd=['clang','-target','avr','-mmcu=atmega328p','-ffreestanding','-I'+str(P/'test_shims'),'-I'+str(P),'-O3','-S',str(source),'-o',str(asm_file)]
 subprocess.run(cmd,check=True)
 ss=asm_file.read_text()
 standalone=re.sub(r'/\*.*?\*/','',(P/'lpc_fast.S').read_text(),flags=re.S)
 merged=asm_file.parent/'merged.s';pos=ss.index('speex_nb8_decode:');merged.write_text(ss[:pos]+standalone+'\n'+ss[pos:])
 flash=bytearray(0x10000);syms={};addr=0x4000
 for path in (P/'speex_tables.c',P/'cos_table.c',source):
  for name,b in tbl_bytes(path).items():
   syms[name]=addr;flash[addr:addr+len(b)]=b;addr+=len(b);addr+=addr&1
 rows,labels,blocks,src_line=parse_source(merged)
 cpu=CPU(rows,labels,blocks,src_line,syms,flash)
 output=[];timings=[];peaks=[]
 data=(R/'data'/(stream+'.spxraw')).read_bytes()
 n=min(n,len(data)//20)
 for i in range(n):
  cpu.m[0x380:0x394]=data[20*i:20*i+20]
  cy=cpu.callfn('speex_nb8_decode',[(24,0x100,2),(22,0x380,2),(20,0x400,2)])
  assert cpu.pair(24)==0
  samples=struct.unpack('<160h',cpu.m[0x400:0x540]);output.extend(samples)
  timings.append(cy);peaks.append(cpu._max_depth)
 return output,timings,peaks

if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--frames',type=int,default=3);args=a.parse_args()
 records=[]
 with tempfile.TemporaryDirectory() as td:
  td=Path(td)
  for stream in ('speech_ru','silence','random_40'):
   golden=None
   for label,path in (('baseline',R/'variants/baseline.c'),('cache10_fused',P/'speex_nb8.c')):
    pcm,cycles,stacks=run_c_program(path,td/(label+'.s'),stream,args.frames)
    if golden is None:golden=pcm
    assert pcm==golden,(label,stream,'PCM mismatch')
    record={'variant':label,'stream':stream,'frames':len(cycles),'mean_cycles':round(statistics.mean(cycles),1),'min_cycles':min(cycles),'max_cycles':max(cycles),'max_stack':max(stacks),'pcm_match':True}
    records.append(record)
    print('PASS',record,flush=True)
 with (R/'results/model_repro.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,records[0].keys());w.writeheader();w.writerows(records)
 print('Note: LLVM AVR instruction model, not avr-gcc or chip measurement.')

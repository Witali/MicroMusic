#!/usr/bin/env python3
"""Build two ROM-only FluidR3 wavetable arrangements with uniform 108T PWM."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import importlib.util
ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('old',ROOT/'../uniform-pwm/build.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
ins,jump=m.ins,m.jump
def slot_address(phase, level):
 # The 20T pulse needs a 9-byte entry; putting it last keeps each stage at 129B.
 offset=120 if level==5 else (level if level<5 else level-1)*8
 return 0x100+phase*129+offset

def tail(level,page):
 target=slot_address(page-0x10,level)
 return [ins(7,f'MVI L,{target&255:03X}H',0x2e,target&255,scratch=True),ins(7,f'MVI H,{target>>8:03X}H',0x26,target>>8,scratch=True),ins(5,'PCHL',0xe9)]

def program(phase,level,period):
 name=f'P{phase}_L{level}';body=name+'_BODY'
 head=[ins(4,'EI' if level else 'DI',0xfb if level else 0xf3),jump('JMP',body)]
 if phase<2:
  reset=name+'_RESET';pair='B' if phase==0 else 'D'
  prefix=[ins(10,'POP H',0xe1,scratch=True),ins(5,'INR H',0x24),jump('JZ',reset,0xca)]
  normal=[ins(5,'DCR H',0x25),ins(10,'DAD '+pair,0x09 if phase==0 else 0x19),ins(5,'MOV '+pair+',H',0x44 if phase==0 else 0x54),ins(5,'MOV '+('C' if phase==0 else 'E')+',L',0x4d if phase==0 else 0x5d,scratch=True)]
  tree=(prefix,[(None,(normal+tail(level,0x10+phase+1),[])),(reset,([ins(10,'LXI '+pair+',00000H',0x01 if phase==0 else 0x11,0,0,scratch=True)]+tail(level,0x10+phase+1),[]))])
 elif phase==2:
  record=name+'_RECORD'
  prefix=[ins(5,'DCR A',0x3d,scratch=True),jump('JZ',record,0xca)]
  rewind=[ins(10,'LXI H,0FFFAH',0x21,0xfa,0xff,scratch=True),ins(10,'DAD SP',0x39),ins(5,'SPHL',0xf9)]
  tree=(prefix,[(None,(rewind+tail(level,0x13),[])),(record,(tail(level,0x14),[]))])
 elif phase==3:
  mix=[ins(10,'POP H',0xe1),ins(5,'MOV L,B',0x68),ins(7,'MOV H,M',0x66),ins(5,'MOV L,D',0x6a),ins(7,'MOV L,M',0x6e),ins(7,'MVI H,001H',0x26,0x01,scratch=True),ins(5,'PCHL',0xe9)]
  tree=(mix,[])
 else:
  eof=name+'_EOF'
  read=[ins(10,'POP H',0xe1),ins(5,'MOV A,L',0x7d),ins(4,'ORA A',0xb7),jump('JZ',eof,0xca)]
  mix=[ins(5,'MOV L,B',0x68),ins(7,'MOV H,M',0x66),ins(5,'MOV L,D',0x6a),ins(7,'MOV L,M',0x6e),ins(7,'MVI H,001H',0x26,0x01,scratch=True),ins(5,'PCHL',0xe9)]
  tree=(read,[(None,(mix,[])),(eof,([ins(7,'MVI H,000H',0x26,0,scratch=True),ins(7,'HLT',0x76)],[]))])
 options=[]
 for rest,ht,hd in m.di_options(head[1:],4,level==0,level*4,True):
  hseq=[head[0]]+rest
  if sum(len(x[2]) for x in hseq)>(9 if level==5 else 8):continue
  planned=m.schedule(tree,ht,hd,level*4,period)
  if planned:options.append((hseq,planned))
 return None if not options else (name,body,*options[0])


def digest(data):
 return hashlib.sha256(data).hexdigest()


def save(name, data, check, root=ROOT):
 m.save(root/name, data, check)


def plan_score(source, bank, period, cpu_hz=3500000):
 if cpu_hz==3500000:
  _, notes=m.plan_score(source,period)
 else:
  elapsed=emitted=0;notes=[];frame_t=period*4
  for note in source['notes']:
   elapsed+=note['duration_t']
   denominator=3500000*frame_t
   total=(elapsed*cpu_hz+denominator//2)//denominator
   ratio=frame_t*3500000/((note['duration_t']/note['groups'])*cpu_hz)
   steps=[None if value is None else round(value*ratio) for value in note['steps']]
   assert all(value is None or 0<value<0xff00 for value in steps)
   notes.append({'frames':total-emitted,'steps':steps,'duration_error_t':total*frame_t-elapsed*cpu_hz/3500000,
    'pitch_error_cents':[None if old is None else 1200*math.log2(new/(old*ratio)) for old,new in zip(note['steps'],steps)]})
   emitted=total
 ages=[0.,0.]; previous=[None,None]; chunks=[]
 for original,note in zip(source['notes'],notes):
  registers=[]
  for channel,step in enumerate(original['steps']):
   if step!=previous[channel]:ages[channel]=0.
   previous[channel]=step
   frequency=0 if step is None else step*3500000/original['group_t']/65536
   midi=0 if not frequency else round(69+12*math.log2(frequency/440))
   registers.append(int(channel==0 and midi>=bank['piano_register_split_midi']))
  remaining=note['frames']
  while remaining:
   count=min(255,remaining);mid=[a+count*period*2/cpu_hz for a in ages]
   piano=sum(mid[0]>=t for t in bank['piano_stage_boundaries_seconds'])
   guitar=sum(mid[1]>=t for t in bank['guitar_stage_boundaries_seconds'])
   chunks.append({'frames':count,'steps':note['steps'],'piano_register':registers[0],
                  'piano_stage':piano,'guitar_stage':guitar})
   ages=[a+count*period*4/cpu_hz for a in ages];remaining-=count
 return chunks,notes


def waves(bank, chunk):
 piano=bank['banks'][chunk['piano_register']]['waves'][chunk['piano_stage']]
 guitar=bank['banks'][2]['waves'][chunk['guitar_stage']]
 return piano,guitar


def mix_range(bank,chunks):
 # Update phases with the current record, then read the following bank when
 # the next header is consumed during the fourth PWM slot of a chunk boundary.
 bc=de=0;low=30;high=0
 for index,chunk in enumerate(chunks):
  for frame in range(chunk['frames']):
   bc=0 if chunk['steps'][0] is None else (bc+chunk['steps'][0])&65535
   de=0 if chunk['steps'][1] is None else (de+chunk['steps'][1])&65535
   lookup=chunks[index+1] if frame==chunk['frames']-1 and index+1<len(chunks) else chunk
   if index==len(chunks)-1 and frame==chunk['frames']-1:break
   piano,guitar=waves(bank,lookup)
   value=piano[bc>>8]+guitar[de>>8]
   low=min(low,value);high=max(high,value)
 assert high>low
 return low,high


def level_for(total,low,high):
 return max(0,min(15,((total-low)*15+(high-low)//2)//(high-low)))


def build(source,bank,period,check,cpu_hz=3500000,*,kernel=None,output_root=None):
 root=output_root or (ROOT if cpu_hz==3500000 else ROOT/'clocks'/str(cpu_hz))
 phases=6 if kernel else 5
 plans=[(kernel or program)(phase,level,period) for phase in range(phases) for level in range(16)]
 assert all(plans),[(i//16,i%16) for i,p in enumerate(plans) if p is None]
 chunks,notes=plan_score(source,bank,period,cpu_hz)
 low,high=mix_range(bank,chunks)
 head=m.Code(0)
 head.emit('DI',0xf3);head.emit('LXI B,00000H',0x01,0,0);head.emit('LXI D,00000H',0x11,0,0)
 head.word('LXI SP,SCORE',0x31,'SCORE');head.emit('POP H',0xe1);head.emit('MOV A,L',0x7d)
 target=slot_address(0,8)
 head.emit(f'LXI H,{target:05X}H',0x21,target&255,target>>8);head.emit('PCHL',0xe9)
 codes=[head];cursor=0x100+phases*129
 for index,(name,body,entry,tree) in enumerate(plans):
  phase,level=divmod(index,16);slot=m.Code(slot_address(phase,level));slot.label(name)
  m.emit_actions(slot,entry)
  assert len(slot.data)<=(9 if level==5 else 8)
  code=m.Code(cursor);code.label(body);m.emit_tree(code,tree)
  codes.extend([slot,code]);cursor=code.pc
 score_at=(cursor+1)&~1;score_bytes=len(chunks)*6+2
 bank_at=(score_at+score_bytes+255)&~255
 mix_page=bank_at>>8;first_page=mix_page+32
 end=(first_page+16)*256
 assert end<=32768,(end,score_at,score_bytes,bank_at)
 labels={k:v for code in codes for k,v in code.labels.items()}|{'SCORE':score_at}
 rom=bytearray([0xff]*32768)
 for code in codes:
  code.resolve(labels);rom[code.origin:code.pc]=code.data
 data=bytearray()
 for chunk in chunks:
  combo=chunk['piano_register']*8+chunk['piano_stage']*2+chunk['guitar_stage']
  data+=bytes([chunk['frames'],first_page+combo])
  for step in chunk['steps']:data+=(0xff00 if step is None else step).to_bytes(2,'little')
 data+=bytes(2)
 rom[score_at:score_at+len(data)]=data
 for guitar_stage in range(2):
  guitar=bank['banks'][2]['waves'][guitar_stage]
  for piano_value in range(16):
   page=mix_page+guitar_stage*16+piano_value
   rom[page*256:(page+1)*256]=bytes(slot_address(0,level_for(piano_value+q,low,high))&255 for q in guitar)
 for register in range(2):
  for stage in range(4):
   piano=bank['banks'][register]['waves'][stage]
   for guitar_stage in range(2):
    page=first_page+register*8+stage*2+guitar_stage
    rom[page*256:(page+1)*256]=bytes(mix_page+guitar_stage*16+q for q in piano)
 name=source['name']+'-fluid-pwm'+str(period)
 meta={'name':name,'backend':'i8080-asm','bytes':len(rom),'sha256':digest(rom),
  'cpu_hz':cpu_hz,'period_t':period,'carrier_hz':cpu_hz/period,'frame_t':period*4,
  'pulses_per_frame':4,'frames':sum(c['frames'] for c in chunks),'levels':16,'width_t':'4*level; zero is silent',
  'source_sha256':source['original_sha256'],'soundfont_sha256':bank['soundfont_sha256'],
  'bank_sha256':digest(json.dumps(bank,sort_keys=True,separators=(',',':')).encode()),
  'instruments':{'lead':'FluidR3 GM0 Yamaha Grand Piano','accompaniment':'FluidR3 GM24 Nylon String Guitar'},
  'samples_per_wave':256,'piano_registers':2,'piano_ages':4,'guitar_ages':2,
  'mix_minimum_sum':low,'mix_maximum_sum':high,'mix_normalization':'Observed full-score extrema -> levels 0..15; one gain across the whole piece',
  'score_at':score_at,'score_bytes':score_bytes,'bank_at':bank_at,'mix_page':mix_page,'first_wave_page':first_page,
  'bank_bytes':12288,'used_bytes':end,'free_bytes':32768-end,'chunks':chunks,'notes':notes,
  'labels':{k:f'{v:04X}' for k,v in labels.items()},'entry_offsets':{str(l):slot_address(0,l)&255 for l in range(16)},
  'hardware_tested':False,'active_interrupts_supported':False}
 if kernel:
  meta['kernel']='Direct jumps, early record header, DCR A live Z across phase1/2'
  meta['dispatch_phases']=phases
  meta['bank_source']=str(Path(os.path.relpath(ROOT if cpu_hz==3500000 else ROOT/'clocks'/str(cpu_hz),root))/'bank.json').replace('\\','/')
 save(name+'.bin',rom,check,root);save(name+'.hex',m.voice.hex_image(rom),check,root)
 save(name+'.json',json.dumps(meta,indent=2)+'\n',check,root)
 asm=[f'; Intel 8080, RAM-free FluidR3 wavetable model, uniform {period}T PWM.',
      '; Explicit ASM build; portable default arithmetic: fluid.c / fluid.h.',
      '; BC/DE=phase; A=frame counter; SP=read-only score cursor; HL=scratch/lookup.',
      '; 129-byte dispatch stages: fifteen 8-byte cells and one 9-byte cell (level 5).',
      '; INT inactive, no WAIT/HOLD. Full data, lookup tables and score generated by build.py.']
 for code in codes:asm+=['',f'    ORG {code.origin:05X}H']+code.source
 save(name+'.asm','\n'.join(asm)+'\n',check,root)
 print(f'{name}: {end}/32768 bytes, {meta["frames"]} frames, mix extrema {low}..{high} -> 0..15')
 return meta


def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--backend',choices=['c','i8080-asm'],default='c');p.add_argument('--architecture',default='portable')
 p.add_argument('--enable-asm',action='store_true');p.add_argument('--check',action='store_true')
 p.add_argument('--cpu-hz',type=int,choices=[2000000,2500000,3500000],default=3500000)
 args=p.parse_args()
 if args.backend=='c':
  print('Portable C selected: fluid.c. No assembly ROM is built.');return
 if args.architecture!='i8080' or not args.enable_asm:p.error('Assembly requires --architecture i8080 --enable-asm')
 root=ROOT if args.cpu_hz==3500000 else ROOT/'clocks'/str(args.cpu_hz)
 bank=json.loads((root/'bank.json').read_text())
 assert bank.get('cpu_hz',3500000)==args.cpu_hz,'Bank clock mismatch'
 scores=json.loads((ROOT/'../uniform-pwm/source-score.json').read_text())['tunes']
 for score in scores:build(score,bank,108,args.check,args.cpu_hz)


if __name__=='__main__':main()

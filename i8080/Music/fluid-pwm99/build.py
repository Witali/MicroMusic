"""Explicit Intel8080 FluidR3 ASM backend, uniform99T / four pulses per sample."""
from pathlib import Path
from functools import lru_cache
import importlib.util,json,argparse
ROOT=Path(__file__).resolve().parent
R=ROOT.parents[2]
def load(name,path):
 s=importlib.util.spec_from_file_location(name,R/path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
p=load('p','i8080/pwm_tools.py');old=load('old','i8080/Music/fluid-pwm/build.py')
i,j=p.ins,p.jump
def tree(phase,level):
 n=f'P{phase}_L{level}'
 to=lambda ph:j(f'P{ph}_L{level}')
 if phase<2:
  reg='B' if phase==0 else 'D';reset=n+'_RESET'
  prefix=(i(10,'POP H',0xe1),i(5,'INR H',0x24),j(reset,'JZ',0xca))
  count=(i(5,'DCR A',0x3d),) if phase==1 else ()
  normal=(i(5,'DCR H',0x25),i(10,'DAD '+reg,0x09 if phase==0 else 0x19),i(5,'MOV '+reg+',H',0x44 if phase==0 else 0x54),i(5,'MOV '+('C' if phase==0 else 'E')+',L',0x4d if phase==0 else 0x5d))
  t=(prefix,((None,(normal+count+(to(phase+1),),())),(reset,((i(10,'LXI '+reg+',00000H',0x01 if phase==0 else 0x11,0,0),)+count+(to(phase+1),),()))))
 elif phase==2:
  record=n+'_RECORD';eof=n+'_EOF'
  read=(i(10,'POP H',0xe1),i(5,'MOV A,L',0x7d),i(4,'ORA A',0xb7),j(eof,'JZ',0xca))
  t=((j(record,'JZ',0xca),),((None,((i(10,'LXI H,0FFFAH',0x21,0xfa,0xff),i(10,'DAD SP',0x39),i(5,'SPHL',0xf9),to(3)),())),(record,(read,((None,((to(4),),())),(eof,((to(5),),())))))))
 elif phase<5:
  ops=(i(10,'POP H',0xe1),) if phase==3 else ()
  t=(ops+(i(5,'MOV L,B',0x68),i(7,'MOV H,M',0x66),i(5,'MOV L,D',0x6a),i(7,'MOV L,M',0x6e),i(7,'MVI H,001H',0x26,1),i(5,'PCHL',0xe9)),())
 else:t=((i(7,'HLT',0x76),),())
 return ((j(n+'_BODY'),)+t[0],t[1])
def convert(t):
 return tuple(a+(False,) for a in t[0]),tuple((label,convert(child)) for label,child in t[1])

@lru_cache(None)
def program(phase,level,period=99):
 planned=p.schedule(tree(phase,level),level*4,period,entry_limit=9 if level==5 else 8,z_live_out=phase==1)
 if planned is None:return None
 entry,body=p.split_entry(planned)
 return f'P{phase}_L{level}',f'P{phase}_L{level}_BODY',convert(entry)[0],convert(body)

def search():
 scores=json.loads((R/'i8080/Music/uniform-pwm/source-score.json').read_text())['tunes'];rows=[]
 for period in range(82,109):
  plans=[p.schedule(tree(ph,q),q*4,period,entry_limit=9 if q==5 else 8,z_live_out=ph==1) for ph in range(6) for q in range(16)]
  missing=[divmod(k,16) for k,t in enumerate(plans) if not t];row={'period':period,'missing':missing}
  if not missing:
   cursor=0x100+6*129+sum(p.size(p.split_entry(t)[1]) for t in plans);at=(cursor+1)&~1;sizes=[]
   for hz in (2000000,2500000,3500000):
    bank=json.loads((R/'i8080/Music/fluid-pwm'/('' if hz==3500000 else f'clocks/{hz}/')/'bank.json').read_text())
    for score in scores:
     chunks,_=old.plan_score(score,bank,period,hz);end=((at+len(chunks)*6+2+255)//256)*256+12288;sizes.append(end)
   row['rom_used_bytes']=sizes;row['body_bytes']=cursor-(0x100+6*129)
  rows.append(row)
 return rows

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--backend',choices=['c','i8080-asm'],default='c')
 parser.add_argument('--architecture',default='portable');parser.add_argument('--enable-asm',action='store_true')
 parser.add_argument('--check',action='store_true');parser.add_argument('--search',action='store_true')
 parser.add_argument('--cpu-hz',type=int,choices=[2000000,2500000,3500000],default=3500000)
 args=parser.parse_args()
 if args.search:
  p.save(ROOT,'SEARCH.json',{'scope':'These six handler templates and fixed16level4T widths, not a global ISA lower bound','rows':search()},args.check)
  print('Verified fixed-template search' if args.check else 'Wrote fixed-template search');return
 if args.backend=='c':print('Portable C selected: ../fluid-pwm/fluid.c; no assembly ROM built.');return
 if args.architecture!='i8080' or not args.enable_asm:parser.error('Assembly requires --architecture i8080 --enable-asm')
 hz=args.cpu_hz
 bank_root=R/'i8080/Music/fluid-pwm'/('' if hz==3500000 else f'clocks/{hz}/')
 bank=json.loads((bank_root/'bank.json').read_text())
 root=ROOT if hz==3500000 else ROOT/'clocks'/str(hz)
 for score in json.loads((R/'i8080/Music/uniform-pwm/source-score.json').read_text())['tunes']:
  old.build(score,bank,99,args.check,hz,kernel=program,output_root=root)

if __name__=='__main__':main()

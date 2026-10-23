#!/usr/bin/env python3
"""Build a 64 KiB *ROM-only* Intel 8080 diagnostic with a self-contained listing.

No RAM, no IO port, no calls/pushes/writes. CPU A15 is physically connected to the ROM; all CPU addresses 0000..FFFF are distinct.
The CRC-16 (polynomial 002Dh, initial 0, non-reflected) covers all physical ROM
bytes including the two-byte correction field. The host chooses the correction
word so that CRC(full ROM)==0. Verified using 8080-only 512-byte ROM lookup (two pages).
"""
from __future__ import annotations
import ast, hashlib, json, re
from pathlib import Path

ROOT=Path(__file__).resolve().parent
ROM_SIZE=0x10000
CODE_START=0x2100
CS_ADDR=0xFFF0

REG={'B':0,'C':1,'D':2,'E':3,'H':4,'L':5,'M':6,'A':7}
RP={'B':0,'D':1,'H':2,'SP':3}
SINGLES={
 'NOP':0x00,'RLC':0x07,'RRC':0x0f,'RAL':0x17,'RAR':0x1f,
 'DAA':0x27,'CMA':0x2f,'STC':0x37,'CMC':0x3f,'HLT':0x76,
 'RET':0xc9,'PCHL':0xe9,'XCHG':0xeb,'DI':0xf3,'EI':0xfb,'SPHL':0xf9,
 'RNZ':0xc0,'RZ':0xc8,'RNC':0xd0,'RC':0xd8,'RPO':0xe0,'RPE':0xe8,'RP':0xf0,'RM':0xf8,
}
JUMPS={'JMP':0xc3,'JNZ':0xc2,'JZ':0xca,'JNC':0xd2,'JC':0xda,'JPO':0xe2,'JPE':0xea,'JP':0xf2,'JM':0xfa}
CALLS={'CALL':0xcd,'CNZ':0xc4,'CZ':0xcc,'CNC':0xd4,'CC':0xdc,'CPO':0xe4,'CPE':0xec,'CP':0xf4,'CM':0xfc}
IMMED={'ADI':0xc6,'ACI':0xce,'SUI':0xd6,'SBI':0xde,'ANI':0xe6,'XRI':0xee,'ORI':0xf6,'CPI':0xfe,'IN':0xdb,'OUT':0xd3}
ALU={'ADD':0,'ADC':1,'SUB':2,'SBB':3,'ANA':4,'XRA':5,'ORA':6,'CMP':7}
LDADDR={'LDA':0x3a,'LHLD':0x2a,'STA':0x32,'SHLD':0x22}


def hx(v,n=2):
 s=f'{v:0{n}X}';return ('0' if s[0].isalpha() else '')+s+'H'

class Assembler:
 def __init__(self,source):
  self.lines=source.splitlines();self.labels={};self.coverage=[]
 def expr(self,s,labels):
  s=s.strip()
  s=re.sub(r'\b([0-9][0-9A-Fa-f]*)H\b',lambda m:'0x'+m.group(1),s,flags=re.I)
  for label,v in labels.items():
   s=re.sub(r'\b'+re.escape(label)+r'\b',str(v),s,flags=re.I)
  root=ast.parse(s,mode='eval')
  def walk(n):
   if isinstance(n,ast.Constant) and isinstance(n.value,int):return n.value
   if isinstance(n,ast.BinOp):
    a,b=walk(n.left),walk(n.right)
    if isinstance(n.op,ast.Add):return a+b
    if isinstance(n.op,ast.Sub):return a-b
    if isinstance(n.op,ast.BitOr):return a|b
    if isinstance(n.op,ast.BitXor):return a^b
   raise ValueError('Unsupported expression '+s)
  return walk(root.body)
 def parse_line(self,l):
  s=l.split(';')[0].strip()
  if not s:return '',[]
  if ':' in s:
   name,other=s.split(':',1);return 'LABEL',[name.strip().upper(),other.strip()]
  parts=s.split(None,1)
  return parts[0].upper(),([x.strip() for x in parts[1].split(',')] if len(parts)>1 else [])
 def size(self,m,args):
  if m in ('ORG','END'):return 0
  if m=='DB':return len(args)
  if m=='DW':return 2*len(args)
  if m in SINGLES:return 1
  if m in JUMPS or m in CALLS or m in LDADDR or m=='LXI':return 3
  if m in IMMED or m=='MVI':return 2
  if m in ('MOV','INX','DCX','DAD','INR','DCR','LDAX','STAX','PUSH','POP') or m in ALU:return 1
  raise ValueError('Unknown instruction '+m)
 def generate(self,m,args,labels):
  ev=lambda s:self.expr(s,labels)
  if m=='DB':return [ev(s)&255 for s in args]
  if m=='DW':
   out=[]
   for x in args:
    v=ev(x);out.extend((v&255,(v>>8)&255))
   return out
  if m in SINGLES:return [SINGLES[m]]
  if m in JUMPS or m in CALLS or m in LDADDR:
   op=(JUMPS|CALLS|LDADDR)[m];v=ev(args[0]);return [op,v&255,(v>>8)&255]
  if m in IMMED:return [IMMED[m],ev(args[0])&255]
  if m=='LXI':
   v=ev(args[1]);return [1+(RP[args[0].upper()]<<4),v&255,(v>>8)&255]
  if m=='MVI':return [6+(REG[args[0].upper()]<<3),ev(args[1])&255]
  if m=='MOV':return [0x40+(REG[args[0].upper()]<<3)+REG[args[1].upper()]]
  if m in ALU:return [0x80+(ALU[m]<<3)+REG[args[0].upper()]]
  if m=='INR':return [4+(REG[args[0].upper()]<<3)]
  if m=='DCR':return [5+(REG[args[0].upper()]<<3)]
  if m in ('INX','DCX','DAD'):return [{'INX':3,'DCX':0x0b,'DAD':9}[m]+(RP[args[0].upper()]<<4)]
  if m in ('LDAX','STAX'):return [({'LDAX':0x0a,'STAX':2}[m])+((RP[args[0].upper()])<<4)]
  if m in ('PUSH','POP'):return [({'PUSH':0xc5,'POP':0xc1}[m])+((3 if args[0].upper()=='PSW' else RP[args[0].upper()])<<4)]
  raise ValueError('Unknown instruction '+m)
 def assemble(self,fill=True):
  location=0; parsed=[]
  for no,line in enumerate(self.lines,1):
   m,args=self.parse_line(line)
   if not m:continue
   if m=='LABEL':
    name,tail=args
    if name in self.labels:raise ValueError('duplicate '+name)
    self.labels[name]=location
    m,args=self.parse_line(tail) if tail else ('',[])
    if not m:continue
   if m=='ORG': location=self.expr(args[0],self.labels);continue
   if m=='END':break
   parsed.append((location,m,args,no))
   location+=self.size(m,args)
  mem=bytearray((sig(i) if fill else 0 for i in range(ROM_SIZE)))
  used=set(); 
  for loc,m,args,no in parsed:
   try:data=self.generate(m,args,self.labels)
   except Exception as e:raise ValueError(f'line {no} {m} {args}: {e}') from e
   if loc<0 or loc+len(data)>ROM_SIZE:raise ValueError('Outside ROM at '+hex(loc))
   for i,x in enumerate(data):
    if loc+i in used:raise ValueError('overlap '+hex(loc+i))
    used.add(loc+i);mem[loc+i]=x
   self.coverage.append((loc,len(data),m))
  return mem,used

# Stable address-specific pseudorandom background, generated on host.  Source
# listing contains each actual filler byte, so no Python is needed to assemble
# the final expanded ASM in a normal 8080 assembler supporting ORG/DB/DW.
def sig(addr):
 return hashlib.blake2s(addr.to_bytes(2,'little')+b'8080-rom64-diagnostic-v1',digest_size=1).digest()[0]


def emit(lines,s='',comment=None):
 if comment: lines.append('; '+comment)
 lines.append(('    '+s) if s else '')

def test_cp(lines,setup,expected,error='BAD_CPU',note=''):
 if note:emit(lines,comment=note)
 for x in setup:emit(lines,x)
 emit(lines,'CPI '+hx(expected));emit(lines,'JNZ '+error)

def body_source():
 q=[];a=lambda s='':emit(q,s)
 a('; ===============================================================')
 a('; INTEL 8080 (NOT Z80) / 64 KiB ROM / ZERO RAM / A15 CONNECTED')
 a('; RESET at 0000h; INTE on pin 16; INT pin 14 must be LOW.')
 a('; Intel 8080A 3.5 MHz is above official datasheet maximum:')
 a('; use a tested 8080-compatible chip and suitable clock circuitry.')
 a('; ===============================================================')
 a('ORG '+hx(CODE_START,4))
 a('START:')
 a('    DI                 ; INTE low; forbid spurious interrupt')
 a('    ; --- Stage 0: audible short power-on beep (~83 ms at 3.5 MHz)')
 a('    MVI B, '+hx(90))
 a('BOOT_TONE:')
 a('    EI                 ; INTE=1')
 a('    MVI C, '+hx(105))
 a('BOOT_HIGH:')
 a('    DCR C')
 a('    JNZ BOOT_HIGH')
 a('    DI                 ; INTE=0')
 a('    MVI C, '+hx(105))
 a('BOOT_LOW:')
 a('    DCR C')
 a('    JNZ BOOT_LOW')
 a('    DCR B')
 a('    JNZ BOOT_TONE')
 a('    DI')
 a('')
 a('; ===== Секция 1. БЫСТРАЯ CRC-16, 2 таблицы в ПЗУ =====')
 a('; CRC-16 полином 002Dh, init=0000h, без отражения, CRC образа = 0.')
 a('; Верхняя таблица на 1C00h, нижняя на 1D00h; каждая 256 байт.')
 a('; BC хранит CRC: B=старший байт, C=младший; DE — адрес ROM.')
 a('; HL используется только для табличного чтения; никакой ОЗУ.')
 a('; Для одного байта: index = (ROM[DE] XOR B).')
 a('; new B = C XOR TABLE_HI[index]; new C = TABLE_LO[index].')
 a('    LXI D, 0000H      ; ROM address')
 a('    LXI B, 0000H      ; CRC=0000h')
 a('ROM_CRC_BYTE:')
 a('    LDAX D            ; 7T: next byte of ROM')
 a('    XRA B             ; 4T: lookup index')
 a('    MOV L,A           ; 5T')
 a('    MVI H,01CH        ; 7T: high table base=1C00h')
 a('    MOV A,M           ; 7T: high CRC table byte')
 a('    XRA C             ; 4T: new high = old low XOR table high')
 a('    MOV B,A           ; 5T: save high')
 a('    INR H             ; 5T: switch to low table at 1D00h')
 a('    MOV A,M           ; 7T: low CRC table byte')
 a('    MOV C,A           ; 5T: save low')
 a('    INX D             ; 5T: next ROM address')
 a('    MOV A,D')
 a('    ORA E            ; 64 KiB: END when DE wraps to 0000h')
 a('    JNZ ROM_CRC_BYTE')
 a('    MOV A,B')
 a('    ORA C')
 a('    JNZ BAD_CHECKSUM')
 a('')
 a('; ===== Секция 2. Адресная шина A0..A15: бегущий 0/1 =======')
 a('; For each of 16 address lines test bit 0 -> 1 while others are 0, then')
 a('; bit 1 -> 0 while others are 1. Two anchor addresses 0000/FFFF.')
 a('; Detect open/stuck/shorted lines where returned bytes differ.')
 a('; A15 IS tested, and must be routed to the ROM address pin.')
 def addr_chk(addr,expected,tag):
  a('    LXI H, '+hx(addr,4)+f' ; {tag}')
  a('    MOV A,M')
  a('    CPI '+hx(expected))
  a('    JNZ BAD_ADDRESS')
 for n in range(16):
  low=0; high=1<<n; low_ones=(0xffff ^ high); high_ones=0xffff
  a(f'    ; A{n}: all-zero background: 0 -> 1; all-one: 0 -> 1')
  for addr,expected,tag in [(low,0xc3,'zero anchor'),(high, (0 if n==0 else 0x21 if n==1 else 0x01 if n==12 else sig(high)),'walking 1'),(low_ones,sig(low_ones),'walking 0'),(high_ones,sig(high_ones),'ones anchor')]:
   addr_chk(addr,expected,tag)
 a('')
 a('; ===== Секция 3. Шина данных D0..D7: бегущая 1/0 =======')
 a('; Locations 1000..1007 store 01,02,04,...80;')
 a('; locations 1010..1017 store FE,FD,FB,...7F.')
 a('    LXI H, 01000H')
 a('    MVI B, 01H')
 a('DATA_ONE_LOOP:')
 a('    MOV A,M')
 a('    CMP B')
 a('    JNZ BAD_DATA')
 a('    INX H')
 a('    MOV A,B')
 a('    RLC')
 a('    MOV B,A')
 a('    CPI 01H')
 a('    JNZ DATA_ONE_LOOP')
 a('    LXI H, 01010H')
 a('    MVI B, 0FEH')
 a('DATA_ZERO_LOOP:')
 a('    MOV A,M')
 a('    CMP B')
 a('    JNZ BAD_DATA')
 a('    INX H')
 a('    MOV A,B')
 a('    RLC')
 a('    MOV B,A')
 a('    CPI 0FEH')
 a('    JNZ DATA_ZERO_LOOP')
 a('')
 a('; ===== Секция 4. Проверка MOV и регистров без ОЗУ ========')
 a('; Only tests where the result can be observed without RAM or I/O.')
 a('; Checks representative flags/results plus every register-to-')
 a('; register MOV opcode and every 8-bit ALU source (including M).')
 a('    NOP')
 a('    JMP TEST_REGISTER_MOV')
 a('    JMP BAD_CPU       ; unreachable if JMP works')
 a('TEST_REGISTER_MOV:')
 regs='BCDEHLA'
 for src in regs:
  for dst in regs:
   a(f'    ; MOV {dst},{src} and register/accumulator data path')
   a(f'    MVI {src}, 0A5H')
   a(f'    MOV {dst},{src}')
   a(f'    MOV A,{dst}')
   a('    CPI 0A5H')
   a('    JNZ BAD_CPU')
 # distinct source-M variants; must reset HL after each as H/L may be overwritten
 a('    ; MOV r,M: read-only ROM operand, never MOV M,r')
 for dst in regs:
  a('    LXI H, 01000H')
  a(f'    MOV {dst},M')
  a(f'    MOV A,{dst}')
  a('    CPI 01H');a('    JNZ BAD_CPU')
 a('')
 a('; ===== Секция 5. АЛУ: арифметика и логика с регистрами ==')
 # For r=A, the operand necessarily equals A=0x35; all other operands=0x22.
 for group in ALU:
  for reg in list(regs)+['M']:
   v=0x35 if reg=='A' else 0x22; aa=0x35
   c=1 if group in ('ADC','SBB') else 0
   if group=='ADD': out=(aa+v)&255; carry=int(aa+v>255); zero=int(out==0)
   elif group=='ADC': out=(aa+v+c)&255;carry=int(aa+v+c>255);zero=int(out==0)
   elif group=='SUB':out=(aa-v)&255;carry=int(aa<v);zero=int(out==0)
   elif group=='SBB':out=(aa-v-c)&255;carry=int(aa<v+c);zero=int(out==0)
   elif group=='ANA':out=aa&v;carry=0;zero=int(out==0)
   elif group=='XRA':out=aa^v;carry=0;zero=int(out==0)
   elif group=='ORA':out=aa|v;carry=0;zero=int(out==0)
   elif group=='CMP':out=aa;carry=int(aa<v);zero=int(aa==v)
   a(f'    ; {group} {reg}: expected A={hx(out)}, Z={zero}, CY={carry}')
   if reg=='M':a('    LXI H, 01018H       ; immutable operand 22h')
   elif reg!='A':a(f'    MVI {reg}, 022H')
   a('    MVI A, 035H')
   if c:a('    STC')
   else:a('    STC');a('    CMC        ; CY clear, check carry output of ALU')
   a(f'    {group} {reg}')
   a('    '+('JZ' if not zero else 'JNZ')+' BAD_CPU')
   a('    '+('JC' if not carry else 'JNC')+' BAD_CPU')
   a('    CPI '+hx(out))
   a('    JNZ BAD_CPU')
 a('')
 a('; ===== Секция 6. Непосредственные операции АЛУ и флаги ==')
 for op in ['ADI','ACI','SUI','SBI','ANI','XRI','ORI','CPI']:
  group=['ADI','ACI','SUI','SBI','ANI','XRI','ORI','CPI'].index(op)
  v=0x22;aa=0x35;c=1 if op in ('ACI','SBI') else 0
  if op in ('ADI','ACI'):out=(aa+v+c)&255;cy=int(aa+v+c>255)
  elif op in ('SUI','SBI'):out=(aa-v-c)&255;cy=int(aa<v+c)
  elif op=='ANI':out=aa&v;cy=0
  elif op=='XRI':out=aa^v;cy=0
  elif op=='ORI':out=aa|v;cy=0
  else:out=aa;cy=0
  a(f'    ; {op} 22h, expected A={hx(out)} CY={cy}')
  a('    MVI A, 035H')
  a('    STC' if c else '    CMC') # cannot assume CMC clears here!
  # ensure CY=0 for non-carry via STC+CMC
  if not c:
   q.pop();a('    STC');a('    CMC')
  a(f'    {op} 022H')
  a('    '+('JC' if not cy else 'JNC')+' BAD_CPU')
  a('    CPI '+hx(out));a('    JNZ BAD_CPU')
 a('    ; --- INR/DCR: cover all seven register encodings and preserve CY')
 for r in 'BCDEHLA':
  a('    ; INR '+r+' and DCR '+r+' preserve the carry flag')
  a('    MVI '+r+', 07FH')
  a('    STC')
  a('    INR '+r)
  a('    JNC BAD_CPU')
  a('    MOV A,'+r)
  a('    CPI 080H')
  a('    JNZ BAD_CPU')
  a('    STC')
  a('    DCR '+r)
  a('    JNC BAD_CPU')
  a('    MOV A,'+r)
  a('    CPI 07FH')
  a('    JNZ BAD_CPU')
 a('    ; Critical 8-bit flags: zero/carry/sign/parity')
 a('    MVI A, 0FFH')
 a('    ADI 01H')
 a('    JNZ BAD_CPU     ; FF+01 wraps to zero')
 a('    JNC BAD_CPU     ; carry must be set')
 a('    JPO BAD_CPU     ; parity of 00 = even')
 a('    JM BAD_CPU      ; zero has positive sign')
 a('    MVI A, 07FH')
 a('    ADI 01H')
 a('    JP BAD_CPU      ; result 80h is negative')
 a('    JPE BAD_CPU     ; 80h has odd parity')
 a('    JC BAD_CPU      ; no carry')
 a('    ; DAA after 09h+09h must give packed BCD 18h')
 a('    MVI A, 09H')
 a('    ADI 09H')
 a('    DAA')
 a('    CPI 018H')
 a('    JNZ BAD_CPU')
 a('    ; RLC,RRC,RAL,RAR and carry flip-flop')
 for ops,val,expected,cy in [(['MVI A, 081H','RLC'],0x81,0x03,1),(['MVI A, 081H','RRC'],0x81,0xc0,1),(['MVI A, 080H','STC','RAL'],0x80,0x01,1),(['MVI A, 001H','STC','RAR'],0x01,0x80,1)]:
  for instr in ops:a('    '+instr)
  a('    JNC BAD_CPU' if cy else '    JC BAD_CPU')
  a('    CPI '+hx(expected));a('    JNZ BAD_CPU')
 a('    MVI A, 055H');a('    CMA');a('    CPI 0AAH');a('    JNZ BAD_CPU')
 a('    STC');a('    CMC');a('    JC BAD_CPU')
 a('    STC');a('    JNC BAD_CPU')
 a('')
 a('; ===== Секция 7. Пары регистров, 16-битная арифметика ==')
 for name,hi,lo in [('B',0x12,0x34),('D',0x56,0x78),('H',0x9A,0xBC)]:
  val=(hi<<8)|lo
  a(f'    ; LXI / INX / DCX {name}')
  a('    LXI '+name+', '+hx(val,4))
  a('    INX '+name)
  a('    DCX '+name)
  a('    MOV A,'+hi_reg(name));a('    CPI '+hx(hi));a('    JNZ BAD_CPU')
  a('    MOV A,'+lo_reg(name));a('    CPI '+hx(lo));a('    JNZ BAD_CPU')
 a('    LXI SP, 05A3CH')
 a('    INX SP');a('    DCX SP')
 a('    LXI H, 0000H');a('    DAD SP')
 a('    MOV A,H');a('    CPI 05AH');a('    JNZ BAD_CPU')
 a('    MOV A,L');a('    CPI 03CH');a('    JNZ BAD_CPU')
 a('    LXI H, 0FFFFH')
 a('    LXI B, 0001H')
 a('    DAD B')
 a('    JNC BAD_CPU')
 a('    MOV A,H');a('    ORA L');a('    JNZ BAD_CPU')
 a('    LXI H, 01000H')
 a('    LXI D, 01234H')
 a('    DAD D')
 a('    MOV A,H');a('    CPI 022H');a('    JNZ BAD_CPU')
 a('    MOV A,L');a('    CPI 034H');a('    JNZ BAD_CPU')
 a('    LXI H, 01234H');a('    DAD H')
 a('    MOV A,H');a('    CPI 024H');a('    JNZ BAD_CPU')
 a('    MOV A,L');a('    CPI 068H');a('    JNZ BAD_CPU')
 a('    ; XCHG and SPHL (neither writes memory)')
 a('    LXI H, 01234H')
 a('    LXI D, 05678H')
 a('    XCHG')
 a('    MOV A,H');a('    CPI 056H');a('    JNZ BAD_CPU')
 a('    MOV A,E');a('    CPI 034H');a('    JNZ BAD_CPU')
 a('    SPHL')
 a('    LXI H, 0000H')
 a('    DAD SP')
 a('    MOV A,H');a('    CPI 056H');a('    JNZ BAD_CPU')
 a('    MOV A,L');a('    CPI 078H');a('    JNZ BAD_CPU')
 a('')
 a('; ===== Секция 8. Прямое и косвенное чтение из ПЗУ ====')
 a('    LXI B, 01000H');a('    LDAX B');a('    CPI 01H');a('    JNZ BAD_CPU')
 a('    LXI D, 01001H');a('    LDAX D');a('    CPI 02H');a('    JNZ BAD_CPU')
 a('    LDA 01002H');a('    CPI 04H');a('    JNZ BAD_CPU')
 a('    LHLD 01018H    ; low=22h, high=E4h')
 a('    MOV A,L');a('    CPI 022H');a('    JNZ BAD_CPU')
 a('    MOV A,H');a('    CPI 0E4H');a('    JNZ BAD_CPU')
 a('')
 a('; ===== Секция 9. POP/RET: читаем слова стека из ПЗУ ==')
 a('; POP and RET only READ the stack: safe with SP pointing to ROM.')
 a('; PUSH,CALL,RST,XTHL are NOT safe without writable memory.')
 a('    LXI SP, 01020H')
 a('    POP B');a('    MOV A,B');a('    CPI 012H');a('    JNZ BAD_CPU')
 a('    MOV A,C');a('    CPI 034H');a('    JNZ BAD_CPU')
 a('    POP D');a('    MOV A,D');a('    CPI 056H');a('    JNZ BAD_CPU')
 a('    MOV A,E');a('    CPI 078H');a('    JNZ BAD_CPU')
 a('    POP H');a('    MOV A,H');a('    CPI 09AH');a('    JNZ BAD_CPU')
 a('    MOV A,L');a('    CPI 0BCH');a('    JNZ BAD_CPU')
 a('    POP PSW')
 a('    JNC BAD_CPU    ; PSW has carry')
 a('    JNZ BAD_CPU    ; PSW has zero')
 a('    JPO BAD_CPU    ; PSW has even parity')
 a('    JM BAD_CPU     ; PSW sign clear')
 a('    CPI 0A6H');a('    JNZ BAD_CPU')
 a('    LXI SP, 01040H')
 a('    RET            ; pops address of TARGET_RET from ROM')
 a('    JMP BAD_CPU')
 a('TARGET_RET:')
 a('    NOP')
 for op,code,setup in [
  ('RNZ','NZ',['MVI A,01H','ORA A']),
  ('RZ','Z',['MVI A,00H','ORA A']),
  ('RNC','NC',['MVI A,01H','ORA A']),
  ('RC','C',['STC']),
  ('RPO','PO',['MVI A,01H','ORA A']),
  ('RPE','PE',['MVI A,00H','ORA A']),
  ('RP','P',['MVI A,00H','ORA A']),
  ('RM','M',['MVI A,080H','ORA A'])]:
  a('    ; conditional RET '+code+' reads its target from ROM')
  a('    LXI SP, RET_PTR_'+code)
  for x in setup:a('    '+x)
  a('    '+op)
  a('    JMP BAD_CPU')
  a('RET_TARGET_'+code+':')
  a('    NOP')
 a('')
 a('; ===== Секция 10. Переходы JMP/PCHL и условный CALL ====')
 # all conditions should be tested via opposite conditions in flags
 for cond,set_seq in [
  ('NZ',['MVI A,01H','ORA A']),('Z',['MVI A,00H','ORA A']),
  ('NC',['MVI A,01H','ORA A']),('C',['STC']),
  ('PO',['MVI A,01H','ORA A']),('PE',['MVI A,00H','ORA A']),
  ('P',['MVI A,00H','ORA A']),('M',['MVI A,080H','ORA A'])]:
  a(f'    ; Check J{cond} taken path')
  for x in set_seq:a('    '+x)
  a('    J'+cond+' J_TARGET_'+cond)
  a('    JMP BAD_CPU')
  a('J_TARGET_'+cond+':')
  a('    NOP')
 # NOT TAKEN calls: opposite condition
 for cond,set_seq in [
  ('NZ',['MVI A,00H','ORA A']),('Z',['MVI A,01H','ORA A']),
  ('NC',['STC']),('C',['MVI A,01H','ORA A']),
  ('PO',['MVI A,00H','ORA A']),('PE',['MVI A,01H','ORA A']),
  ('P',['MVI A,080H','ORA A']),('M',['MVI A,00H','ORA A'])]:
  a(f'    ; C{cond}: only not-taken path is safe without RAM')
  for x in set_seq:a('    '+x)
  a('    C'+cond+' BAD_CPU')
  a('    NOP')
 a('    LXI H, TARGET_PCHL')
 a('    PCHL          ; jumps via HL, uses no stack')
 a('    JMP BAD_CPU')
 a('TARGET_PCHL:')
 a('    DI')
 a('    JMP SUCCESS')
 a('')
 a('; ===== Секция 11. Звуковая сигнализация через INTE ====')
 a('; Success: three SHORT pips (~80ms each) and HLT.')
 a('; Failure checksum: one LONG beep (~0.21s).')
 a('; Failure address: two LONG beeps.')
 a('; Failure ROM data: three LONG beeps.')
 a('; Failure CPU opcode test: four LONG beeps.')
 a('; All error paths HALT; RESET is needed for another test.')
 # Shared ROM-only sound loop. D=number of beeps, E=tone length, H=pause high byte.
 # No stack, no RAM. C is overwritten by tone, B/C/A by the pause loop.
 a('SUCCESS:')
 a('    MVI D, 03H        ; three short beeps')
 a('    MVI E, 05AH       ; beep length 90 cycles')
 a('    MVI H, 041H       ; 4100h pause')
 a('    JMP REPORT_BEEP')
 for label,n in [('BAD_CHECKSUM',1),('BAD_ADDRESS',2),('BAD_DATA',3),('BAD_CPU',4)]:
  a(label+':')
  a('    MVI D, '+hx(n))
  a('    JMP REPORT_ERROR')
 a('REPORT_ERROR:')
 a('    DI')
 a('    MVI E, 0E6H      ; beep length 230 cycles')
 a('    MVI H, 04AH       ; 4A00h pause')
 a('REPORT_BEEP:')
 a('    MOV B,E')
 a('REPORT_CYCLE:')
 a('    EI')
 a('    MVI C, 105')
 a('REPORT_HIGH:')
 a('    DCR C')
 a('    JNZ REPORT_HIGH')
 a('    DI')
 a('    MVI C, 105')
 a('REPORT_LOW:')
 a('    DCR C')
 a('    JNZ REPORT_LOW')
 a('    DCR B')
 a('    JNZ REPORT_CYCLE')
 a('    DI')
 a('    DCR D')
 a('    JZ DONE')
 a('    MOV B,H')
 a('    MVI C, 000H')
 a('REPORT_PAUSE:')
 a('    DCX B')
 a('    MOV A,B')
 a('    ORA C')
 a('    JNZ REPORT_PAUSE')
 a('    JMP REPORT_BEEP')
 a('DONE:')
 a('    DI             ; keep INTE low and INT disabled')
 a('    HLT            ; stop until RESET (or external intervention)')
 a('END')
 return '\n'.join(q)+'\n'

def hi_reg(r):return {'B':'B','D':'D','H':'H'}[r]
def lo_reg(r):return {'B':'C','D':'E','H':'L'}[r]

def segments_source(body):
 out=[]
 out.append('ORG 0000H\nJMP START\n')
 out.append('ORG 01000H\nDB '+', '.join(hx(1<<i) for i in range(8))+'\n')
 out.append('ORG 01010H\nDB '+', '.join(hx((~(1<<i))&255) for i in range(8))+'\n')
 out.append('ORG 01018H\nDB 022H, 0E4H\n')
 out.append('ORG 01020H\nDB 034H, 012H, 078H, 056H, 0BCH, 09AH, 047H, 0A6H\n')
 out.append('ORG 01030H\n')
 for v in ['NZ','Z','NC','C','PO','PE','P','M']:
  out.append('RET_PTR_'+v+': DW RET_TARGET_'+v+'\n')
 out.append('ORG 01040H\nDW TARGET_RET\n')
 out.append('ORG 01C00H\n; ===== FAST CRC16 ROM LOOKUP: HIGH 256 BYTES =====\n')
 for n in range(0,256,16):
  out.append('DB '+', '.join(hx((crc16(bytes([i]))>>8)&255) for i in range(n,n+16))+'\n')
 out.append('ORG 01D00H\n; ===== FAST CRC16 ROM LOOKUP: LOW 256 BYTES =====\n')
 for n in range(0,256,16):
  out.append('DB '+', '.join(hx(crc16(bytes([i]))&255) for i in range(n,n+16))+'\n')
 out.append(body)
 return '\n'.join(out)

def generate_sources():
 intro='''; ДИАГНОСТИКА INTEL 8080, ПЗУ 64 КБ. ЛИНИЯ A15 ПОДКЛЮЧЕНА К ПЗУ.
; При RESET выполняется код с 0000h: переход на 2100h, затем пик по INTE.
; Далее: CRC-16 (полином 002Dh) всего ПЗУ, проверка A0-A15 и D0-D7, тест команд 8080.
; При успехе 3 коротких сигнала и HLT, при ошибке 1-4 длинных и HLT.
; Без ОЗУ, без записей в память; INT (контакт 14) обязательно удерживать 0.
; ВАЖНО: типовой Intel 8080A не гарантированно работает на 3,5 МГц.
; Для сборки использовать build.py, либо самостоятельный FULL.asm.

'''
 return intro+segments_source(body_source())

def to_hex(buf):
 rows=[]
 for address in range(0,len(buf),16):
  data=buf[address:address+16];rec=bytes((len(data),(address>>8)&255,address&255,0))+data
  ch=(-sum(rec))&255
  rows.append(':'+rec.hex().upper()+f'{ch:02X}')
 rows.append(':00000001FF')
 return '\n'.join(rows)+'\n'

def disasm_safety(src,mem):
 asm=Assembler(src)
 rom,used=asm.assemble()
 assert rom[:CS_ADDR]==mem[:CS_ADDR] and rom[CS_ADDR+2:]==mem[CS_ADDR+2:]
 bad={'MOV M','STAX','STA','SHLD','MVI M','INR M','DCR M','PUSH','XTHL','RST','OUT','IN','CALL'}
 ops=[(loc,m,args) for loc,m,args,no in get_instructions(asm)]
 for loc,m,args in ops:
  if m=='MOV' and args[0].upper()=='M':raise AssertionError((m,args))
  if m=='MVI' and args[0].upper()=='M':raise AssertionError((m,args))
  if m in {'STAX','STA','SHLD','PUSH','XTHL','RST','OUT','IN','CALL'}:raise AssertionError((loc,m))
  if m in {'INR','DCR'} and args[0].upper()=='M':raise AssertionError((loc,m))
 return {'instruction_count':len(ops),'distinct_mnemonics':sorted(set(m for loc,m,a in ops)),'ends_with_DI_HLT':mem[asm.labels['DONE']:asm.labels['DONE']+2]==b'\xf3\x76','code_start':CODE_START,'code_end':max(loc+asm.size(m,a) for loc,m,a in ops if loc>=CODE_START),'labels':asm.labels}

def get_instructions(asm):
 loc=0
 for no,line in enumerate(asm.lines,1):
  m,args=asm.parse_line(line)
  if not m:continue
  if m=='LABEL':
   _,tail=args
   m,args=asm.parse_line(tail) if tail else ('',[])
   if not m:continue
  if m=='ORG':loc=asm.expr(args[0],asm.labels);continue
  if m=='END':break
  if m not in ('DB','DW'):
   yield loc,m,args,no
  loc+=asm.size(m,args)

def extended_full_source(rom, source, code_end, checksum):
 # Independently assembled, single-file 64 KiB listing. Fill all ORG gaps
 # with explicit DB lines; all sections of commented source remain visible.
 lines=source.splitlines()
 # Construct by parsing original source and emitting DB fillers immediately
 # before each ORG. This preserves labels and meaningful comments.
 out=[]; location=0
 assembler=Assembler(source)
 _,_=assembler.assemble()
 labels=assembler.labels
 def filler(begin,end):
  if end<=begin:return []
  ss=[]
  for i in range(begin,end,16):
   ss.append('    DB '+', '.join(hx(x) for x in rom[i:min(end,i+16)]))
  return ss
 # go by source original ORGs, track consumed bytes to fill segment gaps
 for raw in lines:
  m,args=assembler.parse_line(raw)
  if m=='LABEL':
   lbl,tail=args
   mm,aa=assembler.parse_line(tail) if tail else ('',[])
   if mm:
    m,args=mm,aa
   else:m,args='',[]
  if m=='ORG':
   goal=assembler.expr(args[0],labels)
   out.extend(filler(location,goal));location=goal
  elif m in ('DB','DW') or (m and m!='END'):
   location+=assembler.size(m,args)
  out.append(raw)
  if m=='END':break
 ends=[i for i,line in enumerate(out) if line.strip().upper()=='END']
 if ends:
  out[ends[0]:ends[0]]=filler(location,ROM_SIZE)
 else:out.extend(filler(location,ROM_SIZE))
 # Because source lacks an explicit ORG checksum region and main body has END,
 # put stored checksum by replacing bytes in unused filler region at FFF0..1
 # (filler method inserts actual bytes). checksum are still explicit bytes.
 return '\n'.join(out)+'\n'


def crc16(data):
 """Reference bitwise CRC-16, MSB-first, poly 002Dh, init=0."""
 crc=0
 for byte in data:
  crc ^= byte << 8
  for _ in range(8):
   carry=bool(crc&0x8000)
   crc=(crc<<1)&0xffff
   if carry: crc ^= 0x002d
 return crc


def make_crc_correction(source, offset):
 """Solve two correction bytes at an arbitrary position over GF(2).

 This differs from appending a conventional CRC: the correction bytes are
 before the final 14 ROM bytes, so their value is solved for ZERO residue.
 """
 assert source[offset:offset+2] == b'\x00\x00' or len(source)>=offset+2
 data=bytearray(source)
 data[offset:offset+2]=b'\x00\x00'
 baseline=crc16(data)
 columns=[]
 for bit in range(16):
  data[offset+(bit//8)] ^= 1<<(bit%8)
  columns.append(crc16(data)^baseline)
  data[offset+(bit//8)] ^= 1<<(bit%8)
 # Solve the 16-bit linear system: xor(columns[i] if bit_i else 0)=baseline
 rows=[]
 for k in range(16):
  coeff=sum(((col>>k)&1)<<i for i,col in enumerate(columns))
  rows.append(coeff|(((baseline>>k)&1)<<16))
 for k in range(16):
  pivot=next((i for i in range(k,16) if (rows[i]>>k)&1),None)
  if pivot is None: raise ValueError('CRC correction matrix is singular')
  rows[k],rows[pivot]=rows[pivot],rows[k]
  for i in range(16):
   if i!=k and ((rows[i]>>k)&1):rows[i]^=rows[k]
 result=sum(((rows[k]>>16)&1)<<k for k in range(16))
 data[offset]=result&255
 data[offset+1]=(result>>8)&255
 assert crc16(data)==0
 return result


def main():
 src=generate_sources()
 (ROOT/'Intel8080_ROM64_Diagnostic.asm').write_text(src,encoding='utf-8')
 asm=Assembler(src)
 rom, used=asm.assemble()
 assert len(rom)==0x10000
 assert asm.labels['DONE']<CS_ADDR
 assert CS_ADDR not in used and CS_ADDR+1 not in used
 # Avoid signature collisions at tested addresses. No checksum field overlap.
 for n in range(16):
  assert rom[0]!=rom[1<<n],(n,'walking1 collision')
  assert rom[0x7fff]!=rom[0x7fff^(1<<n)],(n,'walking0 collision')
 checksum=make_crc_correction(rom, CS_ADDR)
 rom[CS_ADDR]=checksum&255;rom[CS_ADDR+1]=checksum>>8
 assert crc16(rom)==0, f'CRC full ROM mismatch: {crc16(rom):04X}' 
 (ROOT/'Intel8080_ROM64_A15_CONNECTED.bin').write_bytes(rom)
 (ROOT/'Intel8080_ROM64_A15_CONNECTED.hex').write_text(to_hex(rom),encoding='ascii')
  # Need ensure full-source produces expected bytes: directly produce full
 # image with all 64k DB and source code sections, stored checksum inserted
 # in appropriate unused addresses via actual filler bytes.
 full=extended_full_source(rom,src,asm.labels['DONE']+2,checksum)
 (ROOT/'Intel8080_ROM64_FULL.asm').write_text(full,encoding='utf-8')
 checkasm=Assembler(full)
 reb,_=checkasm.assemble(fill=False)
 assert reb==rom,(sum(a!=b for a,b in zip(reb,rom)))
 # Hex roundtrip and checksums
 records=(ROOT/'Intel8080_ROM64_A15_CONNECTED.hex').read_text().splitlines(); decoded=bytearray()
 for record in records:
  assert record.startswith(':')
  raw=bytes.fromhex(record[1:]);assert sum(raw)%256==0
  if raw[3]==0:decoded.extend(raw[4:-1])
  elif raw[3]==1:break
 assert decoded==rom
 safety=disasm_safety(src,rom)
 report={
   'mode':'physical 64 KiB; CPU address A15 connected to ROM',
   'checksum_algorithm':'FAST TABLE CRC-16, poly 002Dh, init 0000h, non-reflected, XOR-out 0000h',
   'crc_table_high_address':'1C00-1CFF',
   'crc_table_low_address':'1D00-1DFF',
   'crc_loop_t_states_per_byte':83 if ROM_SIZE==0x8000 else 80,
   'crc16_correction_word_le':f'{checksum:04X}',
   'crc16_full_rom_residue':f'{crc16(rom):04X}',
   'crc16_correction_storage_address':'FFF0-FFF1',
   'address_lines_tested':'A0..A15',
   'data_lines_tested':'D0..D7',
   'physical_rom_bytes':len(rom),
   'rom_sha256':hashlib.sha256(rom).hexdigest(),
   'instruction_count_in_executable_section':safety['instruction_count'],
   'instruction_groups':safety['distinct_mnemonics'],
   'program_bytes':safety['code_end']-CODE_START,
   'code_end':f'{safety["code_end"]:04X}',
   'start':f'{asm.labels["START"]:04X}',
   'success_address':f'{asm.labels["SUCCESS"]:04X}',
   'error_addrs':{x:f'{asm.labels[x]:04X}' for x in ('BAD_CHECKSUM','BAD_ADDRESS','BAD_DATA','BAD_CPU')},
   'stage_addrs':{x:f'{asm.labels[x]:04X}' for x in ('ROM_CRC_BYTE','DATA_ONE_LOOP','TEST_REGISTER_MOV','TARGET_PCHL','SUCCESS')},
   'final_di_hlt':safety['ends_with_DI_HLT'],
   'ret_targets':{k:f'{v:04X}' for k,v in asm.labels.items() if k.startswith('RET_TARGET_')},
 }
 (ROOT/'build_report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
 print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

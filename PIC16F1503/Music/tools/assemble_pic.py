#!/usr/bin/env python3
"""Minimal reproducible enhanced-PIC16F1 assembler for the MicroMusic sources.

Encodings and 1/2-cycle semantics follow Microchip DS40001607D Table 27-3.
Supports only the instructions actually used by this PIC16F1503 project; it
fails on unfamiliar instructions. MPASM/gpasm-compatible syntax subset.

This tool is NOT an implementation of Microchip pic-as or a claim of vendor
certification: its output is verified by a separate PIC instruction emulator.
"""
import re, sys, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
MAIN=ROOT/'firmware'/'micromusic.asm'

def expand(path):
    lines=[]
    for number,raw in enumerate(path.read_text(encoding='utf8').splitlines(),1):
        s=raw.split(';',1)[0].strip()
        if not s: continue
        m=re.match(r'(?i)^INCLUDE\s+"([^"]+)"$',s)
        if m:lines+=expand(path.parent/m.group(1));continue
        lines.append((str(path.relative_to(ROOT)),number,s))
    return lines

def assemble():
    src=expand(MAIN);symbols={}; stmts=[]; pc=0
    for file,line,s in src:
        if re.match('(?i)^PROCESSOR\\b',s):continue
        if re.match('(?i)^END\\b',s):break
        m=re.fullmatch(r'(?i)([\w]+)\s+EQU\s+(0x[\da-f]+|\d+)',s)
        if m:
            name,expr=m.groups();symbols[name.upper()]=int(expr,0);continue
        while ':' in s:
            label,rest=s.split(':',1)
            if not re.fullmatch(r'[a-zA-Z_][\w]*',label.strip()):raise ValueError((file,line,s))
            if label.upper() in symbols:raise ValueError(f'duplicate label {label}')
            symbols[label.upper()]=pc;s=rest.strip()
            if not s:break
        if not s:continue
        m=re.fullmatch('(?i)ORG\\s+(0x[\\da-f]+|\\d+)',s)
        if m:pc=int(m.group(1),0);continue
        m=re.fullmatch('(?i)DW\\s+(.+)',s)
        if m:
            vals=m.group(1).split(',')
            for v in vals:stmts.append((pc,'DW',[v.strip()],file,line));pc+=1
            continue
        m=re.fullmatch(r'(?i)([A-Z][A-Z0-9]*)\s*(.*)',s)
        if not m:raise ValueError(f'{file}:{line} {s}')
        op,args=m.groups();sts=[x.strip() for x in args.split(',') if x.strip()]
        stmts.append((pc,op.upper(),sts,file,line));pc+=1
    if pc>2048:raise ValueError(f'Program too large: {pc}')
    words=[0x3fff]*2048;occupied={};listings=[];branches=[]
    def ev(ex):
        ex=ex.upper().replace(' ','')
        if ex in symbols:return symbols[ex]
        if '+' in ex:
            left,right=ex.split('+',1);return ev(left)+ev(right)
        if '-' in ex and not ex.startswith('-'):
            left,right=ex.split('-',1);return ev(left)-ev(right)
        if ex.startswith('LOW(') and ex.endswith(')'):return ev(ex[4:-1])&255
        if ex.startswith('HIGH(') and ex.endswith(')'):return (ev(ex[5:-1])>>8)&255
        try:return int(ex,0)
        except ValueError:raise ValueError(f'Unknown symbol {ex}')
    single={'NOP':0x0000,'RETURN':0x0008,'RETFIE':0x0009,'CLRW':0x0100,'BRW':0x000b,'CALLW':0x000a}
    fileop={'ADDWF':0x0700,'ADDWFC':0x3D00,'ANDWF':0x0500,'ASRF':0x3700,'LSLF':0x3500,
        'LSRF':0x3600,'CLRF':0x0180,'COMF':0x0900,'DECF':0x0300,'INCF':0x0a00,'IORWF':0x0400,
        'MOVF':0x0800,'MOVWF':0x0080,'RLF':0x0d00,'RRF':0x0c00,'SUBWF':0x0200,'SUBWFB':0x3b00,
        'SWAPF':0x0e00,'XORWF':0x0600,'DECFSZ':0x0b00,'INCFSZ':0x0f00}
    bitop={'BCF':0x1000,'BSF':0x1400,'BTFSC':0x1800,'BTFSS':0x1c00}
    litop={'MOVLW':0x3000,'ADDLW':0x3e00,'SUBLW':0x3c00,'ANDLW':0x3900,'IORLW':0x3800,'XORLW':0x3a00}
    for pc,op,a,file,line in stmts:
        if pc in occupied:raise ValueError(f'Overlapping ORG at word {pc:04X} ({file}:{line})')
        occupied[pc]=op
        if op=='DW':w=ev(a[0]); assert 0<=w<=0x3fff
        elif op in single:
            if a:raise ValueError(f'Unexpected operands: {op} {a}')
            w=single[op]
        elif op in fileop:
            f=ev(a[0]);assert 0<=f<128
            if op in ('CLRF','MOVWF'):
                if len(a)!=1:raise ValueError((pc,op,a))
                d=1
            else:d=1 if len(a)==1 or a[1].upper() in ('F','1') else 0
            w=fileop[op]|(d<<7)|f
        elif op in bitop:
            f,b=ev(a[0]),ev(a[1]);assert 0<=f<128 and 0<=b<8
            w=bitop[op]|(b<<7)|f
        elif op in litop:
            val=ev(a[0]);assert -128<=val<=255,(pc,op,val)
            w=litop[op]|(val&255)
        elif op=='MOVLB':
            val=ev(a[0]);assert 0<=val<=31
            w=0x20|val
        elif op in ('CALL','GOTO'):
            dest=ev(a[0]);assert 0<=dest<2048,(pc,op,dest)
            w=(0x2000 if op=='CALL' else 0x2800)|dest
        elif op=='BRA':
            dest=ev(a[0]);assert 0<=dest<2048
            delta=dest-pc-1
            if -256<=delta<=255:w=0x3200|(delta&0x1ff)
            else:w=0x2800|dest;branches.append((pc,dest,'GOTO relaxed'))
        elif op in ('MOVIW','MOVWI'):
            m=re.fullmatch(r'(-?\d+)\[FSR([01])\]',a[0].upper())
            if not m:raise ValueError(f'Incorrect MOVIW operand: {a} in {file}:{line}')
            k,n=map(int,m.groups()); assert -32<=k<=31
            w=(0x3F00 if op=='MOVIW' else 0x3F80)|(n<<6)|(k&63)
        else:raise ValueError(f'Unsupported PIC opcode {op} at {file}:{line}')
        assert 0<=w<=0x3fff,(pc,op,w)
        words[pc]=w
        listings.append((pc,w,op+(' '+', '.join(a) if a else ''),file,line))
    maxpc=max(occupied)+1
    bytesout=bytearray()
    for w in words[:maxpc]:bytesout.extend([w&255,w>>8])
    def record(addr,typ,values):
        b=[len(values),(addr>>8)&255,addr&255,typ,*values]
        return ':'+''.join('%02X'%(v&255) for v in b+[(-sum(b))&255])
    hexdump='\n'.join(record(i,0,bytesout[i:i+16]) for i in range(0,len(bytesout),16))+'\n'+record(0,1,[])+'\n'
    (ROOT/'firmware'/'micromusic.hex').write_text(hexdump)
    (ROOT/'firmware'/'micromusic.bin').write_bytes(bytesout)
    (ROOT/'firmware'/'micromusic.lst').write_text('PIC16F1503 / MicroMusic / 14-bit instruction words\n'+
        '\n'.join(f'{pc:04X}  {w:04X}  {s:<38} ; {file}:{line}' for pc,w,s,file,line in listings)+'\n')
    section={label.lower():val for label,val in symbols.items() if label.lower() in (
        'reset','pwm_irq','producer','render_voice','render_sample','render_drum','music_tick','read_event',
        'wave_table','note_table','chord_table','duration_table','playlist_table','score_table',
        'event_note_off','next_section','lead_rest','step_grid','event_chord','event_lead')}
    info={'cpu':'PIC16F1503','program_words':2048,'used_last_word':maxpc-1,'occupied_words':len(occupied),
        'code_words':len([p for p in occupied if p<0x600]),'data_words':len([p for p in occupied if p>=0x600]),
        'branches_relaxed_to_goto':branches,'sections':section,'machine_hex':'firmware/micromusic.hex'}
    (ROOT/'reports'/'assembly.json').write_text(json.dumps(info,indent=2)+'\n')
    print('Assembled:',maxpc,'address range words; occupied',len(occupied),'; code',info['code_words'],'data',info['data_words'])
    print('Labels:',section)
    return info
if __name__=='__main__':assemble()

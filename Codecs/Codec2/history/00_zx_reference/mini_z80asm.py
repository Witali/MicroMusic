#!/usr/bin/env python3
import os, re, sys, ast

REG8={'b':0,'c':1,'d':2,'e':3,'h':4,'l':5,'(hl)':6,'a':7}
REG16={'bc':0,'de':1,'hl':2,'sp':3}
PUSHPOP={'bc':0,'de':1,'hl':2,'af':3}
COND_JR={'nz':0x20,'z':0x28,'nc':0x30,'c':0x38}
COND_JP={'nz':0xC2,'z':0xCA,'nc':0xD2,'c':0xDA,'po':0xE2,'pe':0xEA,'p':0xF2,'m':0xFA}

class AsmError(Exception): pass

def strip_comment(line):
    return line.split(';',1)[0].strip()

def split_args(s):
    out=[]; cur=''; depth=0; quote=None
    for ch in s:
        if quote:
            cur+=ch
            if ch==quote: quote=None
        elif ch in "'\"": quote=ch; cur+=ch
        elif ch=='(':
            depth+=1; cur+=ch
        elif ch==')':
            depth-=1; cur+=ch
        elif ch==',' and depth==0:
            out.append(cur.strip()); cur=''
        else: cur+=ch
    if cur.strip() or s.strip(): out.append(cur.strip())
    return out

def safe_eval(expr, symbols, pc=0, allow_undef=False):
    expr=expr.strip()
    # '$' current address only when standalone or in arithmetic
    expr=re.sub(r'(?<![\w])\$(?![\w])', str(pc), expr)
    names=set(re.findall(r'\b[A-Za-z_][A-Za-z0-9_]*\b', expr))
    env={k:int(v) for k,v in symbols.items()}
    for n in names:
        if n not in env:
            if allow_undef: env[n]=0
            else: raise AsmError(f"undefined symbol {n} in {expr}")
    try:
        node=ast.parse(expr,mode='eval')
        allowed=(ast.Expression,ast.Constant,ast.Name,ast.Load,ast.BinOp,ast.UnaryOp,
                 ast.Add,ast.Sub,ast.Mult,ast.FloorDiv,ast.Div,ast.Mod,ast.LShift,ast.RShift,
                 ast.BitAnd,ast.BitOr,ast.BitXor,ast.USub,ast.UAdd,ast.Invert,ast.Pow)
        if not all(isinstance(x,allowed) for x in ast.walk(node)):
            raise AsmError(f"unsafe/unsupported expression {expr}")
        v=eval(compile(node,'<expr>','eval'),{'__builtins__':{}},env)
        return int(v)
    except AsmError: raise
    except Exception as e: raise AsmError(f"bad expression {expr}: {e}")

def is_mem_abs(op):
    return op.startswith('(') and op.endswith(')') and op.lower()!='(hl)'

def enc_inst(mn,args,pc,sym,allow_undef=False):
    m=mn.lower(); a=[x.lower() for x in args]
    ev=lambda x: safe_eval(x,sym,pc,allow_undef)
    def imm8(x): return [ev(x)&0xff]
    def imm16(x):
        v=ev(x)&0xffff; return [v&255,v>>8]
    def rel8(x):
        target=ev(x); d=target-(pc+2)
        if not allow_undef and not -128<=d<=127: raise AsmError(f"JR target out of range {x}: {d}")
        return [d&255]
    if m=='nop': return [0x00]
    if m=='halt': return [0x76]
    if m=='ei': return [0xfb]
    if m=='di': return [0xf3]
    if m=='ret': return [0xc9]
    if m=='rlca': return [0x07]
    if m=='rrca': return [0x0f]
    if m=='rla': return [0x17]
    if m=='rra': return [0x1f]
    if m=='cpl': return [0x2f]
    if m=='scf': return [0x37]
    if m=='ccf': return [0x3f]
    if m=='ex' and a==['de','hl']: return [0xeb]
    if m=='out' and a==['(c)','a']: return [0xed,0x79]
    if m=='call': return [0xcd]+imm16(args[0])
    if m=='jp':
        if len(a)==1: return [0xc3]+imm16(args[0])
        return [COND_JP[a[0]]]+imm16(args[1])
    if m=='jr':
        if len(a)==1: return [0x18]+rel8(args[0])
        return [COND_JR[a[0]]]+rel8(args[1])
    if m=='djnz': return [0x10]+rel8(args[0])
    if m=='push': return [0xc5+0x10*PUSHPOP[a[0]]]
    if m=='pop': return [0xc1+0x10*PUSHPOP[a[0]]]
    if m in ('sla','sra','srl'):
        base={'sla':0x20,'sra':0x28,'srl':0x38}[m]
        return [0xcb,base+REG8[a[0]]]
    if m=='inc':
        if a[0] in REG8: return [0x04+8*REG8[a[0]]]
        if a[0] in REG16: return [0x03+0x10*REG16[a[0]]]
    if m=='dec':
        if a[0] in REG8: return [0x05+8*REG8[a[0]]]
        if a[0] in REG16: return [0x0b+0x10*REG16[a[0]]]
    if m=='add':
        if len(a)==2 and a[0]=='a':
            if a[1] in REG8: return [0x80+REG8[a[1]]]
            return [0xc6]+imm8(args[1])
        if len(a)==2 and a[0]=='hl' and a[1] in REG16:
            return [0x09+0x10*REG16[a[1]]]
    if m in ('sub','and','or','xor','cp'):
        bases_reg={'sub':0x90,'and':0xa0,'xor':0xa8,'or':0xb0,'cp':0xb8}
        bases_imm={'sub':0xd6,'and':0xe6,'xor':0xee,'or':0xf6,'cp':0xfe}
        op=a[-1]
        if op in REG8: return [bases_reg[m]+REG8[op]]
        return [bases_imm[m]]+imm8(args[-1])
    if m=='ld':
        dst,src=a
        # register-register, including (HL)
        if dst in REG8 and src in REG8:
            return [0x40+8*REG8[dst]+REG8[src]]
        # 8-bit immediate
        if dst in REG8 and src not in REG8 and not is_mem_abs(src):
            return [0x06+8*REG8[dst]]+imm8(args[1])
        # 16-bit immediate
        if dst in REG16 and src not in REG16 and not is_mem_abs(src):
            return [0x01+0x10*REG16[dst]]+imm16(args[1])
        # direct BC/DE indirect special cases
        if dst=='a' and src=='(bc)': return [0x0a]
        if dst=='a' and src=='(de)': return [0x1a]
        if dst=='(bc)' and src=='a': return [0x02]
        if dst=='(de)' and src=='a': return [0x12]
        # absolute memory forms
        if is_mem_abs(dst):
            ex=args[0][1:-1]
            if src=='a': return [0x32]+imm16(ex)
            if src=='hl': return [0x22]+imm16(ex)
        if is_mem_abs(src):
            ex=args[1][1:-1]
            if dst=='a': return [0x3a]+imm16(ex)
            if dst=='hl': return [0x2a]+imm16(ex)
    raise AsmError(f"unsupported instruction: {mn} {' ,'.join(args)}")

def parse_source(path):
    lines=[]
    with open(path,encoding='utf-8') as f:
        for no,line in enumerate(f,1): lines.append((no,line.rstrip('\n')))
    return lines

def assemble(path,outpath,listpath=None):
    src=parse_source(path); base=os.path.dirname(os.path.abspath(path)); sym={}; pc=0; origin=None
    # pass 1
    for no,raw in src:
        line=strip_comment(raw)
        if not line: continue
        # label equ expr
        mm=re.match(r'^([A-Za-z_][\w]*)\s+equ\s+(.+)$',line,re.I)
        if mm:
            sym[mm.group(1)]=safe_eval(mm.group(2),sym,pc,allow_undef=False); continue
        if ':' in line:
            lab,rest=line.split(':',1); lab=lab.strip()
            if lab:
                if lab in sym: raise AsmError(f"line {no}: duplicate {lab}")
                sym[lab]=pc
            line=rest.strip()
            if not line: continue
        parts=line.split(None,1); op=parts[0].lower(); argstr=parts[1].strip() if len(parts)>1 else ''
        if op=='org':
            pc=safe_eval(argstr,sym,pc,False); origin=pc if origin is None else origin; continue
        if op=='db':
            n=0
            for x in split_args(argstr):
                x=x.strip()
                if (len(x)>=2 and x[0] in "'\"" and x[-1]==x[0]): n+=len(ast.literal_eval(x).encode('latin1'))
                else: n+=1
            pc+=n; continue
        if op=='dw': pc+=2*len(split_args(argstr)); continue
        if op=='incbin':
            fn=ast.literal_eval(argstr); pc+=os.path.getsize(os.path.join(base,fn)); continue
        args=split_args(argstr) if argstr else []
        try: pc+=len(enc_inst(op,args,pc,sym,allow_undef=True))
        except Exception as e: raise AsmError(f"line {no}: {raw}\n{e}")
    if origin is None: origin=0
    # pass 2
    pc=0; data=bytearray(); listing=[]
    for no,raw in src:
        line=strip_comment(raw)
        if not line: continue
        mm=re.match(r'^([A-Za-z_][\w]*)\s+equ\s+(.+)$',line,re.I)
        if mm: continue
        if ':' in line:
            _,rest=line.split(':',1); line=rest.strip()
            if not line: continue
        parts=line.split(None,1); op=parts[0].lower(); argstr=parts[1].strip() if len(parts)>1 else ''
        if op=='org':
            newpc=safe_eval(argstr,sym,pc,False)
            if not data: origin=newpc; pc=newpc
            elif newpc!=pc: raise AsmError(f"line {no}: discontiguous ORG unsupported")
            continue
        here=pc; bs=[]
        try:
            if op=='db':
                for x in split_args(argstr):
                    x=x.strip()
                    if len(x)>=2 and x[0] in "'\"" and x[-1]==x[0]: bs+=ast.literal_eval(x).encode('latin1')
                    else: bs.append(safe_eval(x,sym,pc,False)&255)
            elif op=='dw':
                for x in split_args(argstr):
                    v=safe_eval(x,sym,pc,False)&0xffff; bs += [v&255,v>>8]
            elif op=='incbin':
                fn=ast.literal_eval(argstr); bs=list(open(os.path.join(base,fn),'rb').read())
            else:
                args=split_args(argstr) if argstr else []
                bs=enc_inst(op,args,pc,sym,allow_undef=False)
        except Exception as e: raise AsmError(f"line {no}: {raw}\n{e}")
        data.extend(bs); pc+=len(bs)
        if bs:
            listing.append(f"{here:04X}  {' '.join(f'{x:02X}' for x in bs[:8]):<23} {raw}")
            if len(bs)>8: listing.append(f"      ... {len(bs)} bytes")
    open(outpath,'wb').write(data)
    if listpath:
        with open(listpath,'w',encoding='utf-8') as f:
            f.write(f"Origin: {origin:04X}\nSize: {len(data)} bytes\n\nSymbols:\n")
            for k,v in sorted(sym.items(),key=lambda kv:kv[1]): f.write(f"{k:24s} {v:04X}\n")
            f.write("\nListing:\n"+'\n'.join(listing)+'\n')
    return origin,bytes(data),sym

if __name__=='__main__':
    if len(sys.argv)<3:
        print('usage: mini_z80asm.py input.asm output.bin [listing]'); sys.exit(2)
    try:
        o,b,s=assemble(sys.argv[1],sys.argv[2],sys.argv[3] if len(sys.argv)>3 else None)
        print(f"assembled {len(b)} bytes at 0x{o:04X}")
    except AsmError as e:
        print('ASSEMBLY ERROR:',e,file=sys.stderr); sys.exit(1)

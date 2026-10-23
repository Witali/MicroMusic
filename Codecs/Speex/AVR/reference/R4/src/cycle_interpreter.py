#!/usr/bin/env python3
"""Execute LLVM 17 AVR textual assembly to count instruction cycles.

INDEPENDENT diagnostic: this is NOT avr-gcc/simavr.  It emulates the exact
AVR instructions in a clang -target avr -S listing, plus AVR ABI stubs for
libgcc __mulsi3 and __udivmodhi4 and libc memcpy/memset.
Used to produce representative dynamic timing profiles; not hard realtime
certification. Runtime flags and integer outputs are checked where possible.
"""
import sys, re, struct, collections, pathlib, time, argparse
P=pathlib.Path(__file__).resolve().parent
F=P
C,Z,N,V,S,H,T,I=(0,1,2,3,4,5,6,7)
class SimError(Exception):pass

def parse_source(path):
    rows=[]; sym={}; cur=''; mapping={}; block=[]; src_line=[]; current_line=0
    for raw in pathlib.Path(path).read_text().splitlines():
        raw=raw.split(';')[0].strip()
        if not raw:continue
        if raw.startswith('.type\tol_gain_table') or raw.startswith('.type ol_gain_table'):break
        if raw.endswith(':'):
            name=raw[:-1];sym[name]=len(rows)
            if name.startswith('.LBB') or name in ('speex_nb8_decode','speex_nb8_init','cos2_q14'):
                cur=name
            continue
        if raw.startswith('.loc'):
            m=re.search(r'\.loc\s+\d+\s+(\d+)',raw)
            if m:current_line=int(m.group(1))
            continue
        if raw[0]=='.':continue
        if raw.split()[0] in ('.set',):continue
        parts=raw.split(None,1);op=parts[0]
        args=tuple(s.strip() for s in parts[1].split(',')) if len(parts)==2 else ()
        rows.append((op,args))
        block.append(cur);src_line.append(current_line)
    return rows,sym,block,src_line

def tbl_bytes(src):
    text=pathlib.Path(src).read_text()
    tables={}
    for m in re.finditer(r'const\s+(int8_t|int16_t|int32_t)\s+(\w+)\[(\d+)\]\s*(?:\w+)?\s*=\s*\{(.*?)\};', text, flags=re.S):
        dtype,name,count,body=m.groups()
        nums=[int(i) for i in re.findall(r'[-+]?\d+',re.sub(r'/\*.*?\*/','',body,flags=re.S))]
        if len(nums)!=int(count):raise ValueError((name,count,len(nums)))
        width={'int8_t':1,'int16_t':2,'int32_t':4}[dtype]
        binary=b''.join((n%(256**width)).to_bytes(width,'little') for n in nums)
        tables[name]=binary
    return tables

class CPU:
    def __init__(self, rows, syms, blocks, src_line, symbols, flash, mul_cost=69, div_cost=0, mem_cost=10):
        self.rows=rows;self.labels=syms;self.blocks=blocks;self.src_line=src_line
        self.syms=symbols;self.flash=flash;self.mul_cost=mul_cost;self.div_cost=div_cost;self.mem_cost=mem_cost
        self.r=[0]*32;self.m=bytearray(0x10000);self.SP=0x8ff;self.sreg=0;self.pc=0
        self.stack=[];self.cycles=0;self.steps=0;self.hist=collections.Counter()
        self.calls=collections.Counter();self.by_block=collections.Counter();self.by_op=collections.Counter();self.by_line=collections.Counter();self.by_block_cycles=collections.Counter()
        self._lastblock='';self._max_depth=0
    def fl(self,b):return (self.sreg>>b)&1
    def flags(self,changes):
        for b,t in changes.items():
            self.sreg=(self.sreg&~(1<<b)) | (int(bool(t))<<b)
    def nz(self, v, ov=0, z=None):
        n=(v>>7)&1;self.flags({N:n,V:ov,S:n^ov,Z:(v&255)==0 if z is None else z})
    def arithmetic(self,op,d,a,b,carry=0):
        if op=='add':
            ans=a+b+carry; res=ans&255
            c=(ans>>8)&1;h=((a&15)+(b&15)+carry)>15
            v=(~(a^b)&(a^res)&128)!=0
        else:
            res=(a-b-carry)&255
            c=(a<(b+carry));h=((a&15)<((b&15)+carry));v=((a^b)&(a^res)&128)!=0
        z=res==0
        if op in ('sbc','cpc') and (self._old_z_for_sbc is not None):z=z and self._old_z_for_sbc
        self.flags({C:c,H:h,V:v,N:(res>>7)&1,Z:z,S:((res>>7)&1)^int(v)})
        if op in ('adc','add','sub','sbc','subi','sbci','cp','cpc','cpi') and op not in ('cp','cpc','cpi'):
            self.r[d]=res
        return res
    _old_z_for_sbc=None
    def imm(self,a):
        a=a.strip()
        fm=re.fullmatch(r'(lo8|hi8)\((.*)\)',a)
        if fm:
            kind,expression=fm.groups()
            value=self.eval_expr(expression)
            return (value>>(0 if kind=='lo8' else 8))&255
        return int(a,0)&255
    def eval_expr(self,expr):
        expr=expr.strip()
        if expr.startswith('-(') and expr.endswith(')'):return -self.eval_expr(expr[2:-1])
        if expr.startswith('-'):return -self.eval_expr(expr[1:])
        ma=re.fullmatch(r'([a-zA-Z_][\w.]*)([+-]\d+)?',expr)
        if ma:
            return self.syms[ma.group(1)]+int(ma.group(2) or 0)
        return int(expr,0)
    def val(self,arg):
        if re.fullmatch(r'r\d+',arg):return self.r[int(arg[1:])]
        if arg=='__SREG__':return self.sreg
        return self.imm(arg)
    def pair(self,lo):return self.r[lo]|(self.r[lo+1]<<8)
    def setpair(self,lo,x):x&=65535;self.r[lo]=x&255;self.r[lo+1]=x>>8
    def dword(self,lo):return sum(self.r[lo+i]<<(8*i) for i in range(4))
    def setdword(self,lo,val):
        for i in range(4):self.r[lo+i]=(val>>(8*i))&255
    def addr(self,x):
        if x=='X':return self.pair(26)
        if x=='Y':return self.pair(28)
        if x=='Z':return self.pair(30)
        m=re.fullmatch(r'([XYZ])\+(\d+)',x)
        if m:return (self.addr(m.group(1))+int(m.group(2)))&65535
        raise SimError('Bad address '+x)
    def push(self,x):self.m[self.SP]=x&255;self.SP-=1;self._max_depth=max(self._max_depth,0x8ff-self.SP)
    def pop(self):self.SP+=1;return self.m[self.SP]
    def _external(self,name):
        self.calls[name]+=1
        if name=='__mulsi3':
            a=self.dword(22);b=self.dword(18)
            self.setdword(22,a*b)
            # `__mulsi3` clobbers r26:r27, r0:r1 but guarantees r1=0
            self.r[1]=0;self.cycles+=self.mul_cost
        elif name=='__udivmodhi4':
            a=self.pair(24);b=self.pair(22)
            if not b:raise SimError('zero division')
            self.setpair(22,a//b);self.setpair(24,a%b)
            # 16-bit division restoring loop: ~190 + one cycle per successful quotient bit
            self.cycles+=(self.div_cost if self.div_cost else 190+(a//b).bit_count())
        elif name=='memcpy':
            dst=self.pair(24);src=self.pair(22);n=self.pair(20)
            self.m[dst:dst+n]=self.m[src:src+n]
            self.cycles+=self.mem_cost*n+18
        elif name=='memset':
            dst=self.pair(24);v=self.r[22];n=self.pair(20)
            self.m[dst:dst+n]=bytes([v])*n
            self.cycles+=self.mem_cost*n+16
        else:raise SimError('Unknown external: '+name)
    def callfn(self,name,args):
        self.SP=0x8ff;self.sreg=0;self.r=[0]*32;self.stack=[];self.pc=self.labels[name]
        for lo,val,sz in args:
            for j in range(sz):self.r[lo+j]=(val>>(8*j))&255
        self.cycles=0;self.steps=0;self.hist.clear();self.by_block.clear();self.by_op.clear();self.calls.clear();self.by_line.clear();self.by_block_cycles.clear()
        self._max_depth=0
        while self.pc>=0:
            self.step()
            if self.steps>20_000_000:
                raise SimError('Step limit; likely bad flags or pointer. PC='+str(self.pc)+' block='+self.blocks[self.pc])
        return self.cycles
    def step(self):
        pc=self.pc;op,args=self.rows[pc];self.pc+=1;old_cycles=self.cycles
        base=1;branch=None;self.steps+=1;self.by_op[op]+=1
        block=self.blocks[pc];self.by_block[block]+=1
        a=args[0] if len(args)>=1 else None
        b=args[1] if len(args)>=2 else None
        d=int(a[1:]) if a and re.fullmatch(r'r\d+',a) else None
        val=self.val(b) if b and (re.fullmatch(r'r\d+',b) or b[0].isdigit() or b[0]=='-') else None
        if op=='mov':self.r[d]=self.r[int(b[1:])]
        elif op=='movw':self.setpair(d,self.pair(int(b[1:])))
        elif op=='ldi':self.r[d]=self.imm(b)
        elif op=='push':self.push(self.r[d]);base=2
        elif op=='pop':self.r[d]=self.pop();base=2
        elif op=='cli':self.flags({I:0})
        elif op=='sei':self.flags({I:1})
        elif op=='ret':
            base=4
            if not self.stack:self.pc=-1
            else:self.pc=self.stack.pop()
        elif op=='call':
            base=4
            if a in self.labels:self.stack.append(self.pc);self.pc=self.labels[a]
            else:self._external(a)
        elif op in ('rjmp','jmp'):
            self.pc=self.labels[a];base=2 if op=='rjmp' else 3
        elif op.startswith('br'):
            if op=='breq':branch=self.fl(Z)
            elif op=='brne':branch=not self.fl(Z)
            elif op=='brmi':branch=self.fl(N)
            elif op=='brpl':branch=not self.fl(N)
            elif op=='brlo':branch=self.fl(C)
            elif op=='brsh':branch=not self.fl(C)
            elif op=='brge':branch=not self.fl(S)
            elif op=='brlt':branch=self.fl(S)
            elif op=='brcc':branch=not self.fl(C)
            elif op=='brcs':branch=self.fl(C)
            elif op=='brvc':branch=not self.fl(V)
            elif op=='brvs':branch=self.fl(V)
            else:raise SimError('Unknown branch '+op)
            if branch:self.pc=self.labels[a];base=2
        elif op in ('ld','ldd','lpm'):
            postinc=(op=='ld' and b in ('X+','Y+','Z+'))
            addr=self.addr(b[:-1] if postinc else b)
            self.r[d]=(self.flash[addr] if op=='lpm' else self.m[addr])
            if postinc:self.setpair({'X':26,'Y':28,'Z':30}[b[0]],(addr+1)&65535)
            base=3 if op=='lpm' else 2
        elif op in ('st','std'):
            self.m[self.addr(a)]=self.r[int(b[1:])];base=2
        elif op=='in':
            adr=int(b)
            self.r[d]=self.SP&255 if adr==61 else self.SP>>8 if adr==62 else self.sreg if adr==63 else 0
        elif op=='out':
            adr=int(a);v=self.r[int(b[1:])]
            if adr==61:self.SP=(self.SP&0xff00)|v
            elif adr==62:self.SP=(self.SP&0xff)|(v<<8)
            elif adr==63:self.sreg=v
            if adr in (61,62):self._max_depth=max(self._max_depth,0x8ff-self.SP)
        elif op in ('add','adc','sub','sbc','subi','sbci','cp','cpc','cpi'):
            prev=self.fl(Z)
            self._old_z_for_sbc=prev if op in ('sbc','cpc','sbci') else None
            aa=self.r[d];bb= self.val(b) if op in ('subi','sbci','cpi') else self.r[int(b[1:])]
            carry=self.fl(C) if op in ('adc','sbc','sbci','cpc') else 0
            typ='add' if op in ('add','adc') else 'sub'
            rr=self.arithmetic('cpc' if op=='cpc' else 'sbc' if op in ('sbc','sbci') else op if op in ('cp','cpi') else typ,d,aa,bb,carry)
            if op in ('cp','cpc','cpi'):self.r[d]=aa
            else:self.r[d]=rr
            self._old_z_for_sbc=None
        elif op in ('andi','or','eor'):
            aa=self.r[d];bb=self.val(b)
            res=aa&bb if op=='andi' else aa|bb if op=='or' else aa^bb
            self.r[d]=res;self.nz(res)
        elif op in ('clr','tst','com','neg','inc','dec','lsl','rol','lsr','ror','asr','swap'):
            aa=self.r[d];c=self.fl(C)
            if op=='clr':res=0;self.r[d]=res;self.nz(0);self.flags({C:0})
            elif op=='tst':self.nz(aa)
            elif op=='com':res=(~aa)&255;self.r[d]=res;self.nz(res);self.flags({C:1})
            elif op=='neg':
                res=(-aa)&255;self.r[d]=res
                self.nz(res,int(aa==128));self.flags({C:int(aa!=0),H:int(bool((res|aa)&8))})
            elif op=='inc':
                res=(aa+1)&255;self.r[d]=res;self.nz(res,int(aa==127))
            elif op=='dec':
                res=(aa-1)&255;self.r[d]=res;self.nz(res,int(aa==128))
            elif op=='lsl':self.arithmetic('add',d,aa,aa,0)
            elif op=='rol':self.arithmetic('add',d,aa,aa,c)
            elif op in ('lsr','ror','asr'):
                nc=aa&1;res=((aa>>1)|(c<<7)) if op=='ror' else ((aa>>1)|(aa&128)) if op=='asr' else aa>>1
                self.r[d]=res;n=(res>>7)&1;vv=n^nc
                self.flags({C:nc,N:n,V:vv,S:n^vv,Z:int(res==0)})
            elif op=='swap':self.r[d]=((aa>>4)|((aa&15)<<4))
        elif op in ('adiw','sbiw'):
            lo=d;aa=self.pair(lo);imm=int(b);v=(aa+imm if op=='adiw' else aa-imm)&65535
            self.setpair(lo,v);n=(v>>15)&1
            if op=='adiw':vv=int((aa&0x8000)==0 and n==1);cc=int(bool(aa&0x8000) and n==0)
            else:vv=int(bool(aa&0x8000) and n==0);cc=int((aa&0x8000)==0 and n==1)
            self.flags({V:vv,N:n,S:n^vv,C:cc,Z:int(v==0)})
            base=2
        elif op in ('mul','muls','mulsu'):
            aa=self.r[d];bb=self.r[int(b[1:])]
            if op in ('muls','mulsu'):aa=aa-256 if aa&128 else aa
            if op=='muls':bb=bb-256 if bb&128 else bb
            v=(aa*bb)&65535;self.r[0]=v&255;self.r[1]=(v>>8)&255
            self.flags({Z:int(v==0),C:(v>>15)&1});base=2
        else:raise SimError('Unimplemented '+str((op,args,block)))
        self.cycles+=base
        self.by_line[self.src_line[pc]]+=self.cycles-old_cycles
        self.by_block_cycles[block]+=self.cycles-old_cycles
        # no need to track SP in synthetic external stubs

def run_one(asm, stream, nframes, cost_mul=69, cost_div=0, cost_mem=10):
    rows,labels,blocks,src_line=parse_source(asm)
    flash=bytearray(0x10000); symbols={};pos=0x4000
    for file in ('speex_tables.c','cos_table.c','speex_nb8.c'):
        for k,data in tbl_bytes(F/file).items():
            symbols[k]=pos;flash[pos:pos+len(data)]=data;pos+=len(data)
            pos+=(2-pos%2)%2
    cpu=CPU(rows,labels,blocks,src_line,symbols,flash,cost_mul,cost_div,cost_mem)
    out=[];results=[];peak=0
    for frame in range(nframes):
        cpu.m[0x380:0x394]=stream[frame*20:(frame+1)*20]
        arg=[(24,0x100,2),(22,0x380,2),(20,0x400,2)]
        elapsed=cpu.callfn('speex_nb8_decode',arg)
        ret=cpu.pair(24)
        pcm=struct.unpack('<160h',cpu.m[0x400:0x400+320])
        out+=pcm
        if ret!=0:raise SimError(f'Return {ret} frame {frame} pc={cpu.pc} last block={blocks[max(0,cpu.pc)]}')
        peak=max(peak,cpu._max_depth)
        results.append(dict(cycles=elapsed, steps=cpu.steps, calls=dict(cpu.calls), by_block=dict(cpu.by_block_cycles), by_line=dict(cpu.by_line), max_stack=cpu._max_depth))
        if frame%5==0:print('frame',frame,'cycles',elapsed,'steps',cpu.steps,'calls',dict(cpu.calls),'stack depth',peak,flush=True)
    return results,out,peak

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--asm',default=str(P/'speex_nb8_optimized.s'));p.add_argument('--stream',default=str(F/'sample_mode3_8kbps.spxraw'));p.add_argument('--frames',type=int,default=5);p.add_argument('--outprefix',default='run');p.add_argument('--mul-cycles',type=int,default=69);p.add_argument('--div-cycles',type=int,default=0);args=p.parse_args()
    stream=pathlib.Path(args.stream).read_bytes();n=min(args.frames,len(stream)//20)
    t=time.monotonic();results,out,peak=run_one(args.asm,stream,n,args.mul_cycles,args.div_cycles)
    print('frames',n,'elapsed',round(time.monotonic()-t,2),'s','cycles',list(r['cycles'] for r in results))
    print('avg',sum(x['cycles'] for x in results)/n,'min',min(x['cycles'] for x in results),'max',max(x['cycles'] for x in results),'max_stack',peak)
    import json
    (P/(args.outprefix+'_detail.json')).write_text(json.dumps(results,indent=2))
    z=collections.Counter()
    for r in results:z.update(r['by_line'])
    print('TOP CODE LINES:',z.most_common(25));print('TOP BLOCKS:',sorted(((sum(r['by_block'].get(k,0) for r in results),k) for k in {p for r in results for p in r['by_block']}),reverse=True)[:20])
    print('first_pcm',out[:32]);(P/(args.outprefix+'_sim_pcm.raw')).write_bytes(struct.pack('<%dh'%len(out),*out))

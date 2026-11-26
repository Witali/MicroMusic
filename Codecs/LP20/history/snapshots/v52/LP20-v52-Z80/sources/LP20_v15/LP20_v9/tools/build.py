#!/usr/bin/env python3
"""LPX20 ROM-only Z80 machine-code generator. No external assembler needed."""
import argparse,json,struct
from functools import lru_cache
from pathlib import Path
CPU=20_000_000
class Image:
 def __init__(s):s.b=bytearray();s.lines=['; LPX20 ROM-only Z80','    org $0000'];s.labels={};s.fix=[];s.n=0
 @property
 def pc(s):return len(s.b)
 def lab(s,l):assert l not in s.labels;s.labels[l]=s.pc;s.lines.append(l+':')
 def op(s,t,*b):s.lines.append('    '+t);s.b.extend(b)
 def jp(s,l,c=''):
  s.lines.append('    jp '+(c+',' if c else '')+l);s.b.append({'':0xc3,'z':0xca,'nz':0xc2}[c]);s.fix.append((s.pc,l));s.b.extend(b'\0\0')
 def jr(s,l,c=''):
  s.lines.append('    jr '+(c+',' if c else '')+l);s.b.append({'':0x18,'z':0x28,'nz':0x20}[c]);s.fix.append((s.pc,l,True));s.b.append(0)
 def name(s,t):s.n+=1;return f'{t}_{s.n}'
 def data(s,b):
  for i in range(0,len(b),16):s.lines.append('    db '+','.join(f'${v:02x}' for v in b[i:i+16]))
  s.b.extend(b)
 def align(s):s.data(bytes(-s.pc%256))
 def finish(s):
  for fix in s.fix:
   p,l=fix[:2]
   if len(fix)==3:
    d=s.labels[l]-p-1;assert -128<=d<=127;s.b[p]=d&255
   else:s.b[p:p+2]=s.labels[l].to_bytes(2,'little')
  return bytes(s.b)
def pad_bytes(k):
 return {6:1,4:1,7:2,9:2,10:3,12:2}.get(k,6)
@lru_cache(None)
def pad(t,stack=True):
 if t==0:return ()
 if t<0:return None
 opts=[]
 candidates=[6,4,7,9,10,12] if stack else [12,4,7,9,10]
 candidates += [13*n+9 for n in range(1,19) if 13*n+9<=t]
 for k in candidates:
  p=pad(t-k,stack)
  if p is not None:opts.append((sum(pad_bytes(x) for x in p)+pad_bytes(k),(k,)+p))
 return min(opts)[1] if opts else None

def widths_for(period,levels):
 assert levels%2==1 and period%2==0
 m=levels//2;span=period*3//10
 return tuple(period//2+round((i-m)*span/m) for i in range(levels))
def quant(y,levels):
 m=levels//2;return max(0,min(2*m,m+(int(y)*m+64)//128))
def actions(order,map_page=1,lo_page=2,fast=False):
 # group boundaries always use main register set. AF' scratch, DE/IX/IY/DE' history.
 a=[(19,'check',())]+([(15,'peek',()),(38,'reload',()),(23,'gate',()),(34,'advance_fast',())] if fast else [(46,'boundary',()),(52,'advance',())])+[(27,'read',()),(4,'ld l,a',(0x6f,)),(7,f'ld h,${map_page:02x}',(0x26,map_page)),(7,'ld h,(hl)',(0x66,)),(4,"ex af,af'",(8,))]
 for i in range(order):
  if i<2:a.append((4,'ld l,'+['e','d'][i],([0x6b,0x6a][i],)))
  elif i<6:a.append((20,'ixread'+str(i),()))
  elif i<8:a.append((24,'altread'+str(i),()))
  else:
   a.extend([(4,"ex af,af'",(8,)),(4,'ld a,h',(0x7c,)),(10,'ld hl,0',(0x21,0,0)),(11,'add hl,sp',(0x39,))])
   if i==9:a.append((4,'ld l,h',(0x6c,)))
   a.extend([(4,'ld h,a',(0x67,)),(4,"ex af,af'",(8,))])
  a.append((7,'add a,(hl)',(0x86,)))
  if i+1<order:a.append((4,'inc h',(0x24,)))
 if order==10:
  a.extend([(4,"ex af,af'",(8,)),(10,'ld hl,0',(0x21,0,0)),(11,'add hl,sp',(0x39,)),(4,'ld h,l',(0x65,)),(12,'read_h8',()),(4,'ld l,a',(0x6f,)),(6,'ld sp,hl',(0xf9,)),(4,"ex af,af'",(8,))])
 if order>=8:a.append((32,'shiftalt',()))
 if order>=6:a.extend([(8,'ld iyh,iyl',(0xfd,0x65)),(24,'shiftcross',())])
 if order>=4:a.extend([(8,'ld ixh,ixl',(0xdd,0x65)),(8,'ld ixl,d',(0xdd,0x6a))])
 a.extend([(4,'ld d,e',(0x53,)),(4,'ld e,a',(0x5f,)),(4,'ld l,a',(0x6f,)),(7,f'ld h,${lo_page:02x}',(0x26,lo_page)),(7,'ld a,(hl)',(0x7e,)),(4,'inc h',(0x24,)),(7,'ld h,(hl)',(0x66,)),(4,'ld l,a',(0x6f,)),(4,'jp (hl)',(0xe9,))])
 return a

def schedule(a,period,pulses,width,stack=True):
 slots=(width-12,period-width-12)*pulses;ts=[0]
 for t,_,_ in a:ts.append(ts[-1]+t)
 @lru_cache(None)
 def rec(k,i):
  if k==len(slots):return () if i==len(a) else None
  if ts[-1]-ts[i]>sum(slots[k:]):return None
  js=[len(a)] if k==len(slots)-1 else range(len(a)-1,i-1,-1)
  for j in js:
   if j<i:continue
   p=pad(slots[k]-(ts[j]-ts[i]),stack)
   if p is None:continue
   r=rec(k+1,j)
   if r is not None:return ((i,j,p),)+r
  return None
 return rec(0,0)

def emit_pad(im,p,high):
 for t in p:
  if t==6:im.op('inc sp',0x33)
  elif t==4:im.op('nop',0)
  elif t==12:im.op('jr $+2',0x18,0)
  elif t==9:im.op('ld r,a',0xed,0x4f)
  elif t==7:im.op(f'ld b,${high:02x}',6,high)
  elif t==10:l=im.name('delay');im.jp(l);im.lab(l)
  else:
   n=(t-9)//13;assert t==13*n+9 and 1<=n<=255
   im.op(f'ld b,${n:02x}',6,n);im.op('djnz $',0x10,0xfe);im.op(f'ld b,${high:02x}',6,high)

def emit(im,o,book,end,high,stack=True):
 _,k,c=o;e=im.op
 if c:e(k,*c);return
 if k=='check':e('exx',0xd9);e('ld a,h',0x7c);e(f'cp ${end:02x}',0xfe,end);e('exx',0xd9)
 elif k=='peek':e('exx',0xd9);e('ld a,(bc)',0x0a);e('exx',0xd9)
 elif k=='reload':
  norm=im.name('normal');join=im.name('join');e('exx',0xd9);im.jr(norm,'nz');e('ld l,a',0x6f);e(f'ld h,${book:02x}',0x26,book);im.jr(join);im.lab(norm)
  e('nop',0);e('nop',0);l=im.name('delay');im.jp(l);im.lab(l);im.lab(join);e('exx',0xd9)
 elif k=='gate':
  norm=im.name('normal');join=im.name('join');im.jr(norm,'nz');e('or a',0xb7);im.jr(join);im.lab(norm);e('xor a',0xaf);e(f'ld b,${high:02x}',6,high);im.lab(join)
 elif k=='advance_fast':
  norm=im.name('normal');join=im.name('join');e('exx',0xd9);im.jp(norm,'z');e('inc bc',3);im.jp(join);im.lab(norm)
  for _ in range(4):e('nop',0)
  im.lab(join);e('exx',0xd9)
 elif k=='boundary':
  norm=im.name('normal');join=im.name('join')
  e('exx',0xd9);im.jp(norm,'nz');e('ld a,(bc)',0x0a);e('ld l,a',0x6f);e(f'ld h,${book:02x}',0x26,book);im.jp(join)
  im.lab(norm)
  if stack:
   for _ in range(3):e('inc sp',0x33)
  else:
   e('nop',0);e('nop',0);l=im.name('delay');im.jp(l);im.lab(l)
  im.jp(join);im.lab(join);e('exx',0xd9)
 elif k=='advance':
  norm=im.name('normal');zero=im.name('zero');join=im.name('join')
  if stack:
   e('exx',0xd9);im.jp(norm,'nz');e('ld a,l',0x7d);e('or a',0xb7);im.jp(zero,'z');e('inc bc',3);im.jp(join);im.lab(zero);e('inc sp',0x33);im.jp(join)
   im.lab(norm)
   for _ in range(4):e('inc sp',0x33)
   im.jp(join);im.lab(join);e('exx',0xd9)
  else:
   e('exx',0xd9);im.jp(norm,'z');e('jr $+2',0x18,0);e('jr $+2',0x18,0);im.jp(join)
   im.lab(norm);e('ld a,l',0x7d);e('or a',0xb7);im.jp(zero,'z');e('inc bc',3);im.jp(join);im.lab(zero)
   for _ in range(4):e('nop',0)
   im.lab(join);e('exx',0xd9)
 elif k=='read_h8':e('exx',0xd9);e('ld a,d',0x7a);e('exx',0xd9)
 elif k=='read':e('exx',0xd9);e('ld a,(hl)',0x7e);e('inc h',0x24);e("ex af,af'",8);e('ld a,l',0x7d);e('exx',0xd9)
 elif k.startswith('ixread'):
  i=int(k[-1]);pref=0xdd if i<4 else 0xfd;reg='ix' if i<4 else 'iy';part='l' if i%2==0 else 'h';e("ex af,af'",8);e('ld a,'+reg+part,pref,0x7d if part=='l' else 0x7c);e('ld l,a',0x6f);e("ex af,af'",8)
 elif k.startswith('altread'):
  i=int(k[-1]);e("ex af,af'",8);e('exx',0xd9);e('ld a,'+('e' if i==6 else 'd'),0x7b if i==6 else 0x7a);e('exx',0xd9);e('ld l,a',0x6f);e("ex af,af'",8)
 elif k=='shiftalt':e("ex af,af'",8);e('ld a,iyh',0xfd,0x7c);e('exx',0xd9);e('ld d,e',0x53);e('ld e,a',0x5f);e('exx',0xd9);e("ex af,af'",8)
 elif k=='shiftcross':e("ex af,af'",8);e('ld a,ixh',0xdd,0x7c);e('ld iyl,a',0xfd,0x6f);e("ex af,af'",8)
 else:raise ValueError(k)

def make(tables,bookdata,bankmap,stream,order,block,banks,period,pulses,levels,port=0,high=16,romsize=65536):
 assert len(tables)==banks*order*256 and len(bookdata)==block*256 and len(bankmap)==256 and max(bankmap)<banks and 0 not in stream
 assert order in (4,6,8,10) and port!=high
 tab_page=4;book_page=tab_page+order*banks;end=book_page+block;assert end<256
 a=actions(order,fast=period<160);widths=widths_for(period,levels);ss=[schedule(a,period,pulses,w,order<10) for w in widths]
 if any(s is None for s in ss):raise ValueError(f'{sum(s is not None for s in ss)}/{levels} widths feasible')
 im=Image();im.lab('reset');im.op('di',0xf3);im.op('ld sp,0',0x31,0,0);im.op(f'ld bc,${high:02x}{port:02x}',1,port,high);im.op('ld de,0',0x11,0,0);im.op('ld ix,0',0xdd,0x21,0,0);im.op('ld iy,0',0xfd,0x21,0,0);im.op('exx',0xd9);im.op('ld de,0',0x11,0,0)
 sptr=im.pc+1;im.op('ld bc,stream',1,0,0);im.op(f'ld hl,${end:02x}00',0x21,0,end);im.op('exx',0xd9);im.jp(f'pwm_{levels//2}')
 im.align();im.lab('bank_map');im.data(bytes(tab_page+int(b)*order for b in bankmap));assert im.pc==512
 im.lab('dispatch_table');dp=im.pc;dl=len(im.lines);im.data(bytes(512));im.lab('coefficients');im.data(tables);assert im.pc==book_page*256;im.lab('codebook');im.data(bookdata);assert im.pc==end*256
 addrs=[]
 for l,(w,s) in enumerate(zip(widths,ss)):
  im.lab(f'pwm_{l}');addrs.append(im.pc)
  for k,(i,j,p) in enumerate(s):
   im.op('out (c),b' if k%2==0 else 'out (c),c',0xed,0x41 if k%2==0 else 0x49)
   for n in range(i,j):
    if a[n][1]=='jp (hl)':emit_pad(im,p,high)
    emit(im,a[n],book_page,end,high,order<10)
   if j==0 or a[j-1][1]!='jp (hl)':emit_pad(im,p,high)
 endcode=im.pc;im.lab('stream');im.b[sptr:sptr+2]=endcode.to_bytes(2,'little');im.data(stream+b'\0');dataend=im.pc
 if dataend>romsize:raise ValueError(f'ROM needs {dataend} bytes > {romsize}')
 vals=[addrs[quant(i if i<128 else i-256,levels)] for i in range(256)];dt=bytes([v&255 for v in vals]+[v>>8 for v in vals]);im.b[dp:dp+512]=dt
 im.lines[dl:dl+32]=['    db '+','.join(f'${v:02x}' for v in dt[i:i+16]) for i in range(0,512,16)]
 image=im.finish();assert len(image)==dataend
 meta=dict(cpu=CPU,period=period,pulses=pulses,fs=CPU/(period*pulses),carrier=CPU/period,levels=levels,widths=widths,order=order,block=block,banks=banks,port=port,high=high,code_bytes=endcode-end*256,header_tables=end*256,stream_address=endcode,used=dataend,romsize=romsize,dispatch=addrs,decoder_t=sum(o[0] for o in a),padding_t=period*pulses-pulses*24-sum(o[0] for o in a),book_address=book_page*256,table_address=tab_page*256,bank_map_address=256)
 return image+bytes(romsize-dataend),'\n'.join(im.lines+[f'    defs {romsize}-$,0'])+'\n',meta

def unpack(path):
 r=Path(path).read_bytes();assert r[:4]==b'LP20';order,block,banks=r[4:7];period,pulses,levels,n=struct.unpack_from('<HBBI',r,7);p=15;size=order*banks*256;tb=r[p:p+size];p+=size;bm=r[p:p+256];p+=256;bk=r[p:p+block*256];p+=block*256;stream=r[p:];assert len(stream)*block==n;return tb,bk,bm,stream,order,block,banks,period,pulses,levels

def main():
 p=argparse.ArgumentParser();p.add_argument('payload');p.add_argument('--out',required=True);p.add_argument('--size',type=int,default=65536);p.add_argument('--port',type=lambda x:int(x,0),default=0);p.add_argument('--high',type=lambda x:int(x,0),default=16);a=p.parse_args();rom,asm,m=make(*unpack(a.payload),port=a.port,high=a.high,romsize=a.size);out=Path(a.out);out.with_suffix('.bin').write_bytes(rom);out.with_suffix('.asm').write_text(asm);out.with_suffix('.json').write_text(json.dumps(m,indent=2));print({k:v for k,v in m.items() if k not in ('dispatch','widths')})
if __name__=='__main__':main()

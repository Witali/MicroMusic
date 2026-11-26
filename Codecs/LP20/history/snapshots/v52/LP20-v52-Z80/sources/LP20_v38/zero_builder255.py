#!/usr/bin/env python3
'''ROM-threaded 10-bit LPC-6 decoder, exact v9/v10 arithmetic.
SP is a read-only program thread, DE accumulator. I stores bank and oldest
fraction nibble, AF' holds 8 newest fraction bits, IX/IY/DE' hold 6 high bytes.
All LPC products use compact nibble and paired fraction tables. No RAM writes.
'''
import sys,struct,json,os
from functools import lru_cache
from pathlib import Path
import numpy as np
HERE=Path(os.environ.get('LP20_V15',Path(__file__).resolve().parent.parent/'LP20_v15'))/'LP20_v15'
sys.path[:0]=[str(HERE),str(HERE.parent/'LP20_v9'),str(HERE.parent/'LP20_v9'/'tools')]
import opt_build as b
import build_fractional as old
from fractional import pattern,lut10
from precision_study import reconstruct
import common
import period_share as ps
import share_tails
import pattern_balance
# Pages 1..18: LPC products; 19..22: PWM map; 23..24: record pointers;
# 25..26: residual/bank pair lookup; page 27 onward: packed codebook.
# Page 0 also contains the low/high thread-address maps.
ALIAS_ZERO=False
ALIAS8=False
TAB=1; DP=19; NB=9; BOOK=26*256; PTR_LO=20; PTR_HI=22; PAIR_LO=24; PAIR_HI=25; THREAD_LO=0; THREAD_HI=0

def actions(correct=False):
 a=[]
 def op(t,s,*v):a.append((t,s,tuple(v)))
 def g(t,s):op(t,s)
 # Unmodified sentinel handling. advance_new replaces the old inc sp
 # dummy delay on end of stream, which is not safe with a read-only stack.
 g(111,'fetch_ctx_a');g(104,'fetch_ctx_b')
 op(4,'ld l,a',0x6f);op(7,f'ld h,{PAIR_LO}',0x26,PAIR_LO);op(7,'ld a,(hl)',0x7e);op(4,'inc h',0x24);op(7,'ld h,(hl)',0x66);op(4,'ld l,a',0x6f);op(7,'and 15',0xe6,15);op(4,'ld e,a',0x5f);op(9,'ld a,i',0xed,0x57);op(7,'and 240',0xe6,240);op(4,'or e',0xb3);op(9,'ld i,a',0xed,0x47);op(4,'ld a,l',0x7d);op(7,'and 192',0xe6,192);op(4,'ld e,a',0x5f);op(4,'ld d,h',0x54)
 def hist(i):
  if i<4:op(8,'ld a,'+('ix' if i<2 else 'iy')+('l' if i%2==0 else 'h'),0xdd if i<2 else 0xfd,0x7d if i%2==0 else 0x7c)
  else:g(12,'hist'+str(i))
 def rrc(n):
  for _ in range(n):op(4,'rrca',0x0f)
 def page(pg):
  op(9,'ld a,i',0xed,0x57);op(7,'and 15',0xe6,15)
  if pg:
   if ALIAS_ZERO:op(7,'or 8',0xf6,8)
   elif ALIAS8:
    op(7,'add a,8',0xc6,8)
   elif False:
    op(4,'ld h,a',0x67);op(7,'cp 9',0xfe,9);op(4,'sbc a,a',0x9f);op(7,'and 9',0xe6,9);op(4,'add a,h',0x84)
   else:op(7,f'add a,{NB}',0xc6,NB)
  op(4,'ld h,a',0x67)
 current_page=-1
 def lookup(offset,pg):
  nonlocal current_page
  if offset:op(7,f'add a,{offset}',0xc6,offset)
  op(4,'ld l,a',0x6f)
  if current_page!=pg:page(pg);current_page=pg
  # Add little-endian table word to DE without destroying H.
  # INC L and LD A,D preserve the carry from low-byte addition.
  op(7,'ld a,(hl)',0x7e);op(4,'add a,e',0x83);op(4,'ld e,a',0x5f);op(4,'inc l',0x2c);op(4,'ld a,d',0x7a);op(7,'adc a,(hl)',0x8e);op(4,'ld d,a',0x57)
 for i in range(6):
  pg=i//3;off=(i%3)*64
  hist(i);rrc(3);op(7,'and 30',0xe6,30);lookup(off,pg)
  hist(i);op(4,'add a,a',0x87);op(7,'and 30',0xe6,30);lookup(off+32,pg)
 for i in range(3):
  if i<2:g(16,'frac_a')
  else:op(9,'ld a,i',0xed,0x57)
  if i!=1:rrc(3)
  else:op(4,'add a,a',0x87)
  op(7,'and 30',0xe6,30);lookup([192,224,192][i],int(i==2))
 if ALIAS8:g(36,'zero_guard')
 op(4,'ex de,hl',0xeb)
 # Round once, same Q6 arithmetic as v10.
 op(4,'ld a,l',0x7d);op(7,'add a,32',0xc6,32);op(4,'ld l,a',0x6f);op(4,'ld a,h',0x7c);op(7,'adc a,0',0xce,0);op(4,'ld h,a',0x67);op(4,'ld a,l',0x7d);op(7,'and 192',0xe6,192);op(4,'ld l,a',0x6f)
 # Shift integer history and packed fractional state. H/L remain result.
 op(8,'ld a,iyh',0xfd,0x7c);g(16,'shiftalt');op(8,'ld iyh,iyl',0xfd,0x65);op(8,'ld a,ixh',0xdd,0x7c);op(8,'ld iyl,a',0xfd,0x6f);op(8,'ld ixh,ixl',0xdd,0x65);op(4,'ld a,h',0x7c);op(8,'ld ixl,a',0xdd,0x6f)
 op(9,'ld a,i',0xed,0x57);op(4,'ld d,a',0x57);rrc(2);op(7,'and 48',0xe6,48);op(4,'ld e,a',0x5f);op(4,'ld a,d',0x7a);op(7,'and 15',0xe6,15);op(4,'or e',0xb3);op(4,'ld e,a',0x5f);g(16,'frac_copy_d');rrc(2);op(7,'and 192',0xe6,192);op(4,'or e',0xb3);op(9,'ld i,a',0xed,0x47)
 op(4,"ex af,af'",8);rrc(2);op(7,'and 63',0xe6,63);op(4,'or l',0xb5);op(4,"ex af,af'",8)
 # Select next thread. No writes; RET pops ROM addresses.
 # One-byte exact quantizer: low six bits are base index, high two bits
 # are (4-threshold) mod 4. L holds fraction*64. Carry adds one index.
 if correct:raise ValueError('correction not implemented')
 op(4,'ld a,l',0x7d);op(4,'rlca',0x07);op(4,'rlca',0x07);op(7,f'add a,{DP}',0xc6,DP);op(4,'ld h,a',0x67);op(8,'ld a,ixl',0xdd,0x7d);op(4,'ld l,a',0x6f);op(7,'ld a,(hl)',0x7e)
 op(4,'ld l,a',0x6f);op(7,f'ld h,{THREAD_LO}',0x26,THREAD_LO);op(7,'ld a,(hl)',0x7e);op(4,'inc h',0x24);op(7,'ld h,(hl)',0x66);op(4,'ld l,a',0x6f);g(16,'prep_thread');op(4,'jp (hl)',0xe9)
 return a

def emit(im,o):
 t,k,c=o;z=im.op
 if c:z(k,*c);return
 # Conditional JP uses the same fixed 10 T in either direction.
 def jc(label,cc):
  im.lines.append('    jp '+cc+','+label);im.b.append({'c':0xda,'nc':0xd2}[cc]);im.fix.append((im.pc,label));im.b.extend(b'\0\0')
 def pad(t):
  b.emit_pad(im,t,16)
 if k=='zero_guard':
  zero=im.name('zero');join=im.name('join');z('ld a,i',0xed,0x57);z('and 15',0xe6,15);im.jp(zero,'z');im.jp(join);im.lab(zero);z('ld de,0',0x11,0,0);im.lab(join)
 elif k=='fetch_ctx_a':
  norm=im.name('normal');long=im.name('direct');join=im.name('join')
  z('exx',0xd9);z('ld a,(hl)',0x7e);z('or a',0xb7);im.jp(norm,'nz')
  z('ld a,(bc)',0x0a);z(f'cp {SHORTMAX+1}',0xfe,SHORTMAX+1);jc(long,'nc')
  z('ld l,a',0x6f);z('ld a,ixl',0xdd,0x7d);z(f'add a,{THRESHOLD//4}',0xc6,THRESHOLD//4);z(f'cp {THRESHOLD//2}',0xfe,THRESHOLD//2);z(f'ld a,{PTR_LO+1}',0x3e,PTR_LO+1);z('sbc a,0',0xde,0);z('ld h,a',0x67);z('xor a',0xaf);im.jp(join)
  im.lab(long);z(f'add a,{SHIFT}',0xc6,SHIFT);z('ld h,a',0x67);z('inc bc',3);z('ld a,(bc)',0x0a);z('ld l,a',0x6f);z('xor a',0xaf);z('scf',0x37);pad((12,));im.jp(join)
  im.lab(norm);pad((12,12,12,12,12,12,10));im.lab(join);z('exx',0xd9)
 elif k=='fetch_ctx_b':
  norm=im.name('normal');eof=im.name('eof');long=im.name('direct');join=im.name('join')
  z('exx',0xd9);im.jp(norm,'nz');jc(long,'c');z('ld a,(hl)',0x7e);z('inc h',0x24);z('inc h',0x24);z('ld h,(hl)',0x66);z('ld l,a',0x6f);z('ld a,(bc)',0x0a);z('or a',0xb7);im.jp(eof,'z');z('inc bc',3);im.jp(join)
  im.lab(eof);z('nop',0);im.jr(join)
  im.lab(long);z('inc bc',3);pad((12,12,9,10,4));im.jp(join)
  im.lab(norm);pad((12,12,12,12,12,9,4));im.lab(join);z('ld a,(hl)',0x7e);z('inc hl',0x23);z('exx',0xd9)
 elif k=='fetch':
  norm=im.name('normal');eof=im.name('eof');join=im.name('join');z('exx',0xd9);z('ld a,(hl)',0x7e);z('or a',0xb7);im.jr(norm,'nz');z('ld a,(bc)',0x0a);z('ld l,a',0x6f);z(f'ld h,{PTR_LO}',0x26,PTR_LO);z('ld a,(hl)',0x7e);z('inc h',0x24);z('ld h,(hl)',0x66);z('ld l,a',0x6f);z('ld a,(bc)',0x0a);z('or a',0xb7);im.jr(eof,'z');z('inc bc',3);z('jr $+2',0x18,0);im.jr(join);im.lab(eof);z('ld r,a',0xed,0x4f);z('nop',0);im.lab(norm+'_skip');im.jr(join);im.lab(norm)
  # Normal path padding: 83 T, equal to the block-boundary path.
  for v in (12,12,12,12,9,9,9,4,4):b.emit_pad(im,(v,),16)
  im.lab(join);z('ld a,(hl)',0x7e);z('inc hl',0x23);z('exx',0xd9)
 elif k=='advance_new':
  norm=im.name('normal');eof=im.name('eof');join=im.name('join');z('exx',0xd9);im.jp(norm,'nz');z('ld a,(bc)',0x0a);z('or a',0xb7);im.jp(eof,'z');z('inc bc',3);im.jp(join);im.lab(norm);b.emit_pad(im,(9,9,9),16);im.jp(join);im.lab(eof)
  for _ in range(4):z('nop',0)
  im.lab(join);z('exx',0xd9)
 elif k in ('addr_lo','addr_hi'):
  norm=im.name('normal');join=im.name('join');z('exx',0xd9);im.jr(norm,'nz')
  if k=='addr_lo':z('ld l,a',0x6f);z(f'ld h,{PTR_LO}',0x26,PTR_LO);z('ld a,(hl)',0x7e)
  else:z(f'ld h,{PTR_HI}',0x26,PTR_HI);z('ld h,(hl)',0x66);z('ld l,a',0x6f)
  im.jr(join);im.lab(norm);z('jr $+2',0x18,0);z('ld r,a',0xed,0x4f);z('nop',0);im.lab(join);z('exx',0xd9)
 elif k.startswith('hist'):z('exx',0xd9);z('ld a,'+('e' if k=='hist4' else 'd'),0x7b if k=='hist4' else 0x7a);z('exx',0xd9)
 elif k=='shiftalt':z('exx',0xd9);z('ld d,e',0x53);z('ld e,a',0x5f);z('exx',0xd9)
 elif k in ('frac_a','frac_copy_d'):
  z("ex af,af'",8);z('ld '+('d' if k=='frac_copy_d' else 'l')+',a',0x57 if k=='frac_copy_d' else 0x6f);z("ex af,af'",8);z('ld a,'+('d' if k=='frac_copy_d' else 'l'),0x7a if k=='frac_copy_d' else 0x7d)
 elif k=='read_corr':z('exx',0xd9);z('dec hl',0x2b);z('dec hl',0x2b);z('ld a,(hl)',0x7e);z('inc hl',0x23);z('inc hl',0x23);z('exx',0xd9)
 elif k=='prep_thread':z('ld sp,hl',0xf9);z('pop hl',0xe1)
 else:old.emit2(im,o)

def table_data(a):
 banks=np.concatenate([np.zeros((1,6)),a]);out=[bytearray(),bytearray()]
 def words(v):return np.asarray(v,dtype='<i2').tobytes()
 for bank in banks:
  pages=[bytearray(256),bytearray(256)]
  for i in range(6):
   pg=i//3;off=i%3*64;c=bank[i];vs=np.r_[np.r_[np.arange(8),np.arange(-8,0)]*4096,np.arange(16)*256];pages[pg][off:off+64]=words(np.rint(c*vs))
  for i,(pg,off) in enumerate(((0,192),(0,224),(1,192))):
   f=np.arange(16);p=np.rint(bank[2*i]*(f>>2)*64)+np.rint(bank[2*i+1]*(f&3)*64);pages[pg][off:off+32]=words(p)
  for i in range(2):out[i]+=pages[i]
 return out[0]+out[1]

def sched(acts,pat,period=256):
 slots=[x-12 for w in pat for x in (w,period-w)];ts=np.r_[0,np.cumsum([o[0] for o in acts])].tolist();N=len(acts);M=len(slots)
 @lru_cache(None)
 def f(k,i):
  if k==M:return () if i==N else None
  if ts[-1]-ts[i]>sum(slots[k:]):return None
  retopts=(0,) if k==M-1 else (10,0)
  if k<M-1 and slots[k]<10:retopts=(0,)
  for rt in retopts:
   if i>=N-1 and rt:continue
   room=slots[k]-rt
   if room<0:continue
   jj=[N] if k==M-1 else range(min(N-1,int(np.searchsorted(ts,ts[i]+room,side='right')-1)),i-1,-1)
   for j in jj:
    if j<i or j>N or (rt and j>=N-1):continue
    p=b.pad(room-(ts[j]-ts[i]),False)
    if p is None:continue
    z=f(k+1,j)
    if z is not None:return ((i,j,p,rt),)+z
  return None
 return f(0,0)

def fragments(acts,sc,split=True):
 seq=[];cur=[]
 for k,(i,j,p,rt) in enumerate(sc):
  cur.append(('edge',k%2))
  final=j==len(acts)
  if final:
   cur.extend(('act',n) for n in range(i,j-1));cur.extend(('pad',v) for v in p);cur.append(('act',j-1));seq.append(tuple(cur));cur=[];continue
  cur.extend(('act',n) for n in range(i,j));dt=sum(p)
  pp=b.pad(dt-10,False) if split and rt and dt>=10 else None
  if pp is not None:
   cur.append(('ret',));seq.append(tuple(cur));cur=[('pad',v) for v in pp]
  else:cur.extend(('pad',v) for v in p)
  if rt:cur.append(('ret',));seq.append(tuple(cur));cur=[]
 assert not cur
 return seq

def build(src,prefix,split=True,full_levels=False,period=320,grid=None,share=True,alpha=None,span=None):
 global SHORTMAX,SHIFT,ADDRLO,ADDRHI
 pulses=2560//period;assert pulses*period==2560
 d=dict(np.load(src));SHORTMAX=int(d.get('shortmax',223));assert 223<=SHORTMAX<=254;ADDRLO=int(d.get("direct_start",0x1000 if SHORTMAX==223 else 0x1800));ADDRHI=ADDRLO+(255-SHORTMAX)*256;SHIFT=((ADDRLO>>8)-(SHORTMAX+1))&255;assert ADDRLO%256==0 and ADDRHI<=65536;global NB,DP,BOOK,PTR_LO,PTR_HI,PAIR_LO,PAIR_HI,ALIAS_ZERO,ALIAS8,THREAD_LO,THREAD_HI;NB=len(d['a'])+1;ALIAS_ZERO=NB==8;ALIAS8=NB==9 and os.environ.get("LP20_ALIAS8")=="1";DP=2*NB+1-int(ALIAS_ZERO or ALIAS8)-int(ALIAS8);PTR_LO=DP+4;PTR_HI=PTR_LO+2;PAIR_LO=PTR_HI+2;PAIR_HI=PAIR_LO+1;THREAD_LO=PAIR_HI+1;THREAD_HI=THREAD_LO+1;BOOK=(THREAD_HI+1)*256;correct='corr' in d;assert not correct;dpsize=(PTR_LO-DP)*256
 if grid is None: grid=[35,100,135,150,160,170,185,220,285]
 if period not in (256,320,512,640):raise ValueError('unsupported carrier period')
 full_levels=True
 a,bk,bm,lens,idx,y=[d[k] for k in ('a','bk','bm','lens','idx','y')];assert a.shape==(NB-1,6) and int(d['bits'])==10
 global THRESHOLD
 alt,ab,active=d['alt'],d['ab'],d['active'];THRESHOLD=int(d['threshold']);assert THRESHOLD%4==0 and 4<=THRESHOLD<=508
 from precision_study import step
 from numba import njit
 @njit
 def check_plan(tb,rr,ll,plan,y,threshold):
  hist=np.zeros(6,np.int16);p=0
  for k in plan:
   if k<510 and k//255!=int(hist[0]>=threshold or hist[0]<-threshold):return False
   for j in range(ll[k]):
    bank,r=rr[k,j];v,ov=step(hist,tb[bank],r,10)
    if ov or p>=len(y) or v!=y[p]:return False
    p+=1
  return p==len(y)
 assert check_plan(old.compact_tables(a),np.concatenate([d['records'],d['ext_records']]),np.r_[d['lengths'],d['ext_lengths']],d['plan'],y,THRESHOLD)
 alt=np.where(active[:,None],alt,bk);ab=np.where(active,ab,bm)
 im=b.Image();z=im.op;im.lab('reset');z('di',0xf3);z('ld bc,$1000',1,0,16);z('ld ix,0',0xdd,0x21,0,0);z('ld iy,0',0xfd,0x21,0,0);z('xor a',0xaf);z("ex af,af'",8);z(f'ld a,{8 if ALIAS_ZERO else 0 if ALIAS8 else 1}',0x3e,8 if ALIAS_ZERO else 0 if ALIAS8 else 1);z('ld i,a',0xed,0x47);z('exx',0xd9);z('ld de,0',0x11,0,0);sptr=im.pc+1;z('ld bc,stream',1,0,0);z(f'ld hl,${BOOK+1:04x}',0x21,(BOOK+1)&255,(BOOK+1)>>8);z('exx',0xd9);boot=im.pc+1;z('ld sp,thread_1280',0x31,0,0);z('ret',0xc9);assert im.pc<=64;boot_start=im.pc;boot_line=len(im.lines);bootgap=bytearray(64-im.pc);im.data(bootgap);tl=len(im.lines);im.data(bytes(64));im.data(bytes(64));thl=len(im.lines);im.data(bytes(64));assert im.pc==256
 ptr=[];book=bytearray()
 if 'records' in d:
  raw=[tuple((int(b)+(1 if (ALIAS_ZERO or ALIAS8) else 2),int(r)) for b,r in rec[:n]) for rec,n in zip(np.concatenate([d['records'],d['ext_records']]),np.r_[d['lengths'],d['ext_lengths']])]
 else:
  raw=[tuple((int(bs[k])+(1 if (ALIAS_ZERO or ALIAS8) else 2),int(r)) for r in vs[k,:n]) for bs,vs in ((bm,bk),(ab,alt)) for k,n in enumerate(lens)]
 pairs=[(0,0),(8 if ALIAS_ZERO else 0 if ALIAS8 else 1,0)]+sorted(set(p for rec in raw for p in rec));assert len(pairs)<=256;pairidx={v:i for i,v in enumerate(pairs)}
 pairwords=[((r*64)&65535)|bank for bank,r in pairs]+[0]*(256-len(pairs))
 records=[]
 for c in range(2):
  records.append(bytes([1,0]));records.extend(bytes([pairidx[p] for p in rec]+[0]) for rec in raw[c*255:(c+1)*255])
 records.extend(bytes([pairidx[p] for p in rec]+[0]) for rec in raw[510:])
 assert len(records)==512+len(d['ext_lengths'])
 # ROM hole packing: the final 32 bytes of each second LPC page are
 # never addressed. The two pair pages have unused indices >= len(pairs).
 # Page zero offsets 128..191 are outside the boot and both thread maps.
 # Place whole terminated records in these regions. No change to CPU code.
 book.extend(records[0]);offsets={records[0]:BOOK};tab=bytearray(table_data(a));
 if ALIAS_ZERO:tab=tab[256:8*256]+tab[:256]+tab[9*256:]
 elif ALIAS8:tab=tab[256:9*256]+tab[10*256:]
 plo=bytearray(x&255 for x in pairwords);phi=bytearray(x>>8 for x in pairwords);gap=bytearray(64)
 holes=[(128,gap,0,64),(PAIR_LO*256+len(pairs),plo,len(pairs),256),(PAIR_HI*256+len(pairs),phi,len(pairs),256)]
 for pg in range(NB+1-int(ALIAS8),DP):holes.append((pg*256+224,tab,(pg-1)*256+224,pg*256))
 ptrholes=[bytearray(255-SHORTMAX) for _ in range(4)]
 threadholes=[]
 holes.append((boot_start,bootgap,0,len(bootgap)))
 for i,p in enumerate(ptrholes):holes.append(((PTR_LO+i)*256+SHORTMAX+1,p,0,len(p)))
 for addr,p in zip((64+len(d['ww10']),192+len(d['ww10'])),threadholes):holes.append((addr,p,0,len(p)))
 usedh=[0]*len(holes)
 # Group complete records by suffix sharing before placing them.  If any
 # suffix is used with a direct-address escape, require a valid direct
 # address for it at placement time, rather than duplicating it later.
 required=set(records[512:]);unique=set(records);maximal=set(unique)
 for r in unique:
  for j in range(1,len(r)):
   maximal.discard(r[j:])
 def direct(a):return ADDRLO<=a<ADDRHI
 def register(r,a):
  for j in range(len(r)):
   sub=r[j:]
   if sub not in unique:continue
   if sub not in offsets or (sub in required and direct(a+j) and not direct(offsets[sub])):offsets[sub]=a+j
 register(records[0],BOOK)
 def needs(r):return any(r[j:] in required for j in range(len(r)))
 import random
 rng=random.Random(int(os.environ.get("LAYOUT_SEED","0")));order=sorted(sorted(maximal),key=lambda r:(not needs(r),-len(r),rng.random()))
 for r in order:
  if r in offsets and (r not in required or direct(offsets[r])) and all(r[j:] not in required or (r[j:] in offsets and direct(offsets[r[j:]])) for j in range(len(r))):continue
  req=[j for j in range(len(r)) if r[j:] in required and (r[j:] not in offsets or not direct(offsets[r[j:]]))]
  choices=[]
  for i,(addr,buf,l,e) in enumerate(holes):
   u=usedh[i];a=addr+u
   if e-l-u>=len(r) and all(direct(a+j) for j in req):choices.append((e-l-u-len(r),i))
  if choices:
   _,i=min(choices);addr,buf,l,e=holes[i];u=usedh[i];buf[l+u:l+u+len(r)]=r;register(r,addr+u);usedh[i]+=len(r)
  else:
   a=BOOK+len(book);register(r,a);book.extend(r)
 # The boot/tail record may cover a suffix; verify every direct pointer.
 for r in sorted(required,key=lambda r:(-len(r),r)):
  if r not in offsets or not direct(offsets[r]):
   a=BOOK+len(book);register(r,a);book.extend(r)
   assert direct(offsets[r]),'direct address overflow'
 ptr=[offsets[r] for r in records]
 # Assert every terminated record is read identically by the original fetch.
 for record,addr in zip(records,ptr):
  if addr>=BOOK:assert book[addr-BOOK:addr-BOOK+len(record)]==record
  else:
   assert any(start<=addr and addr+len(record)<=start+usedh[i] and buf[l+addr-start:l+addr-start+len(record)]==record for i,(start,buf,l,r) in enumerate(holes))
 im.b[boot_start:64]=bootgap;im.lines[boot_line:tl]=['    db '+','.join(f'${v:02x}' for v in bootgap[i:i+16]) for i in range(0,len(bootgap),16)];im.b[128:192]=gap;im.lines[tl+4:tl+8]=['    db '+','.join(f'${v:02x}' for v in gap[i:i+16]) for i in range(0,64,16)]
 print('hole storage',sum(usedh),'bytes',usedh,flush=True)
 assert im.pc==256;im.data(tab);assert im.pc==DP*256;dp=im.pc;dl=len(im.lines);im.data(bytes(dpsize));pl=bytearray(x&255 for x in ptr[:512]);ph=bytearray(x>>8 for x in ptr[:512]);
 for i,pp in enumerate(ptrholes):
  buf=pl if i<2 else ph;start=(i%2)*256+SHORTMAX+1;buf[start:start+len(pp)]=pp
 im.data(pl);im.data(ph);assert im.pc==PAIR_LO*256;im.data(plo);im.data(phi);assert im.pc==THREAD_LO*256;ptrmap=im.pc;ptrlines=len(im.lines);im.data(bytes(512));assert im.pc==BOOK;im.data(book);codebase=im.pc
 ww=list(map(int,d['ww10']));lut=lut10(ww);outw=lut[y+512]
 if correct:
  cc=np.concatenate([d['corr'][i,:lens[i]] for i in idx]);outw=np.asarray(ww)[d['corrmap'][np.searchsorted(ww,outw),cc]]
 active=ww if full_levels else sorted(set([1280]+list(outw)));acts=actions(correct);chains={};frags={}
 tails={}
 if grid is None:
  plans,miss,lim=common.choose(acts,active,period,pulses)
  print('common chosen',period,lim,'fallback',miss,flush=True)
  pats={w:common.pat(w,period,pulses) for w in active}
 else:
  result=share_tails.choose(acts,period,pulses,grid,emit) if share else ps.choose(acts,period,pulses,grid)
  if result is None:raise ValueError('no common period schedule')
  plan,ranges=result[:2];tails=result[2] if share else {};plans={};pats={}
  for w in active:
   # Clamp rare endpoint levels to the nearest schedulable duty.
   pats[w]=pattern_balance.patterns(w,period,pulses,grid,alpha,span);plans[w]=[plan[i,x] for i,x in enumerate(pats[w])]
  print('period sharing',period,grid,'fallback',set(active)-set(plans),flush=True)
 for w in active:
  if w in plans:ff=plans[w]
  else:
   sc=sched(acts,pats[w],period)
   if sc is None:raise ValueError('No schedule '+str(w))
   ff=fragments(acts,sc,split)
  chain=[]
  for frag in ff:
   if frag not in frags:
    label=f'fragment_{len(frags)}';frags[frag]=label;im.lab(label)
    for item in frag:
     if item[0]=='edge':z('out (c),b' if item[1]==0 else 'out (c),c',0xed,0x41 if item[1]==0 else 0x49)
     elif item[0]=='act':emit(im,acts[item[1]])
     elif item[0]=='pad':b.emit_pad(im,(item[1],),16)
     elif item[0]=='ret':z('ret',0xc9)
     elif item[0]=='tail':im.jp(f'tail_{item[1]}_{item[2]}')
   chain.append(frags[frag])
  chains[w]=chain
 for phase,(i,j,entries,last) in sorted(tails.items()):
  for k in range(i,j+1):
   if k in entries:im.lab(f'tail_{phase}_{k}')
   if k<j:emit(im,acts[k])
  if not last:z('ret',0xc9)
 endfrags=im.pc;addrs={};mp=bytearray();chain_cache={}
 for w,chain in chains.items():
  key=tuple(chain)
  if key in chain_cache:addrs[w]=chain_cache[key];continue
  addrs[w]=im.pc;chain_cache[key]=im.pc;im.lab('thread_'+str(w));mp+=struct.pack('<HH'+str(pulses)+'H',im.pc+2,im.labels[chain[0]],*pats[w]);im.data(b''.join(struct.pack('<H',im.labels[l]) for l in chain))
 endcode=im.pc;im.lab('stream');payload=bytearray()
 for k in d['plan']:
  k=int(k)
  if k<510:
   assert k%255<SHORTMAX;payload.append(k%255+1)
  else:
   addr=ptr[k+2];assert ADDRLO<=addr<ADDRHI;payload.extend((((addr>>8)-SHIFT)&255,addr&255))
 im.data(payload+b'\0');used=im.pc
 print('used',used,'code',endfrags-codebase,'thread',endcode-endfrags,'frags',len(frags),'data',codebase,'cycles',sum(o[0] for o in acts),flush=True)
 if endcode+1>16384:print('EXPERIMENT exceeds 16 KiB:',endcode+1,flush=True)
 if used>65536:raise ValueError('ROM overflow')
 im.b[sptr:sptr+2]=struct.pack('<H',endcode);im.b[boot:boot+2]=struct.pack('<H',addrs[1280]);dt=bytearray()
 for frac in range(4):
  for hi in range(256):
   v=(hi if hi<128 else hi-256)*4+frac;dt.append(active.index(int(lut[v+512])))
 assert len(active)<=256 and len(dt)==dpsize
 vals=[addrs[w] for w in active]+[addrs[1280]]*(256-len(active));data=bytes(v&255 for v in vals)+bytes(v>>8 for v in vals);im.b[ptrmap:ptrmap+512]=data;im.lines[ptrlines:ptrlines+32]=['    db '+','.join(f'${v:02x}' for v in data[i:i+16]) for i in range(0,512,16)]
 im.b[dp:dp+dpsize]=dt;im.lines[dl:dl+dpsize//16]=['    db '+','.join(f'${v:02x}' for v in dt[i:i+16]) for i in range(0,dpsize,16)]
 p=Path(prefix);p.with_suffix('.bin').write_bytes(im.finish()+bytes(65536-used));p.with_suffix('.asm').write_text('\n'.join(im.lines+[f'    defs {65536}-$,0'])+'\n');p.with_suffix('.map').write_bytes(mp);p.with_suffix('.expected').write_bytes(np.r_[0,y,np.zeros(32,np.int16)].astype('<i2').tobytes());np.save(p.with_suffix('.widths10.npy'),outw);p.with_suffix('.threads').write_bytes(np.array([addrs[int(w)]+2 for w in np.r_[1280,outw,np.full(32,1280)]],dtype='<u2').tobytes());m=dict(corrected=correct,context_threshold=THRESHOLD,context_entries=int(np.sum(d['active'])),used=used,stream_bytes=len(payload),fragment_bytes=endfrags-codebase,thread_bytes=endcode-endfrags,header_tables=codebase,lpc_tables=NB*512-256*int(ALIAS_ZERO or ALIAS8)-256*int(ALIAS8),zero_alias=ALIAS_ZERO or ALIAS8,book_bytes=len(book),book_in_holes=sum(usedh),fragments=len(frags),levels=len(active),decoder_t=sum(o[0] for o in acts),period=period,pulses=pulses,split=split,grid=grid,pattern_alpha=alpha,pattern_span=span,patterns={str(int(w)):list(map(int,v)) for w,v in pats.items()});p.with_suffix('.json').write_text(json.dumps(m,indent=2));return m
if __name__=='__main__':build(sys.argv[1],sys.argv[2],split='--no-split' not in sys.argv,full_levels='--full' in sys.argv,period=int(sys.argv[3]) if len(sys.argv)>3 and sys.argv[3].isdigit() else 320,grid=list(map(int,sys.argv[4].split(','))) if len(sys.argv)>4 and not sys.argv[4].startswith('--') else None)

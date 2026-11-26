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
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE.parent/'LP20_v9'),str(HERE.parent/'LP20_v9'/'tools')]
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
TAB=1; DP=19; NB=9; BOOK=24*256; PTR_LO=20; PTR_HI=21; PAIR_LO=22; PAIR_HI=23; THREAD_LO=0; THREAD_HI=0

def actions(correct=False):
 a=[]
 def op(t,s,*v):a.append((t,s,tuple(v)))
 def g(t,s):op(t,s)
 # Unmodified sentinel handling. advance_new replaces the old inc sp
 # dummy delay on end of stream, which is not safe with a read-only stack.
 g(127,'fetch')
 op(4,'ld l,a',0x6f);op(7,f'ld h,{PAIR_LO}',0x26,PAIR_LO);op(7,'ld a,(hl)',0x7e);op(4,'inc h',0x24);op(7,'ld h,(hl)',0x66);op(4,'ld l,a',0x6f);op(7,'and 15',0xe6,15);op(4,'ld e,a',0x5f);op(9,'ld a,i',0xed,0x57);op(7,'and 240',0xe6,240);op(4,'or e',0xb3);op(9,'ld i,a',0xed,0x47);op(4,'ld a,l',0x7d);op(7,'and 192',0xe6,192);op(4,'ld e,a',0x5f);op(4,'ld d,h',0x54)
 def hist(i):
  if i<4:op(8,'ld a,'+('ix' if i<2 else 'iy')+('l' if i%2==0 else 'h'),0xdd if i<2 else 0xfd,0x7d if i%2==0 else 0x7c)
  else:g(12,'hist'+str(i))
 def rrc(n):
  for _ in range(n):op(4,'rrca',0x0f)
 def page(pg):
  op(9,'ld a,i',0xed,0x57);op(7,'and 15',0xe6,15)
  if pg:op(7,'add a,9',0xc6,9)
  op(4,'ld h,a',0x67)
 def add():op(11,'add hl,de',0x19);op(4,'ex de,hl',0xeb)
 def lookup(offset,pg):
  if offset:op(7,f'add a,{offset}',0xc6,offset)
  op(4,'ld l,a',0x6f);page(pg);op(7,'ld a,(hl)',0x7e);op(4,'inc l',0x2c);op(7,'ld h,(hl)',0x66);op(4,'ld l,a',0x6f);add()
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
 op(4,'ld e,l',0x5d);op(8,'ld a,ixl',0xdd,0x7d);op(4,'ld l,a',0x6f);op(7,'ld h,19',0x26,19);op(7,'ld a,(hl)',0x7e);op(4,'add a,e',0x83);op(7,'adc a,0',0xce,0);op(7,'and 63',0xe6,63);op(7,'or 64',0xf6,64)
 op(4,'ld l,a',0x6f);op(7,'ld h,0',0x26,0);op(7,'ld a,(hl)',0x7e);op(8,'set 7,l',0xcb,0xfd);op(7,'ld h,(hl)',0x66);op(4,'ld l,a',0x6f);g(16,'prep_thread');op(4,'jp (hl)',0xe9)
 return a

def emit(im,o):
 t,k,c=o;z=im.op
 if c:z(k,*c);return
 if k=='fetch':
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
 pulses=2560//period;assert pulses*period==2560
 d=dict(np.load(src));correct='corr' in d;assert not correct;dpsize=(PTR_LO-DP)*256
 if grid is None: grid=[35,100,135,150,160,170,185,220,285]
 if period not in (256,320,512,640):raise ValueError('unsupported carrier period')
 full_levels=True
 a,bk,bm,lens,idx,y=[d[k] for k in ('a','bk','bm','lens','idx','y')];assert a.shape==(8,6) and int(d['bits'])==10
 yr,_,ov=reconstruct(d['target'],old.compact_tables(a),bk,bm,lens,idx,10);assert np.array_equal(yr,y) and ov==0
 im=b.Image();z=im.op;im.lab('reset');z('di',0xf3);z('ld bc,$1000',1,0,16);z('ld ix,0',0xdd,0x21,0,0);z('ld iy,0',0xfd,0x21,0,0);z('xor a',0xaf);z("ex af,af'",8);z('ld a,1',0x3e,1);z('ld i,a',0xed,0x47);z('exx',0xd9);z('ld de,0',0x11,0,0);sptr=im.pc+1;z('ld bc,stream',1,0,0);z(f'ld hl,${BOOK+32:04x}',0x21,(BOOK+32)&255,(BOOK+32)>>8);z('exx',0xd9);boot=im.pc+1;z('ld sp,thread_1280',0x31,0,0);z('ret',0xc9);assert im.pc<=64;im.data(bytes(64-im.pc));tl=len(im.lines);im.data(bytes(64));im.data(bytes(64));thl=len(im.lines);im.data(bytes(64));assert im.pc==256
 ptr=[];book=bytearray();pairs=[(0,0),(1,0)]+sorted({(int(bm[k])+2,int(r)) for k,n in enumerate(lens) for r in bk[k,:n]});assert len(pairs)<=256;pairidx={v:i for i,v in enumerate(pairs)};pairwords=[((r*64)&65535)|bank for bank,r in pairs]+[0]*(256-len(pairs))
 # Reserve initial silent record, then store only maximal suffixes.
 records=[bytes([1]*32+[0])]+[bytes([pairidx[int(bm[k])+2,int(r)] for r in bk[k,:n]]+[0]) for k,n in enumerate(lens)]
 book.extend(records[0]);offsets={records[0]:0}
 for record in sorted(set(records[1:]),key=lambda r:(-len(r),r)):
  off=book.find(record)
  if off<0:off=len(book);book.extend(record)
  offsets[record]=off
 ptr=[BOOK+offsets[r] for r in records]
 assert im.pc==256;im.data(table_data(a));assert im.pc==DP*256;dp=im.pc;dl=len(im.lines);im.data(bytes(dpsize));im.data(bytes(x&255 for x in ptr));im.data(bytes(x>>8 for x in ptr));assert im.pc==PAIR_LO*256;im.data(bytes(x&255 for x in pairwords));im.data(bytes(x>>8 for x in pairwords));assert im.pc==BOOK;im.data(book);codebase=im.pc
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
 endcode=im.pc;im.lab('stream');im.data((idx+1).astype(np.uint8).tobytes()+b'\0');used=im.pc
 print('used',used,'code',endfrags-codebase,'thread',endcode-endfrags,'frags',len(frags),'data',codebase,'cycles',sum(o[0] for o in acts),flush=True)
 if endcode+1>16384:raise ValueError(f'Decoder including fixed tables and EOS exceeds 16 KiB: {endcode+1} bytes')
 if used>65536:raise ValueError('ROM overflow')
 im.b[sptr:sptr+2]=struct.pack('<H',endcode);im.b[boot:boot+2]=struct.pack('<H',addrs[1280]);dt=bytearray()
 for hi in range(256):
  v=(hi if hi<128 else hi-256)*4
  indices=[active.index(int(lut[v+frac+512])) for frac in range(4)]
  base=indices[0];assert indices==sorted(indices) and indices[-1]-base<=1
  threshold=next((i for i,q in enumerate(indices) if q!=base),4)
  packed=base|((4-threshold)<<6);dt.append(packed)
  for frac in range(4):
   total=packed+frac*64;assert (((total&255)+(total>>8))&63)==indices[frac]
 assert len(active)<=64;vals=[addrs[w] for w in active]+[addrs[1280]]*(64-len(active));lo=bytes(v&255 for v in vals);hi=bytes(v>>8 for v in vals);im.b[64:128]=lo;im.b[192:256]=hi;im.lines[tl:tl+4]=['    db '+','.join(f'${v:02x}' for v in lo[i:i+16]) for i in range(0,64,16)];im.lines[thl:thl+4]=['    db '+','.join(f'${v:02x}' for v in hi[i:i+16]) for i in range(0,64,16)];assert len(dt)==dpsize
 im.b[dp:dp+dpsize]=dt;im.lines[dl:dl+dpsize//16]=['    db '+','.join(f'${v:02x}' for v in dt[i:i+16]) for i in range(0,dpsize,16)]
 p=Path(prefix);p.with_suffix('.bin').write_bytes(im.finish()+bytes(65536-used));p.with_suffix('.asm').write_text('\n'.join(im.lines+[f'    defs {65536}-$,0'])+'\n');p.with_suffix('.map').write_bytes(mp);p.with_suffix('.expected').write_bytes(np.r_[0,y,np.zeros(32,np.int16)].astype('<i2').tobytes());np.save(p.with_suffix('.widths10.npy'),outw);p.with_suffix('.threads').write_bytes(np.array([addrs[int(w)]+2 for w in np.r_[1280,outw,np.full(32,1280)]],dtype='<u2').tobytes());m=dict(corrected=correct,used=used,stream_bytes=len(idx),fragment_bytes=endfrags-codebase,thread_bytes=endcode-endfrags,header_tables=codebase,lpc_tables=NB*512,book_bytes=len(book),fragments=len(frags),levels=len(active),decoder_t=sum(o[0] for o in acts),period=period,pulses=pulses,split=split,grid=grid,pattern_alpha=alpha,pattern_span=span,patterns={str(int(w)):list(map(int,v)) for w,v in pats.items()});p.with_suffix('.json').write_text(json.dumps(m,indent=2));return m
if __name__=='__main__':build(sys.argv[1],sys.argv[2],split='--no-split' not in sys.argv,full_levels='--full' in sys.argv,period=int(sys.argv[3]) if len(sys.argv)>3 and sys.argv[3].isdigit() else 320,grid=list(map(int,sys.argv[4].split(','))) if len(sys.argv)>4 and not sys.argv[4].startswith('--') else None)

"""ROM-only variable-length codec. Packed residual data; SP is a counter/bank register, never a stack."""
import sys,struct,json,subprocess,tempfile
from pathlib import Path
import numpy as np
import opt_build as b

def make(tb,bk,bm,lens,idx,period=128,pulses=20,levels=77,specialize=None):
 nb,order,_=tb.shape;assert order in (4,6,8)
 tables=np.concatenate((np.zeros((1,order,256),np.int16),tb)).astype(np.uint8)
 sizes=np.r_[32,lens].astype(np.uint8);bankmap=np.r_[0,bm+1].astype(np.uint8);stream=(idx+1).astype(np.uint8).tobytes()
 base=7*256;bookbase=base+tables.size
 rawbook=bytearray(bytes(32));ptrs=[bookbase]
 for k,n in enumerate(lens):ptrs.append(bookbase+len(rawbook));rawbook+=bk[k,:n].astype(np.uint8).tobytes()
 assert len(ptrs)==256 and max(ptrs)<65536 and max(lens)<256
 im=b.Image();im.lab('reset');im.op('di',0xf3);im.op('ld sp,0',0x31,0,0);im.op('ld bc,$1000',1,0,16);im.op('ld de,0',0x11,0,0);im.op('ld ix,0',0xdd,0x21,0,0);im.op('ld iy,0',0xfd,0x21,0,0);im.op('exx',0xd9);im.op('ld de,0',0x11,0,0);sptr=im.pc+1;im.op('ld bc,stream',1,0,0);im.op('ld hl,0',0x21,0,0);im.op('exx',0xd9);im.jp(f'pwm_{levels//2}')
 im.align();im.lab('bank_map');im.data(bytes(7+int(x)*order for x in bankmap));im.lab('dispatch_table');dp=im.pc;dl=len(im.lines);im.data(bytes(512));im.lab('pointer_lo');im.data(bytes(p&255 for p in ptrs));im.lab('pointer_hi');im.data(bytes(p>>8 for p in ptrs));im.lab('length_map');im.data(sizes.tobytes());assert im.pc==base;im.lab('coefficients');im.data(tables.tobytes());assert im.pc==bookbase;im.lab('codebook');im.data(rawbook);codebase=im.pc
 # SP low = remaining samples; SP high = coefficient table page. Alternate HL = packed codeword address.
 a=[(10,'ld hl,0',(0x21,0,0)),(11,'add hl,sp',(0x39,)),(4,'ld a,l',(0x7d,)),(4,'or a',(0xb7,)),(15,'peek',()),(45,'addr_lo',()),(45,'addr_hi',()),(15,'peek',()),(37,'count_lo',()),(43,'count_hi',()),(15,'peek',()),(23,'gate',()),(34,'advance_fast',()),(6,'dec sp',(0x3b,)),(10,'ld hl,0',(0x21,0,0)),(11,'add hl,sp',(0x39,)),(21,'read_packed',())]
 old=b.actions(order,fast=True);a+=old[old.index((4,'ld l,e',(0x6b,))):]
 def emit(o):
  t,k,c=o;e=im.op
  if k in ('addr_lo','addr_hi','count_lo','count_hi'):
   alt=k.startswith('addr');lo=k.endswith('lo');norm=im.name('normal');join=im.name('join')
   if alt:e('exx',0xd9)
   im.jr(norm,'nz')
   if lo:
    e('ld l,a',0x6f);e(f'ld h,{4 if alt else 6}',0x26,4 if alt else 6);e('ld a,(hl)',0x7e)
   else:
    e(f'ld h,{5 if alt else 1}',0x26,5 if alt else 1);e('ld h,(hl)',0x66);e('ld l,a',0x6f)
    if not alt:e('ld sp,hl',0xf9)
   im.jr(join);im.lab(norm);e('jr $+2',0x18,0);e('ld r,a',0xed,0x4f)
   if lo or alt:e('nop',0)
   else:
    l=im.name('delay');im.jp(l);im.lab(l)
   im.lab(join)
   if alt:e('exx',0xd9)
  elif k=='read_packed':e('exx',0xd9);e('ld a,(hl)',0x7e);e('inc hl',0x23);e('exx',0xd9)
  else:b.emit(im,o,0,0,16,False)
 all_widths=b.widths_for(period,levels);active=list(range(levels)) if specialize is None else sorted(set([levels//2]+[b.quant(int(v),levels) for v in specialize]));widths=[all_widths[i] for i in active];addrs=[];loops=0
 def output(k):im.op('out (c),b' if k%2==0 else 'out (c),c',0xed,0x41 if k%2==0 else 0x49)
 for l,w in zip(active,widths):
  im.lab(f'pwm_{l}');addrs.append(im.pc);loop=None
  for dh in (4,0):
   ph=b.pad(w-12-dh,False);pl=b.pad(period-w-12-(4-dh)-14,False)
   if ph is not None and pl is not None:
    for n in range(1,pulses-1):
     aa=a[:-1]+[(7,f'ld a,{pulses-n}',(0x3e,pulses-n))];s=b.schedule(aa,period,n,w,False,short=4)
     if s is not None:loop=(dh,ph,pl,aa,s);break
   if loop:break
  if loop:
   dh,ph,pl,aa,s=loop
   for k,(i,j,p) in enumerate(s):
    output(k)
    for o in aa[i:j]:emit(o)
    b.emit_pad(im,p,16)
   lab=im.name('pwm_repeat');im.lab(lab);im.op('nop',0);output(0)
   if dh:im.op('dec a',0x3d)
   b.emit_pad(im,ph,16);output(1)
   if not dh:im.op('dec a',0x3d)
   b.emit_pad(im,pl,16);im.jp(lab,'nz');im.op('jp (hl)',0xe9);loops+=1
  else:
   s=b.schedule(a,period,pulses,w,False)
   if s is None:raise ValueError(f'no schedule for width {w}')
   for k,(i,j,p) in enumerate(s):
    output(k)
    for n in range(i,j):
     if a[n][1]=='jp (hl)':b.emit_pad(im,p,16)
     emit(a[n])
    if j==0 or a[j-1][1]!='jp (hl)':b.emit_pad(im,p,16)
 endcode=im.pc;im.lab('stream');im.b[sptr:sptr+2]=endcode.to_bytes(2,'little');im.data(stream+b'\0');used=im.pc
 if used>65536:raise ValueError(f'ROM uses {used} bytes')
 vals=[addrs[min(range(len(active)),key=lambda j:abs(active[j]-b.quant(i if i<128 else i-256,levels)))] for i in range(256)];dt=bytes([v&255 for v in vals]+[v>>8 for v in vals]);im.b[dp:dp+512]=dt;im.lines[dl:dl+32]=['    db '+','.join(f'${v:02x}' for v in dt[i:i+16]) for i in range(0,512,16)]
 image=im.finish();meta=dict(cpu=20000000,period=period,pulses=pulses,fs=20000000/(period*pulses),carrier=20000000/period,levels=levels,active_levels=active,widths=widths,order=order,banks=nb,used=used,code_bytes=endcode-codebase,header_tables=codebase,codebook_bytes=len(rawbook),stream_address=endcode,stream_bytes=len(stream),dispatch=addrs,looped_levels=loops,decoder_t=sum(o[0] for o in a),port=0,high=16)
 # Separate serial representation (no ROM alignment / dispatch tables).
 payload=b'LP2P'+bytes([order,nb+1,levels])+struct.pack('<HBII',period,pulses,int(np.sum(lens[idx])),len(stream))+tables.tobytes()+bankmap.tobytes()+sizes.tobytes()+rawbook+stream
 return image+bytes(65536-used),'\n'.join(im.lines+[f'    defs {65536}-$,0'])+'\n',meta,payload

def build(npz,prefix,period=128,pulses=20,levels=77,specialize=0):
 d=np.load(npz);tb,bk,bm,lens,idx,y=(d[k] for k in ['tb','bk','bm','lens','idx','y']);rom,asm,m,payload=make(tb,bk,bm,lens,idx,period,pulses,levels,y if specialize else None)
 # Cross-check independent packed stream decoding and expected sample values.
 order=tb.shape[1];h=[0]*order;exp=bytearray([0]);u=tb.astype(np.uint8)
 for k in idx:
  for j in range(lens[k]):
   v=(int(bk[k,j])+sum(int(u[bm[k],i,h[i]]) for i in range(order)))&255;exp.append(v);h=[v]+h[:-1]
 assert np.array_equal(np.frombuffer(exp[1:],np.int8),y.astype(np.int8));exp.extend(bytes(32));dm=b''.join(struct.pack('<HH',a,w) for a,w in zip(m['dispatch'],m['widths']))
 with tempfile.TemporaryDirectory() as td:
  p=Path(td);(p/'rom').write_bytes(rom);(p/'map').write_bytes(dm);(p/'expected').write_bytes(exp);r=subprocess.run([str(Path(__file__).parent/'test_cpu'),str(p/'rom'),str(p/'map'),str(p/'expected'),str(period),str(pulses),'0','16'],capture_output=True,text=True)
  if r.returncode:raise RuntimeError(r.stderr)
  test=json.loads(r.stdout)
 p=Path(prefix);p.with_suffix('.bin').write_bytes(rom);p.with_suffix('.asm').write_text(asm);p.with_suffix('.json').write_text(json.dumps(m,indent=2));p.with_suffix('.test.json').write_text(json.dumps(test,indent=2));p.with_suffix('.lp2p').write_bytes(payload);print('USED',m['used'],'CODEBOOK',m['codebook_bytes'],'CODE',m['code_bytes'],'PAYLOAD',len(payload),'TEST',test,flush=True)
if __name__=='__main__':build(sys.argv[1],sys.argv[2],*(map(int,sys.argv[3:])))

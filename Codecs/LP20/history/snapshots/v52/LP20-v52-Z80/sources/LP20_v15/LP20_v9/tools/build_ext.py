"""LP2E: one-byte normal + FF escape, metadata fetched via read-only POP HL."""
import sys,struct,json,subprocess,tempfile
from pathlib import Path
import numpy as np
import opt_build as b

def make(tb,bk,bm,lens,idx,prices,period=128,pulses=20,levels=77,specialize=None):
 nb,order,_=tb.shape;assert order in (4,6,8)
 direct=[int(k) for k in np.unique(idx) if prices[k]==1];extended=[int(k) for k in np.unique(idx) if prices[k]==2];assert len(direct)<=254 and len(extended)<=256
 code={k:i+1 for i,k in enumerate(direct)};code.update({k:256+i for i,k in enumerate(extended)});stream=bytearray()
 for k in idx:
  x=code[int(k)];stream.extend([x] if x<255 else [255,x-256])
 assert len(stream)==int(np.sum(prices[idx]));tables=np.concatenate([np.zeros((1,order,256),np.int16),tb]).astype(np.uint8)
 # Dispatch at 0200, records at 0400..0BFF, predictors at 0C00.
 base=12*256;bookbase=base+tables.size;book=bytearray(bytes(32));records=[struct.pack('<HBB',bookbase,32,12)]*512
 for k,x in code.items():
  records[x]=struct.pack('<HBB',bookbase+len(book),int(lens[k]),12+(int(bm[k])+1)*order);book.extend(bk[k,:lens[k]].astype(np.uint8).tobytes())
 im=b.Image();im.lab('reset');im.op('di',0xf3);im.op('ld sp,0',0x31,0,0);im.op('ld bc,$1000',1,0,16);im.op('ld de,0',0x11,0,0);im.op('ld ix,0',0xdd,0x21,0,0);im.op('ld iy,0',0xfd,0x21,0,0);im.op('exx',0xd9);im.op('ld de,0',0x11,0,0);sptr=im.pc+1;im.op('ld bc,stream',1,0,0);im.op('ld hl,0',0x21,0,0);im.op('exx',0xd9);im.jp(f'pwm_{levels//2}')
 im.data(bytes(512-im.pc));im.lab('dispatch_table');dp=im.pc;dl=len(im.lines);im.data(bytes(512));im.lab('record_table');im.data(b''.join(records));assert im.pc==base;im.lab('coefficients');im.data(tables.tobytes());assert im.pc==bookbase;im.lab('codebook');im.data(book);codebase=im.pc
 a=[(10,'ld hl,0',(0x21,0,0)),(11,'add hl,sp',(0x39,)),(4,'ld a,l',(0x7d,)),(4,'or a',(0xb7,)),(45,'fetch',()),(35,'prefix_test',()),(41,'prefix_read',()),(28,'prefix_index',()),(4,"ex af,af'",(8,)),(32,'advance_test',()),(34,'advance',()),(4,"ex af,af'",(8,)),(42,'scale_record',()),(45,'record_sp',()),(38,'pop_pointer',()),(36,'pop_count',()),(6,'dec sp',(0x3b,)),(10,'ld hl,0',(0x21,0,0)),(11,'add hl,sp',(0x39,)),(21,'read_packed',())]
 old=b.actions(order,fast=True);a+=old[old.index((4,'ld l,e',(0x6b,))):]
 def p(t):
  z=b.pad(t,False);assert z is not None,t;b.emit_pad(im,z,16)
 def cond(body,t,nz=False):
  norm=im.name('skip');join=im.name('join');im.jp(norm,'z' if nz else 'nz');body();im.jp(join);im.lab(norm);p(t+10);im.lab(join)
 def emit(o):
  t,k,c=o;e=im.op
  if k=='fetch':
   def body():e('exx',0xd9);e('ld a,(bc)',0x0a);e('exx',0xd9);e('ld l,a',0x6f);e('ld h,0',0x26,0)
   norm=im.name("skip");join=im.name("join");im.jr(norm,"nz");body();im.jr(join);im.lab(norm);p(33);im.lab(join)
  elif k=='prefix_test':
   norm=im.name('not_boundary');join=im.name('join');im.jp(norm,'nz');e("ex af,af'",8);e('ld a,l',0x7d);e('cp 255',0xfe,255);im.jp(join);im.lab(norm);e("ex af,af'",8);e('ld a,1',0x3e,1);e('or a',0xb7);p(10);im.lab(join)
  elif k=='prefix_read':
   def body():e('exx',0xd9);e('inc bc',3);e('ld a,(bc)',0x0a);e('exx',0xd9)
   cond(body,21)
  elif k=='prefix_index':
   def body():e('ld l,a',0x6f);e('inc h',0x24)
   cond(body,8)
  elif k=='advance_test':
   norm=im.name('not_boundary');join=im.name('join');im.jp(norm,'nz');e("ex af,af'",8);e('ld a,h',0x7c);e('or l',0xb5);im.jp(join);im.lab(norm);e("ex af,af'",8);e('xor a',0xaf);p(14);im.lab(join)
  elif k=='advance':
   def body():e('exx',0xd9);e('inc bc',3);e('exx',0xd9)
   cond(body,14,True)
  elif k=='scale_record':
   def body():e('add hl,hl',0x29);e('add hl,hl',0x29)
   cond(body,22)
  elif k=='record_sp':
   def body():e('ld a,h',0x7c);e('add a,4',0xc6,4);e('ld h,a',0x67);e('ld sp,hl',0xf9);e('xor a',0xaf)
   cond(body,25)
  elif k=='pop_pointer':
   def body():e('exx',0xd9);e('pop hl',0xe1);e('exx',0xd9)
   cond(body,18)
  elif k=='pop_count':
   def body():e('pop hl',0xe1);e('ld sp,hl',0xf9)
   cond(body,16)
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
   for k,(i,j,pad) in enumerate(s):
    output(k)
    for o in aa[i:j]:emit(o)
    b.emit_pad(im,pad,16)
   lab=im.name('pwm_repeat');im.lab(lab);im.op('nop',0);output(0)
   if dh:im.op('dec a',0x3d)
   b.emit_pad(im,ph,16);output(1)
   if not dh:im.op('dec a',0x3d)
   b.emit_pad(im,pl,16);im.jp(lab,'nz');im.op('jp (hl)',0xe9);loops+=1
  else:
   s=b.schedule(a,period,pulses,w,False)
   if s is None:raise ValueError(f'no schedule for width {w}')
   for k,(i,j,pad) in enumerate(s):
    output(k)
    for n in range(i,j):
     if a[n][1]=='jp (hl)':b.emit_pad(im,pad,16)
     emit(a[n])
    if j==0 or a[j-1][1]!='jp (hl)':b.emit_pad(im,pad,16)
 endcode=im.pc;im.lab('stream');im.b[sptr:sptr+2]=endcode.to_bytes(2,'little') if endcode<65536 else b'\0\0';im.data(stream+b'\0');used=im.pc
 print('ROM used',used,'code',endcode-codebase,'book',len(book),'stream',len(stream),flush=True)
 if used>65536:raise ValueError(f'ROM uses {used} bytes')
 vals=[addrs[min(range(len(active)),key=lambda j:abs(active[j]-b.quant(i if i<128 else i-256,levels)))] for i in range(256)];dt=bytes([v&255 for v in vals]+[v>>8 for v in vals]);im.b[dp:dp+512]=dt;im.lines[dl:dl+32]=['    db '+','.join(f'${v:02x}' for v in dt[i:i+16]) for i in range(0,512,16)]
 image=im.finish();meta=dict(cpu=20000000,period=period,pulses=pulses,fs=20000000/(period*pulses),carrier=20000000/period,levels=levels,active_levels=active,widths=widths,order=order,banks=nb,used=used,code_bytes=endcode-codebase,header_tables=codebase,codebook_bytes=len(book),stream_address=endcode,stream_bytes=len(stream),dispatch=addrs,looped_levels=loops,decoder_t=sum(o[0] for o in a),port=0,high=16,direct=len(direct),extended=len(extended))
 # Portable payload contains relative offsets (within codebook), length, bank number, not ROM addresses.
 rec=[]
 for r in records:
  addr,n,bank=struct.unpack('<HBB',r);rec.append(struct.pack('<HBB',addr-bookbase,n,(bank-12)//order))
 payload=b'LP2E'+bytes([order,nb+1,levels])+struct.pack('<HBIII',period,pulses,int(np.sum(lens[idx])),len(stream),len(book))+tables.tobytes()+b''.join(rec)+book+stream
 return image+bytes(65536-used),'\n'.join(im.lines+[f'    defs {65536}-$,0'])+'\n',meta,payload

def build(npz,prefix,period=128,pulses=20,levels=77,specialize=0):
 d=np.load(npz);tb,bk,bm,lens,idx,y,prices=(d[k] for k in ['tb','bk','bm','lens','idx','y','prices']);rom,asm,m,payload=make(tb,bk,bm,lens,idx,prices,period,pulses,levels,y if specialize else None)
 h=[0]*tb.shape[1];exp=bytearray([0]);u=tb.astype(np.uint8)
 for k in idx:
  for j in range(lens[k]):
   v=(int(bk[k,j])+sum(int(u[bm[k],i,h[i]]) for i in range(len(h))))&255;exp.append(v);h=[v]+h[:-1]
 assert np.array_equal(np.frombuffer(exp[1:],np.int8),y.astype(np.int8));exp.extend(bytes(32));dm=b''.join(struct.pack('<HH',a,w) for a,w in zip(m['dispatch'],m['widths']))
 with tempfile.TemporaryDirectory() as td:
  p=Path(td);(p/'rom').write_bytes(rom);(p/'map').write_bytes(dm);(p/'expected').write_bytes(exp);r=subprocess.run([str(Path(__file__).parent/'test_cpu'),str(p/'rom'),str(p/'map'),str(p/'expected'),str(period),str(pulses),'0','16'],capture_output=True,text=True)
  if r.returncode:raise RuntimeError(r.stderr)
  test=json.loads(r.stdout)
 p=Path(prefix);p.with_suffix('.bin').write_bytes(rom);p.with_suffix('.asm').write_text(asm);p.with_suffix('.json').write_text(json.dumps(m,indent=2));p.with_suffix('.test.json').write_text(json.dumps(test,indent=2));p.with_suffix('.lp2e').write_bytes(payload);print('PAYLOAD',len(payload),'TEST',test,flush=True)
if __name__=='__main__':build(sys.argv[1],sys.argv[2],*(map(int,sys.argv[3:])))

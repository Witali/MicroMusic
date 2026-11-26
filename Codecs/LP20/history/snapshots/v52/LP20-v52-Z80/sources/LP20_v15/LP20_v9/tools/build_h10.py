"""10-bit LPC-6 ROM-only kernel. 6 high bytes in DE/IX/IY; fractions in D'E'.
SP is an arithmetic accumulator. Three small product tables per coefficient.
Record sentinel/ROM pointer replaces the SP block counter. All actions scheduled
between exact two-edge PWM outputs, no writes or CALL/PUSH.
"""
import sys,struct,json,subprocess,tempfile,math,os
from pathlib import Path
import numpy as np
import opt_build as b
from precision_study import reconstruct,render
from scipy.signal import resample_poly
import encode as e
TAB=11;DP=3

def compact_tables(a):
 x=np.arange(-512,512,dtype=np.int32);hi=x>>2;f=x&3;n=hi>>4;lo=hi&15
 return np.rint(a[:,:,None]*n*4096).astype(np.int32)+np.rint(a[:,:,None]*lo*256).astype(np.int32)+np.rint(a[:,:,None]*f*64).astype(np.int32)

def actions():
 a=[]
 def op(t,s,*v):a.append((t,s,tuple(v)))
 def group(t,s):a.append((t,s,()))
 group(19,'sentinel');group(15,'peek');group(45,'addr_lo');group(45,'addr_hi');group(52,'advance_new')
 group(21,'read');op(4,'ld l,a',0x6f);op(7,'and 63',0xe6,63);op(4,"ex af,af'",8);op(4,'ld a,l',0x7d);op(7,'and 192',0xe6,192);op(4,'ld l,a',0x6f);group(21,'read');op(4,'ld h,a',0x67);op(6,'ld sp,hl',0xf9)
 def load_hi(i):
  if i<2:op(4,'ld a,'+('e' if i==0 else 'd'),0x7b if i==0 else 0x7a)
  else:op(8,'ld a,'+('ix' if i<4 else 'iy')+('l' if i%2==0 else 'h'),0xdd if i<4 else 0xfd,0x7d if i%2==0 else 0x7c)
 def rrc(n):
  for _ in range(n):op(4,'rrca',0x0f)
 def rlc(n):
  for _ in range(n):op(4,'rlca',0x07)
 def lookup(off):
  if off:op(7,f'add a,{off}',0xc6,off)
  op(4,'ld l,a',0x6f);op(4,"ex af,af'",8);op(4,'ld h,a',0x67);op(4,"ex af,af'",8)
  op(7,'ld a,(hl)',0x7e);op(4,'inc l',0x2c);op(7,'ld h,(hl)',0x66);op(4,'ld l,a',0x6f);op(11,'add hl,sp',0x39);op(6,'ld sp,hl',0xf9)
 for i in range(6):
  if i==3:
   group(12,'frac_e');rrc(3);op(7,'and 30',0xe6,30);lookup(192)
   group(12,'frac_e');op(4,'add a,a',0x87);op(7,'and 30',0xe6,30);lookup(224)
   op(4,"ex af,af'",8);op(4,'inc a',0x3c);op(4,"ex af,af'",8)
  off=(i%3)*64
  load_hi(i);rrc(3);op(7,'and 30',0xe6,30);lookup(off)
  load_hi(i);op(4,'add a,a',0x87);op(7,'and 30',0xe6,30);lookup(off+32)
 group(12,'frac_d');rrc(3);op(7,'and 30',0xe6,30);lookup(192)
 op(10,'ld hl,0',0x21,0,0);op(11,'add hl,sp',0x39)
 op(4,'ld a,l',0x7d);op(7,'add a,32',0xc6,32);op(4,'ld l,a',0x6f);op(4,'ld a,h',0x7c);op(7,'adc a,0',0xce,0);op(4,'ld h,a',0x67);op(4,'ld a,l',0x7d);op(7,'and 192',0xe6,192);op(4,'ld l,a',0x6f)
 op(8,'ld iyh,iyl',0xfd,0x65);op(8,'ld a,ixh',0xdd,0x7c);op(8,'ld iyl,a',0xfd,0x6f);op(8,'ld ixh,ixl',0xdd,0x65);op(8,'ld ixl,d',0xdd,0x6a);op(4,'ld d,e',0x53);op(4,'ld e,h',0x5c)
 # 12 fraction bits, packed newest-first; A' holds new fraction during EXX.
 op(4,'ld a,l',0x7d);op(4,"ex af,af'",8);group(36,'shift_d');group(37,'shift_e')
 op(4,'ld a,l',0x7d);rlc(2);op(7,'and 3',0xe6,3);op(4,'add a,a',0x87);op(7,f'add a,{DP}',0xc6,DP);op(4,'ld h,a',0x67);op(4,'ld l,e',0x6b);op(7,'ld a,(hl)',0x7e);op(4,'inc h',0x24);op(7,'ld h,(hl)',0x66);op(4,'ld l,a',0x6f);op(4,'jp (hl)',0xe9)
 return a

def emit(im,o):
 t,k,c=o;z=im.op
 if c:z(k,*c);return
 if k=='sentinel':z('exx',0xd9);z('ld a,(hl)',0x7e);z('or a',0xb7);z('exx',0xd9)
 elif k.startswith('addr_'):
  norm=im.name('normal');join=im.name('join');z('exx',0xd9);im.jr(norm,'nz');lo=k.endswith('lo')
  if lo:z('ld l,a',0x6f);z('ld h,1',0x26,1);z('ld a,(hl)',0x7e)
  else:z('ld h,2',0x26,2);z('ld h,(hl)',0x66);z('ld l,a',0x6f)
  im.jr(join);im.lab(norm);z('jr $+2',0x18,0);z('ld r,a',0xed,0x4f);z('nop',0);im.lab(join);z('exx',0xd9)
 elif k=='advance_new':
  norm=im.name('normal');eof=im.name('eof');join=im.name('join');z('exx',0xd9);im.jr(norm,'nz');z('ld a,(bc)',0x0a);z('or a',0xb7);im.jp(eof,'z');z('inc bc',3);im.jp(join);im.lab(eof);z('inc sp',0x33);im.jp(join);im.lab(norm);z('jr $+2',0x18,0);z('nop',0);z('nop',0);z('nop',0);z('nop',0);z('nop',0);im.lab(join);z('exx',0xd9)
 elif k=='read_pair':z('exx',0xd9);z('ld a,(hl)',0x7e);z('inc hl',0x23);z("ex af,af'",8);z('ld a,(hl)',0x7e);z('inc hl',0x23);z('exx',0xd9)
 elif k=='read':z('exx',0xd9);z('ld a,(hl)',0x7e);z('inc hl',0x23);z('exx',0xd9)
 elif k in ('frac_e','frac_d'):z('exx',0xd9);z('ld a,'+k[-1],0x7b if k[-1]=='e' else 0x7a);z('exx',0xd9)
 elif k=='shift_d':
  # 4+4+4+4+4+4+4+4+4=36? use high two only (old E' low bits).
  z('exx',0xd9);z('ld a,e',0x7b);z('rrca',0x0f);z('rrca',0x0f);z('and 192',0xe6,192);z('ld l,a',0x6f);z('ld a,d',0x7a);z('rrca',0x0f);z('rrca',0x0f);z('and 48',0xe6,48);z('or l',0xb5);z('ld d,a',0x57);z('exx',0xd9)
 elif k=='shift_e':
  z('exx',0xd9);z('ld a,e',0x7b);z('rrca',0x0f);z('rrca',0x0f);z('and 63',0xe6,63);z('ld e,a',0x5f);z("ex af,af'",8);z('or e',0xb3);z('ld e,a',0x5f);z('exx',0xd9)
 else:b.emit(im,o,0,0,16,False)

# shift_d must NOT alter alternate HL (book pointer)! replace with a smaller
# shift using A' temporarily: save new fraction in main L, not A'.
def fix_actions(a):
 # replace shift_d/shift_e and preceding save.  D' consists only of bits7:4.
 # compute new D' using current D' >>2 then low2 of E' shifted to top;
 # store temporary in D', use A scratch only.
 i=next(i for i,o in enumerate(a) if o[1]=='shift_d');a[i]=(58,'shift_d2',());a[i+1]=(43,'shift_e',());return a

def emit2(im,o):
 if o[1]=='shift_d2':
  z=im.op;z('exx',0xd9);z('ld a,d',0x7a);z('rrca',0x0f);z('rrca',0x0f);z('and 48',0xe6,48);z('ld d,a',0x57);z('ld a,e',0x7b);z('rrca',0x0f);z('rrca',0x0f);z('and 192',0xe6,192);z('or d',0xb2);z('ld d,a',0x57);z('exx',0xd9)
 else:emit(im,o)

def table_bytes(a):
 buf=bytearray()
 for bank in np.concatenate([np.zeros((1,6)),a]):
  for off in (0,3):
   page=bytearray()
   for c in bank[off:off+3]:
    vs=np.r_[np.r_[np.arange(8),np.arange(-8,0)]*4096,np.arange(16)*256];p=np.rint(c*vs).astype(np.int64);page+=b''.join(struct.pack('<H',int(v)&65535) for v in p)
   for i in ((0,2) if off==0 else (4,)):
    f=np.arange(16);p=np.rint(bank[i]*(f>>2)*64).astype(np.int64)+np.rint(bank[i+1]*(f&3)*64).astype(np.int64);page+=b''.join(struct.pack('<H',int(v)&65535) for v in p)
   buf+=page+bytes(256-len(page))
 return bytes(buf)

def build(npz,prefix,period=128,pulses=20,limit=77):
 d=np.load(npz);a,bk,bm,lens,idx,y=[d[k] for k in ('a','bk','bm','lens','idx','y')];assert a.shape[1]==6 and int(d['bits'])==10
 tb=compact_tables(a);yr,_,ov=reconstruct(d['target'],tb,bk,bm,lens,idx,10);assert np.array_equal(yr,y) and ov==0
 tables=table_bytes(a);base=TAB*256;bookbase=base+len(tables);book=bytearray();ptr=[]
 for k in range(-1,len(lens)):
  ptr.append(bookbase+len(book));page=TAB+(int(bm[k])+1)*2 if k>=0 else TAB;n=lens[k] if k>=0 else 32
  for r in (bk[k,:n] if k>=0 else np.zeros(n,np.int16)):book+=struct.pack('<H',((int(r)*64)&65535)|page)
  book.append(0)
 assert len(ptr)==256
 im=b.Image();im.lab('reset');z=im.op;z('di',0xf3);z('ld bc,$1000',1,0,16);z('ld de,0',0x11,0,0);z('ld ix,0',0xdd,0x21,0,0);z('ld iy,0',0xfd,0x21,0,0);z('exx',0xd9);z('ld de,0',0x11,0,0);sptr=im.pc+1;z('ld bc,stream',1,0,0);z(f'ld hl,${bookbase+64:04x}',0x21,(bookbase+64)&255,(bookbase+64)>>8);z('exx',0xd9);im.jp('pwm_'+str(period//2));im.align();im.data(bytes(x&255 for x in ptr));im.data(bytes(x>>8 for x in ptr));dp=im.pc;dl=len(im.lines);im.data(bytes(2048));assert im.pc==base;im.data(tables);assert im.pc==bookbase;im.data(book);codebase=im.pc
 acts=fix_actions(actions());print('decode',sum(o[0] for o in acts),'T, data',codebase,'stream',len(idx),flush=True)
 # Need short actions at extreme duty; test every candidate and symmetric subset.
 schedules={};mid=period//2
 for w in range(16,period-15):
  s=b.schedule(acts,period,pulses,w,False)
  if s is not None:schedules[w]=s
 good=sorted(set(schedules)&{period-w for w in schedules});assert mid in good
 span=mid-min(good);ww=sorted(set(min(good,key=lambda w:(abs(w-v),abs(w-mid))) for v in np.linspace(mid-span,mid+span,limit))) if 'ww' not in d else list(map(int,d['ww']));assert set(ww)<=set(good) and ww[0]==mid-span and ww[-1]==mid+span;lut=np.array([min(ww,key=lambda w:(abs(w-(mid+v*span/512)),abs(w-mid))) for v in range(-512,512)]);active=ww if os.environ.get("H10_FULL")=="1" else sorted(set([mid]+list(lut[y+512])));print('range',min(ww),max(ww),'levels',len(ww),'active',len(active),flush=True)
 addrs={};loops=0
 for w in active:
  im.lab(f'pwm_{w}');addrs[w]=im.pc;loop=None
  for dh in (4,0):
   ph=b.pad(w-12-dh,False);pl=b.pad(period-w-12-(4-dh)-14,False)
   if ph is None or pl is None:continue
   for n in range(1,pulses-1):
    aa=acts[:-1]+[(7,f'ld a,{pulses-n}',(0x3e,pulses-n))];s=b.schedule(aa,period,n,w,False,short=4)
    if s is not None:loop=(dh,ph,pl,aa,s);break
   if loop:break
  def output(k):z('out (c),b' if k%2==0 else 'out (c),c',0xed,0x41 if k%2==0 else 0x49)
  if loop:
   dh,ph,pl,aa,s=loop
   for k,(i,j,p) in enumerate(s):
    output(k)
    for o in aa[i:j]:emit2(im,o)
    b.emit_pad(im,p,16)
   lab=im.name('repeat');im.lab(lab);z('nop',0);output(0)
   if dh:z('dec a',0x3d)
   b.emit_pad(im,ph,16);output(1)
   if not dh:z('dec a',0x3d)
   b.emit_pad(im,pl,16);im.jp(lab,'nz');z('jp (hl)',0xe9);loops+=1
  else:
   s=schedules[w]
   for k,(i,j,p) in enumerate(s):
    output(k)
    for n in range(i,j):
     if acts[n][1]=='jp (hl)':b.emit_pad(im,p,16)
     emit2(im,acts[n])
    if j==0 or acts[j-1][1]!='jp (hl)':b.emit_pad(im,p,16)
 endcode=im.pc;im.lab('stream');im.b[sptr:sptr+2]=endcode.to_bytes(2,'little') if endcode<65536 else b'\0\0';im.data((idx+1).astype(np.uint8).tobytes()+b'\0');used=im.pc;print('USED',used,'CODE',endcode-codebase,flush=True)
 if used>65536:raise ValueError('ROM exceeds 64K')
 dt=bytearray()
 for frac in range(4):
  vals=[addrs[min(active,key=lambda w:abs(w-lut[((hi if hi<128 else hi-256)*4+frac)+512]))] for hi in range(256)];dt.extend(bytes(v&255 for v in vals));dt.extend(bytes(v>>8 for v in vals))
 im.b[dp:dp+2048]=dt;im.lines[dl:dl+128]=['    db '+','.join(f'${v:02x}' for v in dt[i:i+16]) for i in range(0,2048,16)];image=im.finish()+bytes(65536-used)
 meta=dict(cpu=20000000,period=period,pulses=pulses,fs=20000000/(period*pulses),carrier=20000000/period,bits=10,order=6,banks=len(a),used=used,code_bytes=endcode-codebase,header_tables=codebase,stream_bytes=len(idx),levels=len(ww),active=active,width_min=min(ww),width_max=max(ww),decoder_t=sum(o[0] for o in acts),looped_levels=loops)
 path=Path(prefix);path.with_suffix('.bin').write_bytes(image);path.with_suffix('.asm').write_text('\n'.join(im.lines+[f'    defs {65536}-$,0'])+'\n');path.with_suffix('.json').write_text(json.dumps(meta,indent=2,default=int));path.with_suffix('.map').write_bytes(b''.join(struct.pack('<HH',addr,w) for w,addr in addrs.items()));path.with_suffix('.expected').write_bytes(np.r_[0,y,np.zeros(32,np.int16)].astype('<i2').tobytes());np.save(path.with_suffix('.widths.npy'),lut[y+512]);print(meta,flush=True)
if __name__=='__main__':build(sys.argv[1],sys.argv[2],*map(int,sys.argv[3:]))

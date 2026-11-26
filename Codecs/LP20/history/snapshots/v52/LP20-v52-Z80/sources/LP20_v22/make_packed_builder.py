from pathlib import Path
s=Path(__file__).with_name('build_v22.py').read_text()
s=s.replace("g(94,'fetch_ctx_a');g(94,'fetch_ctx_b')", "g(99,'packed_a1');g(93,'packed_a2');g(124,'packed_b');g(76,'packed_c1');g(100,'packed_c2');g(83,'packed_c3');g(101,'packed_d')")
# fixed 32 KiB address map; stream reversed below guard byte.
s=s.replace("z('ld bc,stream',1,0,0)","z('ld bc,0',1,0,0)")
s=s.replace("im.b[sptr:sptr+2]=struct.pack('<H',endcode);", "im.b[sptr:sptr+2]=b'\\0\\0';")
s=s.replace("im.lab('stream');im.data((idx+1).astype(np.uint8).tobytes()+b'\\0');used=im.pc", """assert int(max(idx))<=126
 codes=np.r_[idx+1,0].astype(np.uint8);payload=np.packbits(((codes[:,None]>>np.arange(6,-1,-1))&1).astype(np.uint8).ravel(),bitorder='big').tobytes()
 # Guard byte is read only for token phase zero; masked output ignores it.
 end=32768;pad=end-1-len(payload)-im.pc
 if pad<0:raise ValueError(f'packed image needs {im.pc+len(payload)+1} bytes before page alignment')
 im.lab('stream');im.data(bytes(pad));im.lab('packed_stream');im.data(payload[::-1]);im.data(b'\\0');used=im.pc""")
s=s.replace("stream_bytes=len(idx),fragment_bytes", "stream_bytes=len(payload),token_count=len(idx),core_bytes=endcode,packed_padding=pad,packed_end=end,fragment_bytes")
s=s.replace("print('used',used,'code'", "print('packed payload',len(payload),'core',endcode,'padding',pad);print('used',used,'code'")
helper='''\ndef packed_pad(im,n):
 # No register/flag changes: use NOP, JR to following instruction, LD R,A, JP.
 @lru_cache(None)
 def solve(t):
  if t==0:return ()
  if t<0:return None
  choices=[]
  for v in (4,9,12,10):
   z=solve(t-v)
   if z is not None:choices.append((v,)+z)
  return min(choices,key=lambda a:sum(1 if v==4 else 2 if v in (9,12) else 3 for v in a)) if choices else None
 p=solve(n);assert p is not None,n;b.emit_pad(im,p,16)

def shift_packed(im,n):
 for i in range(n):im.op('srl h',0xcb,0x3c);im.op('rra',0x1f)

def conditional_shift(im,bit):
 z=im.op;skip=im.name('skip');join=im.name('shift_done');z(f'bit {bit},d',0xcb,0x42+bit*8);im.jp(skip,'z');shift_packed(im,1<<bit);im.jp(join);im.lab(skip);packed_pad(im,12*(1<<bit)+10);im.lab(join)

def packed_emit(im,k):
 z=im.op;norm=im.name('pack_norm');join=im.name('pack_join')
 if k=='packed_a1':
  z('exx',0xd9);z('ld a,(hl)',0x7e);z('or a',0xb7);im.jp(norm,'nz');z('ld h,b',0x60);z('ld l,c',0x69)
  for i in range(3):z('srl h',0xcb,0x3c);z('rr l',0xcb,0x1d)
  z('cp a',0xbf);z('exx',0xd9);im.jp(join);im.lab(norm);z('exx',0xd9);packed_pad(im,70);im.lab(join)
 elif k=='packed_a2':
  im.jp(norm,'nz');z('exx',0xd9);z('or a',0xb7);z('sbc hl,bc',0xed,0x42);z('dec hl',0x2b);z('dec hl',0x2b);z('ld a,h',0x7c);z('add a,128',0xc6,128);z('ld h,a',0x67);z('ld a,c',0x79);z('and 7',0xe6,7);z('exx',0xd9);z('ld d,a',0x57);z('xor a',0xaf);im.jp(join);im.lab(norm);packed_pad(im,83);im.lab(join)
 elif k=='packed_b':
  im.jp(norm,'nz');z('exx',0xd9);z('ld a,(hl)',0x7e);z('inc hl',0x23);z('exx',0xd9);z('ld e,a',0x5f);z('exx',0xd9);z('ld a,(hl)',0x7e);z('exx',0xd9);z('ld h,a',0x67);z('ld a,e',0x7b);shift_packed(im,1);conditional_shift(im,0);z('cp a',0xbf);im.jp(join);im.lab(norm);packed_pad(im,114);im.lab(join)
 elif k=='packed_c1':
  im.jp(norm,'nz');conditional_shift(im,1);z('cp a',0xbf);im.jp(join);im.lab(norm);packed_pad(im,66);im.lab(join)
 elif k=='packed_c2':
  im.jp(norm,'nz');conditional_shift(im,2);z('cp a',0xbf);im.jp(join);im.lab(norm);packed_pad(im,90);im.lab(join)
 elif k=='packed_c3':
  im.jp(norm,'nz');z('and 127',0xe6,127);z('exx',0xd9);z('ld l,a',0x6f);z('ld a,ixl',0xdd,0x7d);z(f'add a,{THRESHOLD//4}',0xc6,THRESHOLD//4);z(f'cp {THRESHOLD//2}',0xfe,THRESHOLD//2);z(f'ld a,{PTR_LO+1}',0x3e,PTR_LO+1);z('sbc a,0',0xde,0);z('ld h,a',0x67);z('xor a',0xaf);z('exx',0xd9);im.jp(join);im.lab(norm);packed_pad(im,73);im.lab(join)
 elif k=='packed_d':
  z('exx',0xd9);im.jp(norm,'nz');eof=im.name('packed_eof');common=im.name('packed_common');z('ld a,l',0x7d);z('or a',0xb7);im.jp(eof,'z');z('inc bc',3);im.jp(common);im.lab(eof);z('nop',0);im.jr(common);im.lab(common);z('ld a,(hl)',0x7e);z('inc h',0x24);z('inc h',0x24);z('ld h,(hl)',0x66);z('ld l,a',0x6f);im.jp(join);im.lab(norm);packed_pad(im,70);im.lab(join);z('ld a,(hl)',0x7e);z('inc hl',0x23);z('exx',0xd9)
 else:raise ValueError(k)
'''
s=s.replace('def emit(im,o):',helper+'\ndef emit(im,o):').replace("if c:z(k,*c);return\n if k=='fetch_ctx_a':", "if c:z(k,*c);return\n if k.startswith('packed_'):packed_emit(im,k);return\n if k=='fetch_ctx_a':")
Path(__file__).with_name('build_packed7.py').write_text(s)

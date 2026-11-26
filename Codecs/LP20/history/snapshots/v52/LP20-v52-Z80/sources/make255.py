from pathlib import Path
s=Path('LP20_v38/zero_builder52.py').read_text()
a=s.index(' op(4,\'ld e,l\'',s.index(' # Select next thread.'))
e=s.index(' return a',a)
s=s[:a]+''' op(4,'ld a,l',0x7d);op(4,'rlca',0x07);op(4,'rlca',0x07);op(7,f'add a,{DP}',0xc6,DP);op(4,'ld h,a',0x67);op(8,'ld a,ixl',0xdd,0x7d);op(4,'ld l,a',0x6f);op(7,'ld a,(hl)',0x7e)
 op(4,'ld l,a',0x6f);op(7,f'ld h,{THREAD_LO}',0x26,THREAD_LO);op(7,'ld a,(hl)',0x7e);op(4,'inc h',0x24);op(7,'ld h,(hl)',0x66);op(4,'ld l,a',0x6f);g(16,'prep_thread');op(4,'jp (hl)',0xe9)
'''+s[e:]
s=s.replace('PAIR_HI,ALIAS_ZERO,ALIAS8;NB=', 'PAIR_HI,ALIAS_ZERO,ALIAS8,THREAD_LO,THREAD_HI;NB=')
s=s.replace('PTR_LO=DP+1;PTR_HI=PTR_LO+2;PAIR_LO=PTR_HI+2;PAIR_HI=PAIR_LO+1;BOOK=(PAIR_HI+1)*256;', 'PTR_LO=DP+4;PTR_HI=PTR_LO+2;PAIR_LO=PTR_HI+2;PAIR_HI=PAIR_LO+1;THREAD_LO=PAIR_HI+1;THREAD_HI=THREAD_LO+1;BOOK=(THREAD_HI+1)*256;')
s=s.replace("threadholes=[bytearray(64-len(d['ww10'])) for _ in range(2)]",'threadholes=[]')
s=s.replace('im.data(plo);im.data(phi);assert im.pc==BOOK;',"im.data(plo);im.data(phi);assert im.pc==THREAD_LO*256;ptrmap=im.pc;ptrlines=len(im.lines);im.data(bytes(512));assert im.pc==BOOK;")
s=s.replace("if endcode+1>16384:raise ValueError(f'Decoder including fixed tables and EOS exceeds 16 KiB: {endcode+1} bytes')", "if endcode+1>16384:print('EXPERIMENT exceeds 16 KiB:',endcode+1,flush=True)")
a=s.index(' for hi in range(256):',s.index('im.b[sptr:sptr+2]'))
e=s.index(' p=Path(prefix);',a)
s=s[:a]+''' for frac in range(4):
  for hi in range(256):
   v=(hi if hi<128 else hi-256)*4+frac;dt.append(active.index(int(lut[v+512])))
 assert len(active)<=256 and len(dt)==dpsize
 vals=[addrs[w] for w in active]+[addrs[1280]]*(256-len(active));data=bytes(v&255 for v in vals)+bytes(v>>8 for v in vals);im.b[ptrmap:ptrmap+512]=data;im.lines[ptrlines:ptrlines+32]=['    db '+','.join(f'${v:02x}' for v in data[i:i+16]) for i in range(0,512,16)]
 im.b[dp:dp+dpsize]=dt;im.lines[dl:dl+dpsize//16]=['    db '+','.join(f'${v:02x}' for v in dt[i:i+16]) for i in range(0,dpsize,16)]
'''+s[e:]
Path('LP20_v38/zero_builder255.py').write_text(s)
s=Path('native63.py').read_text().replace('zero_builder52','zero_builder255').replace("p=np.load(ROOT/'LP20-v50/first/63-augment.npz');patterns=p['patterns'];sums=p['sums'];", "patterns=np.load(ROOT/'LP20-v51/pwm255.npy');sums=patterns.sum(1);").replace('assert np.ptp(lut.reshape(256,4),axis=1).max()<=1','').replace("'native63'","'native255-experimental'").replace("'0x1800'","'0x1d00'").replace('+1e-9*abs(sums[None,:]-1280)','')
Path('native255.py').write_text(s)

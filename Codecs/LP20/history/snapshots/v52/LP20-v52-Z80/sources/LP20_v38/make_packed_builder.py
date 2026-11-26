from pathlib import Path
R=Path(__file__).resolve().parent
s=(R.parent/'LP20_v25/layout_builder.py').read_text()
# Unused initial bytes in page 0, unused short pointer slots in both contexts,
# and the three impossible indices in each PWM map (61..63).
s=s.replace("assert im.pc<=64;im.data(bytes(64-im.pc));tl=len(im.lines)","assert im.pc<=64;boot_start=im.pc;boot_line=len(im.lines);bootgap=bytearray(64-im.pc);im.data(bootgap);tl=len(im.lines)")
s=s.replace('usedh=[0]*len(holes)', '''ptrholes=[bytearray(255-SHORTMAX) for _ in range(4)]
 threadholes=[bytearray(64-len(d['ww10'])) for _ in range(2)]
 holes.append((boot_start,bootgap,0,len(bootgap)))
 for i,p in enumerate(ptrholes):holes.append(((PTR_LO+i)*256+SHORTMAX+1,p,0,len(p)))
 for addr,p in zip((64+len(d['ww10']),192+len(d['ww10'])),threadholes):holes.append((addr,p,0,len(p)))
 usedh=[0]*len(holes)''')
s=s.replace('im.b[128:192]=gap;', '''im.b[boot_start:64]=bootgap;im.lines[boot_line:tl]=['    db '+','.join(f'${v:02x}' for v in bootgap[i:i+16]) for i in range(0,len(bootgap),16)];im.b[128:192]=gap;''')
s=s.replace('im.data(bytes(x&255 for x in ptr[:512]));im.data(bytes(x>>8 for x in ptr[:512]));', '''pl=bytearray(x&255 for x in ptr[:512]);ph=bytearray(x>>8 for x in ptr[:512]);
 for i,pp in enumerate(ptrholes):
  buf=pl if i<2 else ph;start=(i%2)*256+SHORTMAX+1;buf[start:start+len(pp)]=pp
 im.data(pl);im.data(ph);''')
s=s.replace('lo=bytes(v&255 for v in vals);hi=bytes(v>>8 for v in vals);', '''lo=bytes(v&255 for v in vals[:len(active)])+threadholes[0];hi=bytes(v>>8 for v in vals[:len(active)])+threadholes[1];''')
# Preserve original pointer validation and exact sample path validation.
(R/'packed_builder.py').write_text(s)

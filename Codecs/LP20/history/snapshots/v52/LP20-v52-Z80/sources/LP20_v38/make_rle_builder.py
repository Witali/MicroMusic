from pathlib import Path
R=Path(__file__).resolve().parent
s=(R/'zero_builder.py').read_text()
s=s.replace("g(111,'fetch_ctx_a');g(104,'fetch_ctx_b')", "g(129,'fetch_ctx_a');g(91,'fetch_ctx_b');g(66,'read_rle')")
s=s.replace("norm=im.name('normal');long=im.name('direct');join=im.name('join')\n  z('exx',0xd9);z('ld a,(hl)',0x7e);", "norm=im.name('normal');long=im.name('direct');join=im.name('join');rep=im.name('repeat')\n  z('exx',0xd9);z('bit 7,h',0xcb,0x7c);im.jp(rep,'nz');z('ld a,(hl)',0x7e);",1)
s=s.replace("im.lab(norm);pad((12,12,12,12,12,12,10));im.lab(join);z('exx',0xd9)","im.lab(rep);z('ld a,0',0x3e,0);z('nop',0);im.jp(norm);im.lab(norm);pad((12,12,12,12,12,12,10));im.lab(join);z('exx',0xd9)",1)
s=s.replace("im.lab(join);z('ld a,(hl)',0x7e);z('inc hl',0x23);z('exx',0xd9)\n elif k=='fetch':", "im.lab(join);z('exx',0xd9)\n elif k=='read_rle':\n  second=im.name('second');first=im.name('first');join=im.name('join');z('exx',0xd9);z('bit 7,h',0xcb,0x7c);im.jp(second,'nz');z('ld a,(hl)',0x7e);z(f'cp {ALIAS_MIN}',0xfe,ALIAS_MIN);jc(first,'nc');z('inc hl',0x23);im.jp(join);im.lab(second);z('res 7,h',0xcb,0xbc);z('ld a,(hl)',0x7e);z('inc hl',0x23);z('ld r,a',0xed,0x4f);im.jp(join);im.lab(first);z('set 7,h',0xcb,0xfc);z('nop',0);z('nop',0);im.lab(join);z('exx',0xd9)\n elif k=='fetch':",1)
# Choose repeat aliases from observed repeated pairs across distinct dictionary records.
s=s.replace("pairwords=[((r*64)&65535)|bank for bank,r in pairs]+[0]*(256-len(pairs))", """from collections import Counter
 global ALIAS_MIN
 ALIAS_MIN=len(pairs);counts=Counter()
 for rec in set(raw):
  j=0
  while j<len(rec)-1:
   if rec[j]==rec[j+1]:counts[rec[j]]+=1;j+=2
   else:j+=1
 aliases=[p for p,c in counts.most_common(min(256-len(pairs),int(os.environ.get('LP20_RLE_ALIASES','48')))) if c>=2]
 aliases.sort();aliasidx={p:ALIAS_MIN+i for i,p in enumerate(aliases)};pairs+=aliases
 def rle(rec):
  out=[];j=0
  while j<len(rec):
   if j+1<len(rec) and rec[j]==rec[j+1] and rec[j] in aliasidx:out.append(aliasidx[rec[j]]);j+=2
   else:out.append(pairidx[rec[j]]);j+=1
  return bytes(out+[0])
 print('RLE aliases',len(aliases),'min',ALIAS_MIN,'raw/packed unique bytes',sum(len(rec)+1 for rec in set(raw)),sum(len(rle(rec)) for rec in set(raw)),flush=True)
 pairwords=[((r*64)&65535)|bank for bank,r in pairs]+[0]*(256-len(pairs))""")
s=s.replace('bytes([pairidx[p] for p in rec]+[0])','rle(rec)')
(R/'rle_builder.py').write_text(s)

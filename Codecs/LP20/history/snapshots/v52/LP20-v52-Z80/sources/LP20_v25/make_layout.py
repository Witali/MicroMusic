#!/usr/bin/env python3
"""Generate v24-compatible builder with direct-address-aware suffix packing."""
from pathlib import Path
R=Path(__file__).resolve().parent
s=(R.parent/'LP20_v24'/'build_extended.py').read_text();start=s.index(' for record in sorted(set(records[1:])');end=s.index(' ptr=[offsets[r] for r in records]',start)
s=s[:start]+''' # Group complete records by suffix sharing before placing them.  If any
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
 order=sorted(maximal,key=lambda r:(not needs(r),-len(r),r))
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
''' + s[end:]
s=s.replace('assert SHORTMAX in (223,239);SHIFT=48 if SHORTMAX==223 else 40;ADDRLO=0x1000 if SHORTMAX==223 else 0x1800;ADDRHI=0x3000 if SHORTMAX==223 else 0x2800;', 'assert 223<=SHORTMAX<=254;ADDRLO=int(d.get("direct_start",0x1000 if SHORTMAX==223 else 0x1800));ADDRHI=ADDRLO+(255-SHORTMAX)*256;SHIFT=((ADDRLO>>8)-(SHORTMAX+1))&255;assert ADDRLO%256==0 and ADDRHI<=65536;')
(R/'layout_builder.py').write_text(s)

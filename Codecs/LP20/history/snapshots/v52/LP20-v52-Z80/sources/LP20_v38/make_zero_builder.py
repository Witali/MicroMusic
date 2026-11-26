from pathlib import Path
R=Path(__file__).resolve().parent
s=(R/'packed_builder.py').read_text()
# Eight active banks: pages 1..8 and 9..16. Sentinel bank 0 may read arbitrary
# ROM words during the discarded calculation; force the accumulator to zero.
s=s.replace('elif ALIAS8:\n    op(4,','elif ALIAS8:\n    op(7,\'add a,8\',0xc6,8)\n   elif False:\n    op(4,',1)
s=s.replace(" op(4,'ex de,hl',0xeb)\n # Round once", " if ALIAS8:g(36,'zero_guard')\n op(4,'ex de,hl',0xeb)\n # Round once",1)
s=s.replace(" if k=='fetch_ctx_a':", " if k=='zero_guard':\n  zero=im.name('zero');join=im.name('join');z('ld a,i',0xed,0x57);z('and 15',0xe6,15);im.jp(zero,'z');im.jp(join);im.lab(zero);z('ld de,0',0x11,0,0);im.lab(join)\n elif k=='fetch_ctx_a':",1)
s=s.replace('DP=2*NB+1-int(ALIAS_ZERO or ALIAS8);','DP=2*NB+1-int(ALIAS_ZERO or ALIAS8)-int(ALIAS8);')
s=s.replace('9 if ALIAS8 else 1','0 if ALIAS8 else 1')
s=s.replace('elif ALIAS8:tab=tab[256:9*256]+tab[:256]+tab[10*256:]','elif ALIAS8:tab=tab[256:9*256]+tab[10*256:]')
s=s.replace('range(NB+1,DP)','range(NB+1-int(ALIAS8),DP)')
s=s.replace('lpc_tables=NB*512-256*int(ALIAS_ZERO or ALIAS8)','lpc_tables=NB*512-256*int(ALIAS_ZERO or ALIAS8)-256*int(ALIAS8)')
(R/'zero_builder.py').write_text(s)

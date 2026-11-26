#!/usr/bin/env python3
"""Cross-recording scalar quantizer grid check (no new voices, no coefficient retuning)."""
from grid51 import *

def main():
 lib=s50.library();ds={c:s50.load(c) for c in ('first','second')};rows=[]
 for c in ds:
  d,m,r,z=ds[c];other='second' if c=='first' else 'first';zo=ds[other][-1];old={sum(v):v for v in m['patterns'].values()}
  for nm,g in [('cross-.005',s50.select(lib,255,1,zo,.005)),('cross-.02',s50.select(lib,255,1,zo,.02)),('cross-.12',s50.select(lib,255,1,zo,.12)),('power1.4',s50.select(lib,255,1.4)),('power2.0',s50.select(lib,255,2.0))]:
   p=np.array([old[int(s)] if int(s) in old else lib[int(s)] for s in g],np.int16);a=evaluate(r,render_new(z,d,p));row=dict(clip=c,profile=nm,snr_db=float(a['snr_db']),peak_error_pct=float(a['peak_error_pct']),p999_pct=float(a['p999_pct']));rows.append(row);print(row,flush=True)
  (ROOT/'grid-cross.json').write_text(json.dumps(rows,indent=2))
if __name__=='__main__':main()

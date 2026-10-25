#!/usr/bin/env python3
"""Certify redundant NB3 margins and exact signed16 paired averages.

An affine form over the original 64*64*64 codebook is separable into one
base, one low and one high correction. Its exact maximum is three 64-way
maxima plus the fixed linear term. Every convex interpolation has the same
upper bound. Endpoint multiples of 16 give multiple-of-four quarter states.

Only upper(3), lower(4), upper(4), lower(5) can affect output. To exclude the
upper check at index 5, write x for raw and y for corrected output:
 y3 <= x3; y4 <= max((x4+x5-16)/2, x3+16).
 Before its upper check, y5 <= max(x5,(x4+x5+16)/2,x3+32).
 Thus y5+16-x6 is bounded by the three certificates named gap-5,
 propagation-average and propagation-previous. All are negative. The next
 lower check is also redundant, then positive gaps exclude all later ones.

The two surviving upper/lower pairs share predicates: their incoming values
are even, so a>b-16 implies average(a,b-16)+16>b, and conversely. The extra
nonadjacent gap excludes simultaneous repairs. Either average therefore
uses multiple-of-four raw inputs and remains even. The three sum
certificates keep a+(b-16) and b+(c-16) inside signed16.
General interpolation outside this pinned domain must retain both shifts.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
TABLE=ROOT/'vendor/speex-1.2.1/libspeex/lsp_tables_nb.c'
def canonical_hash(p):return hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
def prove():
    source=TABLE.read_text()
    def table(name,size):
        a=[int(v) for v in re.search(name+r'\[\d+\]=\{([^}]+)\}',source)[1].split(',') if v.strip()]
        assert len(a)==size;return a
    base,low,high=table('cdbk_nb',640),table('cdbk_nb_low1',320),table('cdbk_nb_high1',320)
    def maximum(w,c):
        fixed=c+sum(w[i]*(i+1)*2048 for i in range(10))
        return fixed+max(sum(w[i]*32*base[10*k+i] for i in range(10)) for k in range(64))+\
            max(sum(w[i]*16*low[5*k+i] for i in range(5)) for k in range(64))+\
            max(sum(w[i+5]*16*high[5*k+i] for i in range(5)) for k in range(64))
    forms=[]
    def form(name,terms,constant,limit):
        w=[terms.get(i,0) for i in range(10)];value=maximum(w,constant);assert value<=limit,name
        forms.append(dict(name=name,weights=w,constant=constant,maximum=value,requiredUpperBound=limit))
    for i in range(9):form('gap-'+str(i),{i:1,i+1:-1},16,0 if i not in (3,4) else 32767)
    form('propagation-average',{4:1,5:1,6:-2},48,0)
    form('propagation-previous',{3:1,6:-1},48,0)
    form('repair-exclusion',{3:1,5:-1},32,0)
    form('first-average-sum',{3:1,4:1},-16,32767)
    form('second-average-raw-sum',{4:1,5:1},-16,32767)
    form('second-average-raised-sum',{3:1,5:1},0,32767)
    assert len(forms)==15
    return dict(profile='Pinned Xiph Speex 1.2.1 NB3; order 10; four exact quarters; margin 16',
        domain='Convex combinations of codebook endpoints; quarter raw state is a multiple of four',
        source='vendor/speex-1.2.1/libspeex/lsp_tables_nb.c',sourceSha256=canonical_hash(TABLE),
        proverSha256=canonical_hash(Path(__file__)),sourceHashNormalization='LF',codebookTriples=262144,
        endpointRange=[96,24880],survivingChecks=['upper-3','lower-4','upper-4','lower-5'],
        pairedRepairs=2,mutuallyExclusiveRepairs=True,certificates=forms,
        provenance='Original bound analysis; Xiph codebook copyright/license retained in vendor/speex-1.2.1/COPYING')
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,default=ROOT/'reports/margin-proof.json')
    p.add_argument('--check',action='store_true');args=p.parse_args();data=prove()
    if args.check:assert json.loads(args.out.read_text())==data,'Stored geometry proof is stale'
    else:args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(data,indent=2)+'\n')
    print('PASS: 15 exact affine certificates; two mutually exclusive NB3 repairs; signed16 sums bounded')
if __name__=='__main__':main()

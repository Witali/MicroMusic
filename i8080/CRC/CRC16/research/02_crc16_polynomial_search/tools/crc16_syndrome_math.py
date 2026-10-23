#!/usr/bin/env python3
"""Exact undetected 2-bit and 3-bit error enumerations for 16-bit CRC on fixed codeword lengths.

Uses every bit error syndrome x^i mod G(x), and an XOR Walsh-Hadamard
transform to count triples.  Works without probabilistic simulation.
"""
import csv
import math
import argparse
from pathlib import Path

POLY = (0x0007,0x0009,0x001b,0x002d,0x0031,0x0039,0x1021,0x8005)

def period(poly):
    v=1
    for k in range(1,65536):
        v = ((v << 1) ^ (poly if v & 0x8000 else 0)) & 0xffff
        if v == 1:
            return k
    raise ValueError('No multiplicative order found')

def fwht(a):
    import numpy as np
    a=a.astype(np.int64,copy=True)
    n=len(a); step=1
    while step<n:
        b=a.reshape(-1,2*step)
        x=b[:,:step].copy()
        y=b[:,step:].copy()
        b[:,:step]=x+y
        b[:,step:]=x-y
        step*=2
    return a

def undetected_error_counts(poly,n):
    import numpy as np
    freq=np.zeros(65536,dtype=np.int64)
    v=1
    for _ in range(n):
        freq[v]+=1
        v=((v<<1)^(poly if v&0x8000 else 0))&0xffff
    pair_count=int(np.dot(freq, freq) - n)//2
    f=fwht(freq)
    triple_ord=int(np.sum(f*f*f,dtype=np.int64))//65536
    assert triple_ord%6==0
    return pair_count, triple_ord//6

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--bytes',type=int,default=65536)
    p.add_argument('--output',type=Path)
    args=p.parse_args(); n=args.bytes*8
    records=[]
    print('Polynomials; codeword bits',n)
    for poly in POLY:
        pair,triple=undetected_error_counts(poly,n)
        row={'poly':f'0x{poly:04X}','period':period(poly),
             'detects_all_odd_errors':bool((poly.bit_count()&1)),
             'undetected_2bit':pair,'possible_2bit':math.comb(n,2),
             'undetected_3bit':triple,'possible_3bit':math.comb(n,3),
             'fraction_2bit':pair/math.comb(n,2),
             'fraction_3bit':triple/math.comb(n,3)}
        records.append(row)
        print(row['poly'],'period',row['period'],'pairs',pair,'triples',triple,
              '2-bit chance',f"{row['fraction_2bit']:.9g}",
              '3-bit chance',f"{row['fraction_3bit']:.9g}")
        # Cross-check pair count against the analytical period formula.
        per=period(poly)
        assert pair == sum(n-d for d in range(per,n,per))
        if poly.bit_count()&1: assert triple == 0
    if args.output:
        with args.output.open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=records[0].keys())
            writer.writeheader();writer.writerows(records)

if __name__=='__main__':main()

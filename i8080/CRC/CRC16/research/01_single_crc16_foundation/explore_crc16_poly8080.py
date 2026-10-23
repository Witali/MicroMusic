#!/usr/bin/env python3
"""Search a small, structured class of polynomial CRCs for Intel 8080.

Not proof of global optimality: compares binomial products and trinomials only.
"""
def period(poly):
    s=1
    for j in range(1,65536):
        s=((s<<1)^(poly if s&0x8000 else 0))&0xffff
        if s==1: return j
    raise AssertionError('No cycle')

print('Trinomials x^16+x^k+1:')
for k in range(1,9):
    p=(1<<k)|1
    print(f'  k={k}: poly=0x{p:04X}, order={period(p)}')
print('Products (1+x^a)(1+x^b), a<b<=8 with maximal period:')
for a in range(1,9):
    for b in range(a+1,9):
        p=(1^(1<<a)^(1<<b)^(1<<(a+b)))
        if p >= 65536:continue
        if period(p)==65535:
            print(f'  a={a}, b={b}, shifts={a+b}, poly=0x{p:04X}')

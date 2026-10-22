#!/usr/bin/env python3
"""Independent GF(2) properties of dual CRC16 (0x0025 + 0x0047)."""
from math import lcm

def mul(a,b):
    result=0
    while b:
        if b&1:result^=a
        a<<=1;b>>=1
    return result

def mod(a,g):
    while a.bit_length()>=g.bit_length():
        a ^= g << (a.bit_length()-g.bit_length())
    return a

def gcd(a,b):
    while b:a,b=b,mod(a,b)
    return a

def period(poly):
    state=1
    for n in range(1,65536):
        state=((state<<1)^(poly if state&0x8000 else 0))&65535
        if state==1:return n
    raise AssertionError('Unexpected period')

G25,G47=0x10025,0x10047
G=mul(G25,G47)
p25,p47=period(0x25),period(0x47)
assert G==0x1006209BB
assert gcd(G25,G47)==1
assert (p25,p47)==(1023,21845)
assert lcm(p25,p47)==22347435>524288-1
assert (G25.bit_count()&1)==0  # factor x+1: guarantees all odd-weight errors
witness=(0,1065,1278,3920)
poly_error=0
for p in witness:poly_error^=1<<p
assert mod(poly_error,G)==0
print('G25:',hex(G25),'G47:',hex(G47),'product:',hex(G))
print('gcd=1, periods:',p25,p47, 'lcm:',lcm(p25,p47))
print('All 1-bit, 2-bit, 3-bit and arbitrary odd-weight errors detected (64 KiB).')
print('All bursts 1..32 bits detected.')
print('Known undetectable 4-bit witness:',witness,'span',witness[-1]+1,'bits')
print('PASS: mathematical checks')

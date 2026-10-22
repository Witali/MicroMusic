#!/usr/bin/env python3
"""Independent GF(2) analysis for dual-CRC polynomials and witness errors."""
import math

def multiply(a,b):
    r=0
    while b:
        if b&1:r^=a
        b >>=1;a<<=1
    return r

def remainder(a,b):
    while a and a.bit_length()>=b.bit_length():a ^= b << (a.bit_length()-b.bit_length())
    return a

def gcd(a,b):
    while b:a,b=b,remainder(a,b)
    return a

def period(poly):
    v=1
    for j in range(1,65536):
        v=((v<<1)^ (poly if v&0x8000 else 0))&0xFFFF
        if v==1:return j
    raise AssertionError('period missing')

def syndrome(poly,offset):
    cur=1
    for _ in range(offset):cur=((cur<<1) ^ (poly if cur&0x80000000 else 0))&0xffffffff
    return cur

N=524288
G1=0x10007
G2_old=0x10009
G2_new=0x10021
Qold=multiply(G1,G2_old)
Qnew=multiply(G1,G2_new)
assert gcd(G1,G2_new)==1
assert Qold==0x1000E003F and Qnew==0x1002600E7
P1=period(7);P2_old=period(9);P2_new=period(0x21)
assert (P1,P2_old,P2_new)==(32767,57337,16383)
assert math.lcm(P1,P2_new)>N-1
assert G1.bit_count()%2==0 # x+1 factor => detects all odd-weight errors
old_witness=(0,777,1076,2007)
new_witness=(0,1968,2021,3224)
for name,q,w in [('old',Qold,old_witness),('new',Qnew,new_witness)]:
    err=0
    for position in w:err ^= 1 << position
    assert remainder(err,q)==0,(name,w)
assert remainder(sum(1<<i for i in old_witness),Qnew)!=0
# All 32-or-fewer-bit bursts detected for any 32-bit monic generator with constant 1.
print('Coprime polynomials:',hex(G1),hex(G2_new))
print('Product Q=',hex(Qnew),'poly32=',hex(Qnew&0xffffffff))
print('Periods old:',P1,P2_old,'LCM:',math.lcm(P1,P2_old))
print('Periods new:',P1,P2_new,'LCM:',math.lcm(P1,P2_new))
print('Old 4-bit undetected witness',old_witness,'not missed by new pair: PASS')
print('New 4-bit undetected witness',new_witness,'span',new_witness[-1]+1,': PASS')
print('Guaranteed at 65536 bytes: all 1-, 2-, 3-bit errors; all odd parity errors and <=32-bit bursts')

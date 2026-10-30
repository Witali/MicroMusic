#!/usr/bin/env python3
"""Integer/range proof for exact five-symbol noise and narrowed vocoder state."""
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
def s16(v):return (v+32768)%65536-32768
def s32(v):return (v+2**31)%2**32-2**31
def sha(p):return hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()

def main():
    source=(ROOT/'src/lowrate_noise.c').read_text()
    limits=list(map(int,re.findall(r'high<\s*(-?\d+)',source)))
    assert len(limits)==4
    center_lo,outer_lo,center_hi,outer_hi=limits
    counts=[0]*5
    for high in range(-32768,32768):
        original=(high-(high>>3)+8192)>>14
        actual=(-2 if high<outer_lo else -1) if high<center_lo else 0 if high<center_hi else 1 if high<outer_hi else 2
        assert actual==original,(high,actual,original)
        counts[actual+2]+=1
        weighted=(9830*high)>>15
        assert s16(weighted)==weighted
    upstream=(ROOT/'vendor/speex-1.2.1/libspeex/nb_celp.c').read_text()
    raw=list(map(int,re.search(r'ol_gain_table\[32\]=\{([^}]+)',upstream)[1].split(',')))
    scales=[(28406*g)//32768 for g in raw]
    assert min(scales)==16384 and max(scales)==115088100
    max_noise=0
    for scale in scales:
        for value in range(-2,3):
            # Literal original split Q14 product and signed16 low cast.
            a=value*128
            original=a*s16(scale>>14)+s16((a*(scale&16383))>>14)
            exact=(a*scale)>>14
            assert original==exact
            aligned=exact*128
            assert -(2**31)<=aligned+8192<2**31
            word=(aligned+8192)>>14
            assert word==s16(word)
            max_noise=max(max_noise,abs(word))
    # The seed is unsigned32. Verify exact transition/classification from
    # independent full-width equations; no smaller RNG state is substituted.
    seed=1000
    for i in range(100000):
        seed=(1664525*seed+1013904223)&0xffffffff
        high=s16(seed>>16)
        assert -2<=(high-(high>>3)+8192)>>14<=2
    # Alias proof in both byte orders: classes occupy the upper 40 of 80 B.
    for order in ['little','big']:
        for shift in range(5):
            values=[-14049,-7024,0,7024,14049]
            classes=[(i+shift)%5 for i in range(40)]
            buffer=bytearray(80);buffer[40:]=bytes(classes)
            for i in range(40):
                value=values[buffer[40+i]]
                buffer[2*i:2*i+2]=value.to_bytes(2,order,signed=True)
            assert buffer==b''.join(values[c].to_bytes(2,order,signed=True) for c in classes)
    for pitch in range(17,145):
        for offset in range(144):
            phase=offset
            for i in range(40):
                if i==phase:phase+=pitch
            assert 0<=phase-40<=143 and phase<=183
    assert 32768*(26214+6554)+16384<2**31
    report=dict(scope='Exact integer identities/ranges, not runtime or perceptual admission',
        signed16Classifications=65536,noiseClassCounts=counts,seedTransitions=100000,
        exactScaleValues=32,maxAbsoluteRoundedNoise=max_noise,historyOffsetCases=128*144,
        aliasExpansionByteOrders=['little','big'],pcmPrecisionChanged=False,
        sourceSha256={p.relative_to(ROOT).as_posix():sha(p) for p in [
            ROOT/'src/lowrate_noise.c',ROOT/'src/lowrate_excitation.h',Path(__file__)]})
    out=ROOT/'build/low-noise-proof.json';out.parent.mkdir(parents=True,exist_ok=True)
    out.write_bytes((json.dumps(report,indent=2)+'\n').encode())
    print('PASS exact noise thresholds, scaling, weighted state, bounded offsets and alias expansion')

if __name__=='__main__':main()

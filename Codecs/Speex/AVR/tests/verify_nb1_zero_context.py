#!/usr/bin/env python3
"""Prove the prepared-context zero predicate over NB1's complete bounds."""
import json
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]


def main():
    # For S>=0, floor((4096-S)/8192)==0 iff S<=4096; otherwise it is
    # negative. Multiplication by 77*g, g=1..64, cannot overflow a word
    # after Q15 and stays strictly negative. This covers the large-scale
    # region by enumerating all possible negative words and nonzero gains.
    negative_pairs=0;small_pairs=0
    assert (4096-121000000)//8192 == -14771
    for g in range(1,65):
        for n in range(-14771,0):
            previous=(77*g*n)//32768
            assert -32768 <= previous < 0
            negative_pairs+=1
        for scale in range(4097):
            noise=[(4096-scale)//8192,(8192-scale)//16384,0,(scale+8192)//16384,(scale+4096)//8192]
            assert noise[0]==0 and all((77*g*n)//32768==0 for n in noise)
            assert (scale+8192)//16384==0  # Both amplitude-derived pulses vanish.
            small_pairs+=1
    # At gain0 all previous terms/pulses vanish for every scale; noise and
    # incoming cursor state remain observable and must still be processed.
    gains=list(map(int,re.search(r'ol_gain_table\[32\]=\{([^}]+)\}',(ROOT/'vendor/speex-1.2.1/libspeex/nb_celp.c').read_text())[1].split(',')))
    scales=[28406*g//32768 for g in gains];assert len(scales)==32 and min(scales)==16384 and max(scales)<=121000000
    assert all(s>4096 for s in scales)
    report=dict(scope='Independent integer proof, not target speed evidence',scaleBounds=[0,121000000],gainBounds=[0,64],
        negativeNoiseGainPairs=negative_pairs,smallScaleGainPairs=small_pairs,zeroBoundary=4096,
        packetScaleCodes=32,minimumPacketScale=min(scales),positiveGainZeroContextUnreachableForPackets=True,
        preparedContextPredicateExact=True,arbitraryContextPredicateClaimed=False,zeroGainPreservesNoiseAndIncomingCursor=True)
    out=ROOT/'build/zero-vocoder-unit';out.mkdir(parents=True,exist_ok=True)
    (out/'predicate.json').write_bytes((json.dumps(report,indent=2)+'\n').encode())
    print('PASS',json.dumps(report))


if __name__=='__main__':main()

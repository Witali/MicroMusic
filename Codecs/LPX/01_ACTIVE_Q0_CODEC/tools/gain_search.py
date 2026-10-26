"""Host-only gain proposals using existing excitation scale fields.

Copy the spectral/excitation payload, including sparse modes, and change only
scale codewords. Fixed-point rounding and clipping prevent assuming exact
waveform scaling: callers must decode and evaluate the resulting stream.
"""
import numpy as np
from lpx4 import BitWriter,decode
from lossless_repack import layout,copy_bits,scale_cost
from rice_v4_reference import write_scale
from q0_model import table
from perceptual_rate import expanded_v2
from compact_format import pack


def search_upshift(reference):
    peak=int(np.max(np.abs(np.asarray(reference,dtype=np.int64))))
    shift=0
    if peak:
        while shift<14 and peak*(1<<(shift+1))<=32767:shift+=1
    return shift


def rescale_excitation(blob,downshift):
    if not isinstance(downshift,int) or not 0<=downshift<=15:
        raise ValueError('Expected a bounded integer downshift')
    if not downshift:return blob
    expanded=expanded_v2(blob);frames,blocks,q,spans=layout(expanded)
    steps=table('scale_table.inc');writer=BitWriter();previous=0;cursor=160
    for block,span in zip(blocks,spans):
        if not any(block['q']):value=previous
        else:
            wanted=float(steps[block['scale']])/(1<<downshift)
            minimum=1 if wanted>0 else 0
            distance=np.abs(steps.astype(float)-max(minimum,wanted));distance[steps<minimum]=np.inf
            choices=np.flatnonzero(distance==np.min(distance))
            value=min(map(int,choices),key=lambda i:(int(scale_cost(previous,i)),abs(i-(block['scale']-16*downshift)),i))
        copy_bits(writer,expanded,cursor,span.scale_start);write_scale(writer,previous,value)
        previous=value;cursor=span.scale_end
    copy_bits(writer,expanded,cursor,spans[-1].end);writer.aligned()
    result=expanded[:20]+writer.get()
    if blob[4]==3:result=pack(result,blob[5]&124)[0]
    new_frames,new_blocks,new_q=decode(result)
    if new_frames!=frames or new_q!=q or [b['bits'] for b in new_blocks]!=[b['bits'] for b in blocks]:
        raise AssertionError('Gain proposal changed spectral or excitation codes')
    return result

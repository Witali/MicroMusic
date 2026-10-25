#!/usr/bin/env python3
"""Stress the heaviest measured LPX comparison stream, with active IRQ."""
import argparse
import json
from pathlib import Path
import struct
import numpy as np
from batch_decoder import BatchSession
from benchmark_standards import save,sha,compact
from lpx4 import decode,encode
from lossless_repack import optimize_scales,optimize_excitation
from profile_avr import run as profile
from q0_model import decode_pcm16


def run(results,verification,output,avr_bin,runner,lib=None,wsl=None):
    results,output=Path(results),Path(output);output.mkdir(parents=True,exist_ok=True)
    previous=json.loads(Path(verification).read_text(encoding='utf-8'))
    digest,measured=max(previous['images'].items(),key=lambda kv:kv[1]['mean_decode_wall_cycles'])
    case,point=next((case,point) for case in previous['cases'] for point in case['rates'] if point['stream_sha256']==digest)
    source=results/case['id']/str(point['ceiling_bps'])/'selected.l4hy';blob=source.read_bytes()
    if sha(blob)!=digest:raise ValueError('Worst input changed')
    frames,blocks,q=decode(blob);raw=bytearray(blob[:20]);raw[:6]=b'L3AV\x01\x03';struct.pack_into('<I',raw,8,len(q)*2)
    packed=encode({'raw':bytes(raw),'frames':frames*2,'blocks':blocks*2},fast=True)[0]
    with BatchSession('batch',v3_features=124) as decoder:
        packed,_=optimize_scales(packed,decoder);packed,_=optimize_excitation(packed,decoder)
        packed,_=compact(packed)
        native=decoder.decode_one_s16(packed,len(q)*2)
        if native is None or not np.array_equal(native,decode_pcm16(packed)):raise AssertionError('Long native/model mismatch')
    path=output/'repeated.l4hy';path.write_bytes(packed)
    report={'source_case':case['id'],'source_ceiling_bps':point['ceiling_bps'],'source_sha256':digest,
        'source_mean_decode_cycles':measured['mean_decode_wall_cycles'],
        'recipe':'Repeat decoded LSF frames and q/scale blocks twice; repack exact modes with continuous decoder state. '
                 'This is an 8-second workload, not a new independent quality reference or a reset at the join.',
        'repeated_sha256':sha(packed),'native_pcm16_sha256':sha(native.astype('<i2').tobytes()),
        'native_model_exact':True,'profiles':[]}
    settings=[('normal',512,384,9,0),('compact',256,160,3,0),
              ('load50',512,384,9,50),('load100',512,384,9,100)]
    for name,queue,prefill,unroll,load in settings:
        r=profile(path,output/name,avr_bin,runner,lib,wsl,enable_asm=True,v3_features=24,
                  queue=queue,prefill=prefill,dot_unroll=unroll,irq_load=load)
        report['profiles'].append({'name':name,**r});save(output/'verification.json',report)
        print(name,r['mean_decode_wall_cycles']/20,'percent',r['underruns'],'underruns',flush=True)
    return report


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('results','verification','output'):ap.add_argument(name,type=Path)
    ap.add_argument('--avr-bin',type=Path,required=True);ap.add_argument('--sim-runner',type=Path,required=True)
    ap.add_argument('--sim-lib-dir',type=Path);ap.add_argument('--wsl')
    a=ap.parse_args();run(a.results,a.verification,a.output,a.avr_bin,a.sim_runner,a.sim_lib_dir,a.wsl)

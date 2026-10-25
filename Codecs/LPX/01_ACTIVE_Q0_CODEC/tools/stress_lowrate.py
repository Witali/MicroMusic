"""Repeat the heaviest admitted final low-rate stream for full AVR timing."""
import argparse,json,struct
from pathlib import Path
import numpy as np
from batch_decoder import BatchSession
from benchmark_standards import save,sha
from lpx4 import decode,encode
from lossless_repack import optimize_scales,optimize_excitation
from compact_format import pack
from q0_model import decode_pcm16
from profile_avr import run as profile


def run(results,verification,output,avr_bin,runner,lib=None,wsl=None):
    results,output=Path(results),Path(output);output.mkdir(parents=True,exist_ok=True)
    previous=json.loads(Path(verification).read_text(encoding='utf-8'))
    points=[(c,p) for c in previous['cases'] for p in c['points'] if p['stage'] in ('joint','perceptual') and p['avr_admitted']]
    case,point=max(points,key=lambda cp:previous['images'][cp[1]['stream_sha256']]['mean_decode_wall_cycles'])
    digest=point['stream_sha256'];source=json.loads((results/case['id']/'complete.json').read_text(encoding='utf-8'))
    item=next(r for r in source['rates'] if r['ceiling_bps']==point['ceiling_bps'])[point['stage']]
    blob=Path(item['path']).read_bytes()
    if sha(blob)!=digest:raise ValueError('Source changed')
    frames,blocks,q=decode(blob);raw=bytearray(blob[:20]);raw[:6]=b'L3AV\x01\x03';struct.pack_into('<I',raw,8,len(q)*2)
    repeated=encode({'raw':bytes(raw),'frames':frames*2,'blocks':blocks*2},fast=True)[0]
    with BatchSession('batch',v3_features=24) as decoder:
        repeated,_=optimize_scales(repeated,decoder);repeated,_=optimize_excitation(repeated,decoder)
        other,_=pack(repeated,24)
        if len(other)<len(repeated):repeated=other
        native=decoder.decode_one_s16(repeated,len(q)*2)
        if native is None or not np.array_equal(native,decode_pcm16(repeated)):raise AssertionError('Repeated native/model mismatch')
    path=output/'repeat.l4hy';path.write_bytes(repeated)
    report={'source_case':case['id'],'source_stage':point['stage'],'source_ceiling_bps':point['ceiling_bps'],
      'source_sha256':digest,'source_mean_decode_cycles':previous['images'][digest]['mean_decode_wall_cycles'],
      'recipe':'Repeat decoded LSF/q/scale blocks twice with continuous state, exact repacking; an 8s timing workload, not a new independent quality reference.',
      'repeated_sha256':sha(repeated),'native_pcm16_sha256':sha(native.astype('<i2').tobytes()),
      'native_model_exact':True,'profiles':[]}
    for name,assembly,load in [('normal',True,0),('extra_irq100',True,100),('c_fallback',False,0)]:
        p=profile(path,output/name,avr_bin,runner,lib,wsl,enable_asm=assembly,irq_load=load,v3_features=24)
        report['profiles'].append({'name':name,**p});save(output/'verification.json',report)
        print(name,p['mean_decode_wall_cycles']/20,'decode percent',p['underruns'],'underruns',flush=True)
    return report


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('results','verification','output'):ap.add_argument(name,type=Path)
    ap.add_argument('--avr-bin',type=Path,required=True);ap.add_argument('--sim-runner',type=Path,required=True)
    ap.add_argument('--sim-lib-dir',type=Path);ap.add_argument('--wsl')
    a=ap.parse_args();run(a.results,a.verification,a.output,a.avr_bin,a.sim_runner,a.sim_lib_dir,a.wsl)

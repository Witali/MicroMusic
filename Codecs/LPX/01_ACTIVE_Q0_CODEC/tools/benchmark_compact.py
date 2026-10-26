#!/usr/bin/env python3
"""Measure compact-container payload, total ELF, RAM and active-IRQ timing."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from compact_format import pack
from batch_decoder import BatchSession
from profile_avr import run as profile


def run(inputs,output,report_path,features,avr_bin,runner,lib=None,wsl=None,**settings):
    output,report_path=Path(output),Path(report_path)
    output.mkdir(parents=True,exist_ok=True);report_path.parent.mkdir(parents=True,exist_ok=True)
    report={'physical_hardware_measured':False,'feature_masks':list(features),'cases':[]}
    with BatchSession('batch',v3_features=124) as dec:
        for source in sorted(map(Path,inputs)):
            key=source.parent.name;folder=output/key;folder.mkdir(exist_ok=True)
            blob=source.read_bytes();samples=int.from_bytes(blob[8:12],'little')
            expected=dec.decode_one_s16(blob,samples)
            base=folder/'baseline.l4hy';base.write_bytes(blob)
            before=profile(base,folder/'avr-baseline',avr_bin,runner,lib,wsl,enable_asm=True,**settings)
            item={'id':key,'source_sha256':hashlib.sha256(blob).hexdigest(),'before':before,'variants':[]}
            for mask in features:
                packed,stats=pack(blob,mask)
                actual=dec.decode_one_s16(packed,samples)
                if actual is None or expected is None or not np.array_equal(actual,expected):
                    raise AssertionError('Compact native PCM16 changed')
                path=folder/f'features-{mask}.l4hy';path.write_bytes(packed)
                after=profile(path,folder/f'avr-{mask}',avr_bin,runner,lib,wsl,enable_asm=True,v3_features=mask,**settings)
                stats.update(input_sha256=hashlib.sha256(blob).hexdigest(),output_sha256=hashlib.sha256(packed).hexdigest(),
                             native_pcm16_exact=True,pcm16_sha256=hashlib.sha256(actual.astype('<i2').tobytes()).hexdigest())
                item['variants'].append({'packing':stats,'avr':after,
                    'flash_saved':before['flash_bytes']-after['flash_bytes'],
                    'decoder_flash_added':(after['flash_bytes']-len(packed))-(before['flash_bytes']-len(blob)),
                    'strict_time_accepted':after['underruns']==0 and after['mean_decode_wall_cycles']<=before['mean_decode_wall_cycles']
                        and after['decode_wall_cycles_max_160']<=before['decode_wall_cycles_max_160']})
                print(key,mask,len(blob),'->',len(packed),'ELF',before['flash_bytes'],'->',after['flash_bytes'],
                      'cycles',round(before['mean_decode_wall_cycles'],2),'->',round(after['mean_decode_wall_cycles'],2),flush=True)
            report['cases'].append(item)
            report_path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('inputs',nargs='+',type=Path);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--report',type=Path,required=True);ap.add_argument('--features',nargs='+',type=int,required=True)
    ap.add_argument('--avr-bin',type=Path,required=True);ap.add_argument('--sim-runner',type=Path,required=True)
    ap.add_argument('--sim-lib-dir',type=Path);ap.add_argument('--wsl')
    args=ap.parse_args();run(args.inputs,args.output,args.report,args.features,args.avr_bin,args.sim_runner,args.sim_lib_dir,args.wsl)

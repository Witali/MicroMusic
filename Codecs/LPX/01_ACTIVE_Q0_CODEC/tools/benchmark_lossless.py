#!/usr/bin/env python3
"""Compare lossless repacks on existing streams with full AVR IRQ timing.

Inputs are read from another directory. Only numeric reports are retained in
research; media and ELF files belong in an ignored build directory.
"""
import argparse
import hashlib
import json
from pathlib import Path
from batch_decoder import BatchSession
from lossless_repack import optimize
from profile_avr import run as profile


def run(inputs, output, report_path, avr_bin, runner, lib=None, wsl=None, stage='scale'):
    output, report_path = Path(output), Path(report_path)
    output.mkdir(parents=True, exist_ok=True); report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {'stage':stage, 'contract':'identical native PCM16 and AVR PWM; full active-IRQ firmware',
              'physical_hardware_measured':False, 'cases':[]}
    with BatchSession('batch') as decoder:
        for source in sorted(map(Path, inputs)):
            key = source.parent.name
            folder = output/key; folder.mkdir(exist_ok=True)
            blob = source.read_bytes()
            candidate, search = optimize(blob, decoder, stage)
            paths = [folder/'baseline.l4hy', folder/'candidate.l4hy']
            for path, data in zip(paths, (blob,candidate)): path.write_bytes(data)
            timings = []
            for index,path in enumerate(paths):
                if index and candidate == blob: timings.append(timings[0]); continue
                timings.append(profile(path, folder/('avr-'+str(index)), avr_bin, runner, lib, wsl, enable_asm=True))
            a,b = timings
            accepted = (b['underruns'] == 0 and b['flash_bytes'] <= a['flash_bytes'] and
                        b['static_sram_bytes'] <= a['static_sram_bytes'] and
                        b['mean_decode_wall_cycles'] <= a['mean_decode_wall_cycles'] and
                        b['decode_wall_cycles_max_160'] <= a['decode_wall_cycles_max_160'])
            report['cases'].append({'id':key, 'source_sha256':hashlib.sha256(blob).hexdigest(),
                'search':search, 'before':a, 'candidate':b, 'accepted_strict_timing':accepted})
            report_path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
            print(key,len(blob),'->',len(candidate),'cycles',round(a['mean_decode_wall_cycles'],2),
                  '->',round(b['mean_decode_wall_cycles'],2),'strict',accepted,flush=True)
    return report


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('inputs', type=Path, nargs='+'); ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--report',type=Path,required=True); ap.add_argument('--avr-bin',type=Path,required=True)
    ap.add_argument('--sim-runner',type=Path,required=True); ap.add_argument('--sim-lib-dir',type=Path)
    ap.add_argument('--wsl');ap.add_argument('--stage',choices=('scale','excitation','all'),default='all')
    args=ap.parse_args()
    run(args.inputs,args.output,args.report,args.avr_bin,args.sim_runner,args.sim_lib_dir,args.wsl,args.stage)

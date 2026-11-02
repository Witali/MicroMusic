"""Replay private final 2/3 kbit/s selections on the complete Tiny88 player.

Media and bindings remain in ignored build/. Retain only summary.json: anonymous
ordinals, numerical measurements and source hashes, without media fingerprints.
The 8192-byte experiment cap is separate from the 6656-byte release admission.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import sys
import traceback

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from verify_attiny88_player import verify


def sha(data):return hashlib.sha256(data).hexdigest()


def run(manifest_path,output,*,wsl=None,jobs=2):
    manifest_path=Path(manifest_path).resolve();output=Path(output).resolve()
    if REPO/'build' not in output.parents:raise ValueError('Use ignored repository build storage')
    if not 1<=jobs<=4:raise ValueError('Use 1..4 workers')
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'));base=manifest_path.parent
    if manifest.get('schema')!='lpx-final-corpus-firmware-inputs-private-v1':raise ValueError('Unknown replay manifest')
    entries=manifest['jobs']
    if len(entries)!=manifest['job_count'] or not entries:raise ValueError('Incomplete replay manifest')
    output.mkdir(parents=True,exist_ok=True)
    sources=[*sorted((ROOT/'src').glob('Lpx4*')),ROOT/'profiles/Lpx4Sram512.h',
             ROOT/'examples/ATTINY88_V5_PLAYER/player.cpp',ROOT/'tools/build_attiny88_player.py',
             ROOT/'tools/verify_attiny88_player.py',ROOT.parent/'validation/attiny88/sim_player.c',Path(__file__)]
    hashes={str(p.relative_to(REPO)):sha(p.read_bytes()) for p in sources}
    def check(entry):
        rate=entry['kbps'];ordinal=entry['ordinal']
        folder=output/('case-'+str(ordinal).zfill(3)+'-rate-'+str(rate))
        if rate not in (2,3) or type(ordinal) is not int or ordinal<0:raise ValueError('Invalid case')
        stream=(base/entry['stream_file']).resolve();oracle=(base/entry['expected_pwm8_file']).resolve()
        if base not in stream.parents or base not in oracle.parents:raise ValueError('Replay path escapes manifest directory')
        blob=stream.read_bytes();expected=oracle.read_bytes()
        if sha(blob)!=entry['stream_sha256'] or sha(expected)!=entry['expected_pwm8_sha256']:
            raise ValueError('Private replay binding mismatch')
        if len(blob)!=entry['encoded_bytes'] or len(expected)!=entry['samples']:
            raise ValueError('Private replay length mismatch')
        measured=verify(stream,folder,wsl=wsl,sparse80=rate==2,flash_limit=8192)
        # Independent frozen oracle checks both current portable C and actual AVR.
        exact=(folder/'expected.pwm').read_bytes()==expected and (folder/'actual.pwm').read_bytes()==expected
        row=dict(ordinal=ordinal,kbps=rate,**measured,independent_pwm_exact=exact,
                 release_flash_limit=6656,release_accepted=bool(measured['accepted'] and exact and measured['flash_bytes']<=6656))
        if not exact:row['accepted']=False
        return row
    rows=[]
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures={pool.submit(check,e):e for e in entries}
        for future in as_completed(futures):
            entry=futures[future]
            try:row=future.result()
            except Exception as error:
                (output/('failure-'+str(entry['ordinal'])+'-'+str(entry['kbps'])+'-private.log')).write_text(traceback.format_exc(),encoding='utf-8')
                row=dict(ordinal=entry['ordinal'],kbps=entry['kbps'],accepted=False,error_type=type(error).__name__)
            rows.append(row)
            print(json.dumps(dict(completed=len(rows),total=len(entries),kbps=row['kbps'],accepted=row['accepted'],
                                  flash_bytes=row.get('flash_bytes'),release_accepted=row.get('release_accepted',False))),flush=True)
    if hashes!={str(p.relative_to(REPO)):sha(p.read_bytes()) for p in sources}:raise ValueError('Sources changed during replay')
    summary=dict(schema='lpx-attiny88-lowrate-v1',cpu='ATtiny88 / AVR25',cpu_hz=16000000,
                 sample_hz=8000,queue=32,prefill=24,simulation_flash_limit=8192,release_flash_limit=6656,
                 physical_board_measured=False,source_sha256=hashes,
                 cases=sorted(rows,key=lambda row:(row['ordinal'],row['kbps'])))
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    if not all(row['accepted'] for row in rows):raise AssertionError('Some replay cases failed; inspect ignored private logs')
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--wsl');parser.add_argument('--jobs',type=int,default=2)
    args=parser.parse_args();run(args.manifest,args.output,wsl=args.wsl,jobs=args.jobs)

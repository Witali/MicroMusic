"""Build actual LG streams, verify independent/native replay and compare quality.

Requires the parent's current calls4 baseline models and verified public PCM.
All media and executable output stays under ignored build/lbg1-encoder/.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]
BUILD=REPO/'build/lbg1-encoder'
COMMON=REPO/'build/lbg1-common'
VARIANTS={'exact':'exact','bfp-exact':'bfp-exact','bfp-fine':'bfp-quality',
          'bfp-compact':'bfp-compact','trajectory-fine':'trajectory-quality',
          'trajectory-compact':'trajectory-compact','fine':'combined-quality',
          'compact':'combined-compact','fine-refit':'combined-quality-refit','compact-refit':'combined-compact-refit'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path):
    return path.relative_to(REPO).as_posix()


def write_json(path,value):
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,indent=2)+'\n')
    os.replace(temporary,path)


def build():
    manifest=json.loads((COMMON/'build.json').read_text())
    command=manifest['command'].copy()
    entry=next(i for i,value in enumerate(command) if value.endswith('/probe.cpp'))
    command[entry:entry+1]=[relative(HERE/name) for name in ('encoder.cpp','decoder.cpp','encode_probe.cpp')]
    command[command.index('-o')+1]=relative(BUILD/'encode-probe')
    inputs=[REPO/p for p in manifest['sources'] if not p.endswith('/probe.cpp')]
    inputs += [HERE/name for name in ('encoder.h','encoder.cpp','decoder.h','decoder.cpp','encode_probe.cpp','compare.py')]
    inputs += [REPO/'Codecs/LPX/01_ACTIVE_Q0_CODEC'/name for name in ('host/LpxLpcStability.h','host/LpxAdaptive.h','host/LpxQuality.h','host/LpxFullBand.h','src/Lpx4Math.h')]
    hashes={relative(path):sha(path) for path in inputs}
    receipt=BUILD/'build.json'
    if receipt.exists():
        old=json.loads(receipt.read_text())
        if old.get('sources')==hashes and (BUILD/'encode-probe').exists() and old.get('binary_sha256')==sha(BUILD/'encode-probe'):
            return old
    subprocess.run(command,cwd=REPO,check=True)
    if hashes!={relative(path):sha(path) for path in inputs}:
        raise RuntimeError('A codec input changed while building')
    result=dict(compiler=subprocess.check_output(['g++','--version'],text=True).splitlines()[0],command=command,
                sources=hashes,binary_sha256=sha(BUILD/'encode-probe'))
    write_json(receipt,result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',action='append',dest='cases')
    parser.add_argument('--variants',nargs='+',choices=tuple(VARIANTS),default=tuple(key for key in VARIANTS if not key.endswith('-refit')))
    parser.add_argument('--build-only',action='store_true')
    parser.add_argument('--selftest-only',action='store_true')
    parser.add_argument('--manifest',type=Path,help='Separate manifest under ignored build/lbg1-encoder')
    args=parser.parse_args()
    known={f'{clip}-p{level}' for clip in ('chego','otvechaesh','vinni','bread') for level in (4,6)}
    if args.cases and set(args.cases)-known:parser.error('Unknown case selection: '+', '.join(sorted(set(args.cases)-known)))
    BUILD.mkdir(parents=True,exist_ok=True)
    output_manifest=args.manifest or BUILD/('partial-manifest.json' if args.cases else 'manifest.json')
    if not output_manifest.is_absolute():output_manifest=REPO/output_manifest
    if not output_manifest.resolve().is_relative_to(BUILD.resolve()) or output_manifest.is_symlink():
        raise ValueError('Use a regular output manifest under build/lbg1-encoder')
    output_manifest.parent.mkdir(parents=True,exist_ok=True)
    receipt=build()
    if args.build_only:
        print('Built build/lbg1-encoder/encode-probe')
        return
    if args.selftest_only:
        master=BUILD/'manifest.json';before=sha(master) if master.exists() else None
        invalid=subprocess.run([sys.executable,str(Path(__file__)), '--case','not-a-public-case'],capture_output=True,text=True)
        if invalid.returncode!=2 or (sha(master) if master.exists() else None)!=before:
            raise AssertionError('Invalid case selection was not rejected before mutation')
        control=BUILD/'synthetic-log-rise'
        measured=json.loads(subprocess.check_output([str(BUILD/'encode-probe'),'selftest',str(control)],text=True))
        result=dict(schema='lbg1-encoder-validation-v1',build=receipt,unknown_case_rejected=True,
                    master_manifest_unchanged_by_negative_test=True,synthetic=measured,
                    lg_sha256=sha(control.with_suffix('.lbg')),pcm_sha256=sha(control.with_suffix('.pcm')))
        write_json(BUILD/'encoder-validation.json',result);print(json.dumps(result,indent=2));return
    cases=[]
    for clip in ('chego','otvechaesh','vinni','bread'):
        for level in (4,6):
            name=f'{clip}-p{level}'
            if args.cases and name not in args.cases:
                continue
            prefix=COMMON/'baselines'/name
            reference=COMMON/f'{clip}.source.pcm'
            paths={kind:prefix.with_suffix('.'+kind) for kind in ('lpx','model','pcm','json')}
            if not all(path.exists() for path in [reference,*paths.values()]):
                raise RuntimeError(f'Complete current calls4 baseline is not ready: {name}')
            case=dict(name=name,clip=clip,level=level,reference=relative(reference),reference_sha256=sha(reference),
                      baseline=dict(path=relative(paths['lpx']),pcm=relative(paths['pcm']),bytes=paths['lpx'].stat().st_size,
                                    sha256=sha(paths['lpx']),pcm_sha256=sha(paths['pcm']),model_sha256=sha(paths['model'])),variants={})
            destination=BUILD/name;destination.mkdir(exist_ok=True)
            for key in args.variants:
                output=destination/key
                command=[str(BUILD/'encode-probe'),str(paths['model']),str(reference),str(paths['pcm']),str(output),VARIANTS[key]]
                process=subprocess.run(command,cwd=REPO,capture_output=True,text=True)
                if process.returncode:
                    raise RuntimeError(f'{name}/{key}: {process.stderr.strip()}')
                measured=json.loads(process.stdout)
                artifact=output.with_suffix('.lbg');pcm=output.with_suffix('.pcm')
                case['variants'][key]=dict(path=relative(artifact),pcm=relative(pcm),sha256=sha(artifact),pcm_sha256=sha(pcm),metrics=measured)
                print(name,key,measured['bytes'],'PCM-STOI',measured['pcm_stoi'],'exact',measured['baseline_pcm_equal'],flush=True)
            cases.append(case)
            # Publish only fully verified cases; the AVR agent may read it now.
            result=dict(schema='lbg1-actual-stream-comparison-v1',baseline_source_revision='24fd9416',
                        source_manifest_sha256=sha(COMMON/'sources.json'),build=receipt,
                        method='Current LPX calls4 models on eight public8k inputs; actual LG files, independent reference and native LG decoder exact comparison; no source-specific decoder constants.',cases=cases)
            if (COMMON/'baselines.json').exists():result['baseline_manifest_sha256']=sha(COMMON/'baselines.json')
            write_json(output_manifest,result)
    summaries={}
    for key in args.variants:
        selected=[(case,case['variants'][key]['metrics']) for case in cases]
        summaries[key]=dict(files=len(selected),bytes=sum(m['bytes'] for _,m in selected),
            baseline_bytes=sum(c['baseline']['bytes'] for c,_ in selected),
            pcm_sse=sum(m['pcm_sse'] for _,m in selected),baseline_pcm_sse=sum(m['baseline_pcm_sse'] for _,m in selected),
            mean_pcm_stoi=sum(m['pcm_stoi'] for _,m in selected)/len(selected),
            mean_baseline_pcm_stoi=sum(m['baseline_pcm_stoi'] for _,m in selected)/len(selected),
            level_safe_files=sum(m['level_safe'] for _,m in selected),spectrum_safe_files=sum(m['spectrum_safe'] for _,m in selected),
            exact_baseline_outputs=sum(m['baseline_pcm_equal'] for _,m in selected),
            scale_commands=[sum(m['scale_commands'][i] for _,m in selected) for i in range(4)],
            pitch_commands=[sum(m['pitch_commands'][i] for _,m in selected) for i in range(4)])
    result['summaries']=summaries;write_json(output_manifest,result)
    print(json.dumps(summaries,indent=2))


if __name__=='__main__':
    main()

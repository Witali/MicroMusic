"""Four bounded one-bin proposals per file, with original-V9 whole-output gate.

No new-format decoder is built. Native Rice is the packing baseline and the
original unmodified V9 file is retained if either quality or packing fails.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
from analyze import REPO,read_model,native,grouped

HERE=Path(__file__).resolve().parent
COMMON=REPO/'build/lsf1-common'
BUILD=REPO/'build/lsf1-encoder'
POLICIES=('hold','snap','even_delta','greedy')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    receipt=json.loads((COMMON/'build.json').read_text())
    command=receipt['command'].copy();entry=next(i for i,p in enumerate(command) if p.endswith('/probe.cpp'))
    command[entry]=str((HERE/'gate_probe.cpp').relative_to(REPO));command[command.index('-o')+1]=str((BUILD/'gate-probe').relative_to(REPO))
    inputs=[REPO/p for p in receipt['sources']]
    inputs.extend([HERE/'gate_probe.cpp',HERE/'gate.py',HERE/'analyze.py',REPO/'Codecs/LPX/research/lbg1-2026-11-26/probe.cpp'])
    hashes={str(p.relative_to(REPO)):sha(p) for p in inputs}
    subprocess.run(command,cwd=REPO,check=True)
    if hashes!={str(p.relative_to(REPO)):sha(p) for p in inputs}:raise RuntimeError('An input changed during the gate build')
    return dict(compiler=subprocess.check_output(['g++','--version'],text=True).splitlines()[0],command=command,sources=hashes,binary_sha256=sha(BUILD/'gate-probe'))


def ordered(vector,bits):
    return all(0<=v<1<<bits for v in vector) and all(a<b for a,b in zip(vector,vector[1:]))


def possibilities(target,old,bits):
    candidates={'original':target.copy()}
    if old is None:return candidates
    if max(abs(a-b) for a,b in zip(target,old))<=1:candidates['hold']=old.copy()
    snapped=[b if abs(a-b)<=1 else a for a,b in zip(target,old)]
    even=[b+(1 if a>=b else -1)*(abs(a-b)//2)*2 for a,b in zip(target,old)]
    for name,vector in (('snap',snapped),('even_delta',even)):
        if ordered(vector,bits) and max(abs(a-b) for a,b in zip(target,vector))<=1:candidates[name]=vector
    return candidates


def propose(vectors,bits,policy):
    result=[];old=None;selected_groups=0;group_exponents={}
    for target in vectors:
        options=possibilities(target,old,bits)
        if policy=='greedy':
            choices=[]
            for name,vector in options.items():
                native_bits,_=native(vector,old,bits)
                g=grouped(vector,old,bits) if vector!=old else None
                choices.append((min(native_bits,g['bits'] if g else 1),name!='original',name,vector,g,native_bits))
            _,_,_,vector,g,native_bits=min(choices,key=lambda c:c[:3])
        else:
            vector=options.get(policy,target).copy();native_bits,_=native(vector,old,bits)
            g=grouped(vector,old,bits) if vector!=old else None
        if g and g['bits']<native_bits:
            selected_groups+=1
            for item in g['groups']:
                if item['width']:group_exponents[str(item['exponent'])]=group_exponents.get(str(item['exponent']),0)+1
        result.append(vector);old=vector
    return result,selected_groups,group_exponents


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=HERE/'one-bin-gate.json')
    args=parser.parse_args();BUILD.mkdir(parents=True,exist_ok=True)
    receipt=build();rows=[]
    for clip in ('chego','otvechaesh','vinni','bread'):
        for profile in (4,6):
            name=f'{clip}-p{profile}';prefix=COMMON/'baselines'/name;source=COMMON/f'{clip}.source.pcm'
            baseline=prefix.with_suffix('.lpx');model_path=prefix.with_suffix('.model');model=read_model(model_path)
            bits=5 if profile==4 else 6;destination=BUILD/name;destination.mkdir(exist_ok=True)
            row=dict(name=name,baseline_path=baseline.relative_to(REPO).as_posix(),baseline_bytes=baseline.stat().st_size,
                     baseline_sha256=sha(baseline),model_sha256=sha(model_path),reference_sha256=sha(source),proposals=[])
            for policy in POLICIES:
                vectors,groups,exponents=propose(model['spectra'],bits,policy)
                output=destination/policy;indices=output.with_suffix('.bins.txt')
                indices.write_text('\n'.join(' '.join(map(str,v)) for v in vectors)+'\n')
                command=[str(COMMON/'probe'),'replace',str(baseline),str(indices),str(source),str(output)]
                process=subprocess.run(command,capture_output=True,text=True,cwd=REPO)
                if process.returncode:raise RuntimeError(f'{name}/{policy}: '+process.stderr)
                candidate=output.with_suffix('.lpx')
                compared=json.loads(subprocess.check_output([str(BUILD/'gate-probe'),str(baseline),str(candidate),str(source)],text=True))
                changed=sum(a!=b for original,new in zip(model['spectra'],vectors) for a,b in zip(original,new))
                if changed!=compared['changed_lsf_indices'] or compared['maximum_lsf_bin_error']>1:raise AssertionError('Candidate source bound differs')
                admitted=compared['quality_admitted'] and candidate.stat().st_size<row['baseline_bytes']
                proposal=dict(policy=policy,candidate_bytes=candidate.stat().st_size,candidate_sha256=sha(candidate),
                    changed_lsf_indices=changed,projected_group_packets=groups,projected_group_exponents=exponents,
                    native_packing_gain_bytes=row['baseline_bytes']-candidate.stat().st_size,admitted=admitted,metrics=compared)
                row['proposals'].append(proposal)
                print(name,policy,proposal['candidate_bytes'],'quality',compared['quality_admitted'],'admitted',admitted,'reasons',compared['rejection_bits'],flush=True)
            accepted=[p for p in row['proposals'] if p['admitted']]
            chosen=min(accepted,key=lambda p:p['candidate_bytes']) if accepted else None
            row['selected_policy']=chosen['policy'] if chosen else 'unmodified_baseline'
            row['selected_bytes']=chosen['candidate_bytes'] if chosen else row['baseline_bytes']
            row['selected_changed_lsf_indices']=chosen['changed_lsf_indices'] if chosen else 0
            rows.append(row)
    totals=dict(files=len(rows),proposals=sum(len(r['proposals']) for r in rows),baseline_bytes=sum(r['baseline_bytes'] for r in rows),
                selected_bytes=sum(r['selected_bytes'] for r in rows),admitted_proposals=sum(p['admitted'] for r in rows for p in r['proposals']),
                changed_selected_files=sum(r['selected_policy']!='unmodified_baseline' for r in rows),
                selected_projected_group_packets=sum(p['projected_group_packets'] for r in rows for p in r['proposals'] if p['policy']==r['selected_policy']))
    result=dict(schema='lsf1-bounded-one-bin-gate-v1',method='Exactly four deterministic one-bin proposals per file in original V9, with the same levels, pitch, pulses and extras. Native/model PCM equality and all source-relative quality guards; full baseline fallback when quality fails or the actual native file does not shrink. Group counts are cost projections, not emitted packets. No new-format decoder or AVR implementation.',
        build=receipt,source_manifest_sha256=sha(COMMON/'sources.json'),baseline_manifest_sha256=sha(COMMON/'baselines.json'),
        rejection_bits={'pcm_sse':1,'pwm_sse':2,'pcm_stoi':4,'pwm_stoi':8,'fullband':16,'level':32,'spectrum':64,'stability':128},
        rows=rows,totals=totals)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(totals,indent=2))


if __name__=='__main__':main()

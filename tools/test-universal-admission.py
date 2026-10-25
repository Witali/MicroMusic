"""Measured UM88 admission matrix, including deliberate real-time/output failures.

Requires GNU AVR and Node. All synthetic fixtures are JSON in ignored build/.
No assembler change is made and no MIDI binary is created.
"""
from pathlib import Path
import argparse
import copy
import json
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def fixture(name,voices,stress=False,burst=False):
    wave=[(i-8) for i in range(16)]
    packed=[(wave[i]+8)|((wave[i+1]+8)<<4) for i in range(0,16,2)]
    raw=[]
    for tick in range(48):
        if tick==0 or stress:
            for i in range(voices):
                raw.extend([64+i,(i+tick)%8,72+i,1+(i+tick)%8,128+(i<<4)+(14 if tick&1 else 15),80+i])
            if stress:raw.extend([96,128|(tick%3)|8,97,(tick*7)&255,98,1+(tick&15)])
        if burst:raw.extend([64,0]*1200)
        raw.append(1)
    raw.append(0)
    return dict(schema='micromusic-um88-score',version=1,name=name,voices=voices,channels=1,
                waves=packed*8,contexts=[[0,i*8,3,128] for i in range(8)],
                envelopes=[[v for level in range(16) for v in (level,0,0)]],
                pitches=[None,48,52,55,60,64,67,72,76],commands=raw,controlTicks=48,
                groupGain=False,normalizer=[],normalizerMinimum=0,masterShift=0,
                source=dict(kind='original deterministic stress fixture',license='CC0-1.0'))


def save(path,data):path.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')


def run(command):return subprocess.run([str(x) for x in command],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'build/universal/admission')
    parser.add_argument('--report',type=Path)
    args=parser.parse_args();folder=args.output_dir.resolve();folder.mkdir(parents=True,exist_ok=True)
    cases=[]
    configurations=[('c',8000000,n,False,False) for n in range(1,6)]+[
        ('avr-asm',8000000,3,True,False),('avr-asm',8000000,8,True,False),
        ('avr-asm',12000000,8,True,False),('avr-asm',8000000,1,False,True)]
    for backend,cpu,voices,stress,burst in configurations:
        name=f"{backend}-{cpu}-{voices}-"+('burst' if burst else 'dense' if stress else 'held')
        source=folder/(name+'.json');save(source,fixture(name,voices,stress,burst))
        result=run([sys.executable,ROOT/'tools/build-universal-music.py','--backend',backend,'--cpu-hz',cpu,
                    '--score',source,'--output-dir',folder])
        if result.returncode:raise RuntimeError(result.stderr or result.stdout)
        audit=run(['node',ROOT/'tools/audit-universal-music.mjs','--directory='+str(folder),name])
        measured=json.loads((folder/name/'verification.json').read_text(encoding='utf-8'))
        assert measured['passed']==(audit.returncode==0)
        if backend=='avr-asm' and voices==3:assert measured['passed'],measured
        if backend=='c' and voices==1:assert measured['passed'],measured
        if burst or backend=='c' and voices>=4 or backend=='avr-asm' and voices==8:
            assert not measured['passed'] and measured['fifoUnderruns']>0,measured
        cases.append(dict(workload='1200 redundant CONTEXT commands every tick' if burst else
                          f'{voices} voices; every tick changes all contexts, pitches, levels, phases and percussion' if stress else
                          f'{voices} continuously held independent voices; LOOP/restart',verification=measured))
        print(name,'PASS' if measured['passed'] else 'REJECTED',measured.get('failure','').splitlines()[0] if not measured['passed'] else '')
    # Negative controls bypass packaging checks: the oracle must detect wrong
    # musical commands and post-mix output even when the firmware hash is valid.
    original=folder/'avr-asm-8000000-3-dense'
    for mutation in ('percussion','output'):
        name='wrong-'+mutation;target=folder/name
        target.mkdir(exist_ok=True)
        for filename in ('score.json','synth.bin','build-report.json'):shutil.copyfile(original/filename,target/filename)
        score=json.loads((target/'score.json').read_text(encoding='utf-8'))
        if mutation=='output':score['masterShift']=1
        else:
            at=score['commands'].index(96);score['commands'][at+1]^=1
        save(target/'score.json',score)
        result=run(['node',ROOT/'tools/audit-universal-music.mjs','--directory='+str(folder),name])
        measured=json.loads((target/'verification.json').read_text(encoding='utf-8'))
        assert result.returncode and not measured['passed']
        assert ('Percussion mode' if mutation=='percussion' else 'generated PWM') in measured['failure'],measured
        cases.append(dict(workload='Deliberately wrong expected '+mutation,verification=measured))
        print(name,'DETECTED')
    report=dict(schema='micromusic-um88-admission-matrix',version=1,hardwareTested=False,
                toolchain=json.loads((original/'build-report.json').read_text(encoding='utf-8'))['toolchainVersion'],
                compilerOptions='-mmcu=attiny88 -Os -fno-jump-tables -ffunction-sections -fdata-sections -Wl,--gc-sections',
                cases=cases,conclusion='Only the recorded workloads/profiles are established; every new score must pass its own full audit')
    target=args.report or folder/'admission.json';target.parent.mkdir(parents=True,exist_ok=True);save(target,report)


if __name__=='__main__':main()

"""Check exact AVR25 LPC synthesis with selectable C/ASM and active IRQ.

Run under Linux/WSL with AVR-GCC and simavr1.6. All generated files stay in
build/. Reuse the retained PWM-gain probe's official device metadata and
Timer1 observer; specialize only its expected case count in a private copy.
No production source or retained observer is modified.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
REPO=next(p for p in HERE.parents if (p/'Codecs/LPX/01_ACTIVE_Q0_CODEC/src').is_dir())
ACTIVE=REPO/'Codecs/LPX/01_ACTIVE_Q0_CODEC'
TESTS=ACTIVE/'tests'
DFP=REPO/'ATtiny88/Music/universal/vendor/ATtiny_DFP/3.4.278/include'

def sha(data):return hashlib.sha256(data).hexdigest()

def run(*args):
    r=subprocess.run([str(a) for a in args],capture_output=True)
    if r.returncode:
        raise RuntimeError((r.stderr.decode(errors='replace') or r.stdout.decode(errors='replace')).replace(str(REPO),'<repo>'))
    return r.stdout

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=REPO/'build/avr25-lpc-exact')
    parser.add_argument('--source-codec',type=Path,default=ACTIVE)
    parser.add_argument('--fixtures',choices=('linear','mirror','both'),default='both')
    args=parser.parse_args()
    output=args.output.resolve()
    if REPO/'build' not in output.parents or output.is_symlink():raise ValueError('Use an output subdirectory under build/')
    output.mkdir(parents=True,exist_ok=True)
    source=output/'source';bindings={}
    for p in sorted((args.source_codec.resolve()/'src').glob('Lpx4*.h')):
        relative=Path('src')/p.name
        data=p.read_text(encoding='utf-8').replace('\r\n','\n')
        destination=source/relative;destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_text(data,encoding='utf-8',newline='\n');bindings[relative.as_posix()]=sha(data.encode())
    profile=Path('profiles/Lpx4Sram512.h')
    p=args.source_codec.resolve()/profile
    if not p.is_file():p=ACTIVE/profile
    data=p.read_text(encoding='utf-8').replace('\r\n','\n')
    (source/profile).parent.mkdir(parents=True,exist_ok=True)
    (source/profile).write_text(data,encoding='utf-8',newline='\n');bindings[profile.as_posix()]=sha(data.encode())
    spec=importlib.util.spec_from_file_location('lpx_gain_metadata',TESTS/'verify_pwm_gain.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    simavr=run('pkg-config','--modversion','simavr').decode().strip()
    if simavr!='1.6':raise ValueError('This IRQ calibration requires simavr1.6')
    observer=(TESTS/'sim_pwm_gain.c').read_text(encoding='utf-8')
    token='read32(cpu,cases)!=32768'
    if observer.count(token)!=1:raise ValueError('Review changed PWM-gain observer before reusing its case gate')
    fixtures=[('linear','avr25_lpc_synthesis.cpp',44662),('mirror','avr25_mirrored_lpc.cpp',41280)]
    rows=[]
    for name,filename,count in fixtures:
        if args.fixtures!='both' and args.fixtures!=name:continue
        folder=output/name;folder.mkdir(exist_ok=True)
        hardware=helper.metadata('attiny88',folder)
        (folder/'observer.c').write_text(observer.replace(token,'read32(cpu,cases)!='+str(count)),encoding='utf-8',newline='\n')
        sim=folder/'sim_lpc'
        run('gcc','-O2','-std=c11','-I'+str(folder),'-I/usr/include/simavr',folder/'observer.c','-lsimavr','-lelf','-o',sim)
        for asm in (0,1):
            flags=['-mmcu=attiny88','-DF_CPU=16000000UL','-Os','-std=gnu++11',
                '-DLPX4_COMPACT_VERSION=9','-DLPX4_AVR25_SATURATED_PRODUCTS=1',f'-DLPX4_ENABLE_ASM={asm}',
                '-include',str(source/profile),'-I'+str(DFP),'-I'+str(source/'src')]
            elf=folder/f'asm{asm}.elf'
            run('avr-g++',*flags,HERE/filename,'-o',elf)
            log=run(sim,elf).decode();(folder/f'asm{asm}.log').write_text(log,encoding='utf-8')
            result=json.loads(next(line for line in reversed(log.splitlines()) if line.startswith('{')))
            assert result['done']==1 and not result['error'] and not result['zero_error'],result
            assert result['backend']==asm and result['cases']==count and result['irqs']>100,result
            rows.append(dict(fixture=name,assembly=asm,**result,hardware=hardware,
                compiler_options=[f.replace(str(REPO),'<repo>')for f in flags],elf_sha256=sha(elf.read_bytes())))
            print(name,asm,result,flush=True)
    retained={p.name:sha(p.read_bytes()) for p in [Path(__file__),*(HERE/name for _,name,_ in fixtures),
        TESTS/'sim_pwm_gain.c',TESTS/'verify_pwm_gain.py']}
    result=dict(schema='lpx-avr25-lpc-exact-v1',cpu_hz=16000000,simavr=simavr,
        compiler=run('avr-g++','--version').decode().splitlines()[0],arithmetic_source_lf_sha256=bindings,
        retained_source_sha256=retained,physical_board_measured=False,results=rows,
        linear_domain='signed16 boundary/random coefficients/history, scaled/unscaled excitation, keepQ4 on/off, spare history on/off and bounded production form',
        mirrored_domain='all20 initial sample positions,48 scenarios,43 transitions each; sign/clamp/zero/wrap, read/write bounds and r1/activeIRQ',
        input_contract='Q4 excitation is integer excitation multiplied by16, and bounded coefficients exclude-32768')
    (output/'receipt.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=True,fixtures=args.fixtures,receipt=str((output/'receipt.json').relative_to(REPO)))))

if __name__=='__main__':main()

"""Exhaust actual ROM PWM gain on both AVR targets, explicit C/ASM and live IRQ.

The probe extracts playbackGain from production player.cpp. It changes only
the gain byte's hardware load into a parameter, then invokes the same arithmetic
through a non-inlined GNU ABI boundary with saved-register and r1 checks.
No production source is written. All generated files must stay under build/.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
REPO=next(p for p in HERE.parents if (p/'Codecs/LPX/01_ACTIVE_Q0_CODEC/src').is_dir())
ACTIVE=REPO/'Codecs/LPX/01_ACTIVE_Q0_CODEC'
PLAYER=ACTIVE/'examples/ATTINY88_V5_PLAYER/player.cpp'
DFP=REPO/'ATtiny88/Music/universal/vendor/ATtiny_DFP/3.4.278/include'
REGISTERS='TCNT1L TCNT1H TCCR1B TIMSK1 TIFR1'.split()
CONSTANTS='RAMSTART RAMEND FLASHEND E2END CS10 CS11 CS12 TOIE1 TOV1 TIMER1_OVF_vect_num'.split()

def sha(data):return hashlib.sha256(data).hexdigest()

def run(*args):
    result=subprocess.run([str(a) for a in args],capture_output=True)
    if result.returncode:
        message=result.stderr.decode(errors='replace') or result.stdout.decode(errors='replace')
        raise RuntimeError(message.replace(str(REPO),'<repo>'))
    return result.stdout

def extract_gain(source):
    signature='static uint8_t playbackGain(uint8_t sample){'
    start=source.index(signature)
    end=source.index('\n}\n#endif',start)+2
    body=source[start:end]
    load='    const uint8_t gain=pgm_read_byte(voice+sizeof(voice)-1);\n'
    if body.count(load)!=1:raise ValueError('Expected one ROM gain load; review extraction for the changed player')
    body=body.replace(signature,'static uint8_t playbackGain(uint8_t sample,uint8_t gain){',1).replace(load,'',1)
    return '#include "Lpx4Math.h"\n'+body+'\n'

def metadata(target,folder):
    values=[(r,'_SFR_MEM_ADDR('+r+')') for r in REGISTERS]+[(c,c) for c in CONSTANTS]
    cpp='#include <avr/io.h>\nextern "C" const unsigned short hardware[] __attribute__((used,section(".gain_meta")))={'+','.join(v for _,v in values)+'};\n'
    (folder/'hardware.cpp').write_text(cpp,encoding='ascii')
    flags=['-mmcu='+target,*(['-I'+str(DFP)] if target=='attiny88' else [])]
    run('avr-g++',*flags,'-c',folder/'hardware.cpp','-o',folder/'hardware.o')
    run('avr-objcopy','-O','binary','-j','.gain_meta',folder/'hardware.o',folder/'hardware.bin')
    data=(folder/'hardware.bin').read_bytes()
    if len(data)!=2*len(values):raise ValueError('Invalid official device metadata')
    definitions={name:int.from_bytes(data[2*i:2*i+2],'little') for i,(name,_) in enumerate(values)}
    (folder/'hardware.h').write_text(''.join(f'#define H_{name} {value}\n' for name,value in definitions.items()),encoding='ascii')
    return definitions

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=REPO/'build/avr-pwm-gain-exhaustive')
    args=parser.parse_args()
    output=args.output.resolve()
    if REPO/'build' not in output.parents or output.is_symlink():raise ValueError('Use a private output below build/')
    output.mkdir(parents=True,exist_ok=True)
    player=PLAYER.read_text(encoding='utf-8').replace('\r\n','\n')
    extracted=extract_gain(player)
    (output/'gain.h').write_text(extracted,encoding='utf-8',newline='\n')
    # Freeze arithmetic selection and its profile before compiling either
    # backend, so a concurrent checkout edit cannot create a mixed receipt.
    source=output/'source'
    source_hashes={}
    files=[*sorted((ACTIVE/'src').glob('Lpx4*.h')),ACTIVE/'profiles/Lpx4Sram512.h']
    for original in files:
        relative=original.relative_to(ACTIVE)
        destination=source/relative;destination.parent.mkdir(parents=True,exist_ok=True)
        data=original.read_text(encoding='utf-8').replace('\r\n','\n')
        destination.write_text(data,encoding='utf-8',newline='\n')
        source_hashes[original.relative_to(REPO).as_posix()]=sha(data.encode())
    simavr=run('pkg-config','--modversion','simavr').decode().strip()
    if simavr!='1.6':raise ValueError('This IRQ entry calibration requires simavr1.6')
    rows=[]
    for target in ('atmega328p','attiny88'):
        folder=output/target;folder.mkdir(exist_ok=True)
        device=metadata(target,folder)
        observer=folder/'sim_gain'
        observer_flags=['-DGAIN_NATIVE_MCU="'+target+'"'] if target=='atmega328p' else []
        run('gcc','-O2','-std=c11','-I'+str(folder),'-I/usr/include/simavr',*observer_flags,
            HERE/'sim_pwm_gain.c','-lsimavr','-lelf','-o',observer)
        for assembly in (False,True):
            suffix='asm' if assembly else 'c'
            elf=folder/(suffix+'.elf')
            flags=['-mmcu='+target,'-Os','-flto','-ffunction-sections','-fdata-sections',
                '-fno-exceptions','-fno-rtti','-std=gnu++11','-DF_CPU=16000000UL',
                '-DLPX4_COMPACT_VERSION=9','-DLPX4_ENABLE_ASM='+str(int(assembly)),
                '-include',str(source/'profiles/Lpx4Sram512.h'),
                *(['-I'+str(DFP)] if target=='attiny88' else []),
                '-I'+str(source/'src'),'-I'+str(output)]
            run('avr-g++',*flags,HERE/'avr_pwm_gain.cpp','-Wl,--gc-sections','-o',elf)
            log=run(observer,elf).decode()
            (folder/(suffix+'.log')).write_text(log,encoding='utf-8')
            measured=json.loads(next(line for line in reversed(log.splitlines()) if line.startswith('{')))
            if measured['backend']!=int(assembly):raise ValueError('Requested arithmetic backend was not selected')
            assert measured['done']==1 and measured['error']==measured['zero_error']==0
            assert measured['cases']==32768 and measured['irqs']>0
            backend_macro=measured.pop('backend')
            rows.append(dict(target=target,backend=suffix,backend_macro=backend_macro,**measured,elf_sha256=sha(elf.read_bytes()),
                compiler_options=[v.replace(str(REPO),'<repo>') for v in flags],hardware=device))
    retained={p.name:sha(p.read_bytes()) for p in (HERE/'avr_pwm_gain.cpp',HERE/'sim_pwm_gain.c',Path(__file__))}
    receipt=dict(schema='lpx-avr-pwm-gain-exhaustive-v1',cpu_hz=16000000,
        domain=dict(duty_min=0,duty_max=255,gain_min=128,gain_max=255,cases_per_backend=32768),
        compiler=run('avr-g++','--version').decode().splitlines()[0],simavr=simavr,
        player_source_lf_sha256=sha(player.encode()),extracted_gain_lf_sha256=sha(extracted.encode()),
        arithmetic_source_lf_sha256=source_hashes,
        retained_source_sha256=retained,abi_callee_saved_registers=[*range(2,18),28,29],
        physical_board_measured=False,cases=rows)
    (output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=True,targets=2,backends=4,cases_per_backend=32768,
        receipt=str((output/'receipt.json').relative_to(REPO)))))

if __name__=='__main__':main()

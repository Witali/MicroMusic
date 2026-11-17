"""Build a bounded 16 MHz / 8 kHz ATtiny88 v5 ROM player, C or opt-in ASM.

Standard library only. Run with Linux AVR-GCC, or --wsl Ubuntu on Windows.
No media or generated firmware is added to Git. Output must be under build/.
"""
import argparse
import hashlib
import json
import os
import re
import struct
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[2]
DFP=REPO/'ATtiny88/Music/universal/vendor/ATtiny_DFP/3.4.278/include'

def read_irq_registers(register_map):
    names=('sample','sreg')
    bindings=re.findall(r'^\.equ lpx25_irq_(sample|sreg),\s*(\d+)\s*$',
                        register_map.read_text(encoding='ascii'),re.M)
    values={name:int(number) for name,number in bindings}
    if len(bindings)!=2 or values.keys()!=set(names):
        raise ValueError('Expected one numeric .equ for each IRQ register')
    sample,status=(values[name] for name in names)
    if sample not in range(2,16,2) or status!=sample+1:
        raise ValueError('IRQ registers must form an even callee-saved register pair')
    return sample,status

def audit_registers(elf,listing,reserved,*,irq_registers,sample_irq,allow_hardware_mul):
    """Inspect ELF function bodies, excluding ROM media marked STT_OBJECT."""
    data=Path(elf).read_bytes()
    if data[:6]!=b'\x7fELF\x01\x01':raise ValueError('Expected little-endian ELF32')
    shoff=struct.unpack_from('<I',data,32)[0]
    size,count=struct.unpack_from('<HH',data,46)
    sections=[struct.unpack_from('<10I',data,shoff+i*size) for i in range(count)]
    functions=[]
    for section in sections:
        if section[1]!=2:continue
        strings=sections[section[6]];names=data[strings[4]:strings[4]+strings[5]]
        for at in range(section[4],section[4]+section[5],section[9]):
            name,value,length,info,_,_=struct.unpack_from('<IIIBBH',data,at)
            if info&15==2 and length:
                text=names[name:names.index(0,name)].decode()
                functions.append((value,value+length,text))
    if not functions:raise ValueError('ELF has no function ranges')
    pattern=re.compile(r'\br(?:'+'|'.join(map(str,irq_registers))+r')\b')
    irq_operands=set()
    for line in Path(listing).read_text().splitlines():
        match=re.match(r'^\s*([0-9a-f]+):\s+(?:[0-9a-f]{2}\s+)+(.+)$',line)
        if not match:continue
        pc=int(match[1],16);instruction=match[2].split(';')[0].strip()
        owner=next((name for a,b,name in functions if a<=pc<b),None)
        if owner is None:continue
        if instruction.split()[0] in ('mul','muls','mulsu','fmul','fmuls','fmulsu'):
            if not allow_hardware_mul or (reserved and owner==sample_irq):
                raise ValueError('Hardware multiply in an unsupported function')
        fixed=pattern.findall(instruction)
        if reserved and owner==sample_irq:
            irq_operands.update(fixed)
        elif reserved and fixed:
            abi=(owner=='__prologue_saves__' and instruction.startswith('push')) or (
                 owner=='__epilogue_restores__' and instruction.startswith('ldd'))
            if not abi:raise ValueError('Foreground function uses ISR-reserved registers: '+owner)
    if reserved and irq_operands!={f'r{reg}' for reg in irq_registers}:
        raise ValueError('Sample IRQ does not use the reserved register pair')
    return True

def target_path(path,wsl):
    p=Path(path).resolve()
    if wsl and os.name=='nt':
        return '/mnt/'+p.drive[0].lower()+'/'+ '/'.join(p.parts[1:])
    return str(p)

def build(source,output,*,assembly=False,queue=None,repeat=1,wsl=None,avr_bin=None,lpc_segments=2,asm_isr=False,extra_flags=(),flash_limit=8192,sparse80=False,mul16_unroll=None,output_gain=128,universal=True,rom_output_gain=False,target='attiny88',nano_pwm=False):
    if target not in ('attiny88','atmega328','atmega328p'):
        raise ValueError('Unsupported AVR player target')
    if nano_pwm and target=='attiny88':
        raise ValueError('Nano PWM requires ATmega328 or ATmega328P')
    inputs=source if isinstance(source,(list,tuple)) else [source]
    if not 1<=len(inputs)<=255:
        raise ValueError('Expected 1..255 complete LPX streams')
    sources=[Path(path).resolve() for path in inputs]
    source,output=sources[0],Path(output).resolve()
    if output==REPO/'build' or REPO/'build' not in output.parents or source==output or output.is_symlink():
        raise ValueError('Use an output subdirectory under ignored repository build/')
    names=('audio.inc','output_gain.inc','segment_lengths.inc','player.elf','player.bin','player.hex','player.nm','player.lss','build.json',
           'hardware.cpp','hardware.o','hardware.bin','hardware.h')
    if any((output/n).is_symlink() or (output/n).resolve() in sources or
           ((output/n).exists() and (output/n).stat().st_nlink>1) for n in names):
        raise ValueError('Output aliases input or uses a symlink')
    blobs=[path.read_bytes() for path in sources]
    blob=blobs[0]
    if type(universal) is not bool:raise ValueError('Universal selection must be boolean')
    if mul16_unroll is None:mul16_unroll=2 if universal else 16
    if universal and ((output_gain!=128 and not rom_output_gain) or any(flag.startswith('-DLPX4_FIXED_') for flag in extra_flags)):
        raise ValueError('Universal playback reads stream parameters without per-record specialization')
    if not isinstance(sparse80,bool):raise ValueError('Sparse80 selection must be boolean')
    version=9 if blob[:2]==b'L9' else blob[4] if len(blob)>=16 else 0
    header_bytes=13 if version==9 else 22
    flags_at=2 if version==9 else 5
    if not header_bytes<=len(blob)<=65535 or not ((version==9 or blob[:5]==b'L4HY\x05') and (blob[flags_at]&127 in (4,6) or version==9 and blob[flags_at]==15) or
            sparse80 and blob[:6]==b'L4HY\x08\x0f'):
        raise ValueError('Expected compact v5/v9, or sparse80 with its explicit enable')
    compact_version=9 if version==9 else 5
    if len(blobs)>1:
        if not universal or compact_version!=9 or any(data[:2]!=b'L9' for data in blobs):
            raise ValueError('Multiple streams require universal LPX v9')
        for data in blobs:
            if len(data)<13 or len(data)!=13+int.from_bytes(data[11:13],'little'):
                raise ValueError('Incomplete LPX v9 segment')
    if rom_output_gain and (not universal or compact_version!=9):
        raise ValueError('ROM output gain requires universal LPX v9')
    if queue is None:queue=32 if compact_version==9 or not universal else 44
    samples=sum(int.from_bytes(data[5:7] if version==9 else data[8:12],'little') for data in blobs)
    pre_at=7 if version==9 else 12
    if queue not in (16,24,32,44) or not 1<=repeat<=255 or lpc_segments not in (1,2,4):raise ValueError('Invalid playback geometry')
    physical_flash=8192 if target=='attiny88' else 32768
    if not 1<=flash_limit<=physical_flash:raise ValueError('Flash limit exceeds the selected device')
    if isinstance(mul16_unroll,bool) or mul16_unroll not in (1,2,4,8,16):raise ValueError('Invalid AVR25 multiply unroll')
    if type(output_gain) is not int or not 128<=output_gain<=255:raise ValueError('Invalid Q7 output gain')
    output.mkdir(parents=True,exist_ok=True)
    path=lambda p:target_path(p,wsl)
    prefix=['wsl','-d',wsl,'--'] if wsl else []
    def run(tool,*args):
        executable=str(Path(avr_bin)/tool) if avr_bin else tool
        result=subprocess.run([*prefix,executable,*args],capture_output=True)
        if result.returncode:raise RuntimeError(result.stderr.decode(errors='replace'))
        return result.stdout
    audio_data=b''.join(blobs)
    voice=audio_data+bytes([output_gain]) if rom_output_gain else audio_data
    (output/'audio.inc').write_text(','.join(map(str,audio_data))+'\n',encoding='ascii')
    if len(blobs)>1:
        (output/'segment_lengths.inc').write_text(','.join(str(len(data)) for data in blobs)+'\n',encoding='ascii')
    if rom_output_gain:
        (output/'output_gain.inc').write_text(f',{output_gain}\n',encoding='ascii')
    flags=['-mmcu='+target,'-DF_CPU=16000000UL','-Os','-flto','-mcall-prologues','-mrelax',
           '-fno-jump-tables','-fno-exceptions','-fno-rtti','-ffunction-sections','-fdata-sections',
           '-std=gnu++11','-DLPX4_FUNCTION_TUNING=0',f'-DLPX4_ENABLE_ASM={int(assembly)}',f'-DLPX3_LPC_SEGMENTS={lpc_segments}',
           f'-DLPX25_QUEUE={queue}',f'-DLPX25_REPEAT={repeat}',f'-DPWM_GAIN_Q7={128 if rom_output_gain else output_gain}',
           f'-DLPX4_AVR25_MUL16_UNROLL={mul16_unroll}',
           '-include',path(ROOT/'profiles/Lpx4Sram512.h'),
           *(['-I'+path(DFP)] if target=='attiny88' else []),
           '-I'+path(ROOT/'src'),'-I'+path(output)]
    player=ROOT/'examples/ATTINY88_V5_PLAYER/player.cpp'
    register_map=player.with_name('irq_registers.inc')
    shared_irq=asm_isr and universal and compact_version==9
    irq_registers=read_irq_registers(register_map) if shared_irq else ((4,5) if target!='attiny88' else (2,3))
    if asm_isr:
        flags+=['-DLPX25_ENABLE_ASM_ISR=1','-DLPX25_ISR_FIXED_REGS=1',*(f'-ffixed-r{r}' for r in irq_registers)]
    if shared_irq:
        # LTO assembles the IRQ from a temporary file. Give GAS the map's
        # full path so it does not need the original assembler search path.
        map_path=path(register_map).replace('\\','/')
        flags+=[f'-DLPX25_IRQ_REGISTER_MAP={json.dumps(map_path)}',
                f'-DLPX25_IRQ_SAMPLE_REGISTER={irq_registers[0]}',
                f'-DLPX25_IRQ_SREG_REGISTER={irq_registers[1]}']
    if rom_output_gain:flags+=['-DLPX25_ROM_OUTPUT_GAIN=1']
    if nano_pwm:flags+=['-DLPX25_NANO_PWM=1']
    if len(blobs)>1:flags+=[f'-DLPX25_SEGMENTS={len(blobs)}']
    if sparse80:flags+=['-DLPX4_ENABLE_SPARSE80=1']
    if compact_version==9:flags+=['-DLPX4_COMPACT_VERSION=9']
    if universal:
        flags+=['-DLPX4_AVR25_SATURATED_PRODUCTS=1','-DLPX25_REUSE_TIMER1_HIGH=1']
    else:
        flags += [f'-DLPX4_FIXED_PRE_Q14={int.from_bytes(blob[pre_at:pre_at+2],"little")}',
                  f'-DLPX4_FIXED_BRIGHT_Q14={int.from_bytes(blob[pre_at+2:pre_at+4],"little")}',
                  f'-DLPX4_FIXED_SPEECH_FLAGS={blob[flags_at]}']
    # Measured AVR25 ASM recipe: avoid repeated small reader bodies and reduce
    # foreground register pressure. The explicitly selected C recipe stays C.
    if assembly:flags+=['-finline-small-functions' if universal else '-fno-inline-small-functions']
    if assembly and universal and compact_version==9 and target!='attiny88' and rom_output_gain:
        # Spend the ten cycles recovered by the AVR5 ROM-gain kernel on a
        # single LPC tap body. Other recipes retain the default two-tap loop.
        flags+=['-DLPX4_AVR5_LPC_UNROLL=1']
    flags+=list(extra_flags)
    run('avr-g++',*flags,path(player),
        path(ROOT/'src/Lpx4HybridCore.cpp'),'-Wl,--gc-sections','-o',path(output/'player.elf'))
    for fmt,name in [('binary','player.bin'),('ihex','player.hex')]:
        run('avr-objcopy','-O',fmt,'-R','.eeprom',path(output/'player.elf'),path(output/name))
    (output/'player.nm').write_bytes(run('avr-nm','-S',path(output/'player.elf')))
    (output/'player.lss').write_bytes(run('avr-objdump','-d','-C',path(output/'player.elf')))
    registers='TCCR0A TCNT0 OCR0A OCR0B TIMSK0 TIFR0 TCCR1A TCCR1B TCNT1L TCNT1H OCR1AL OCR1AH OCR1BL OCR1BH ICR1L ICR1H TIMSK1 TIFR1 PORTB DDRB PINB SPL SPH CLKPR'.split()
    constants='CTC0 CS00 CS01 CS02 OCIE0A OCF0A TOIE0 TOV0 OCIE1A OCF1A TOIE1 TOV1 WGM10 WGM11 WGM12 WGM13 CS10 CS11 CS12 COM1A0 PB1 TIMER0_COMPA_vect_num TIMER0_OVF_vect_num TIMER1_COMPA_vect_num TIMER1_COMPB_vect_num TIMER1_OVF_vect_num RAMSTART RAMEND FLASHEND E2END LPX25_QUEUE'.split()
    if target!='attiny88':
        registers+=['TCCR0B','TCCR2A','TCCR2B','OCR2B','DDRD']
        constants[0]='WGM01'
    values=[(name,'_SFR_MEM_ADDR('+name+')') for name in registers]+[(name,name) for name in constants]
    text='#include <avr/io.h>\nextern "C" const unsigned short hardware[] __attribute__((used,section(".lpx_meta")))={'+','.join(v for _,v in values)+'};\n'
    (output/'hardware.cpp').write_text(text,encoding='ascii')
    run('avr-g++',*[f for f in flags if f!='-flto'],'-c',path(output/'hardware.cpp'),'-o',path(output/'hardware.o'))
    run('avr-objcopy','-O','binary','-j','.lpx_meta',path(output/'hardware.o'),path(output/'hardware.bin'))
    hardware=(output/'hardware.bin').read_bytes()
    if len(hardware)!=2*len(values):raise ValueError('Invalid vendor metadata object')
    definitions={name:int.from_bytes(hardware[2*i:2*i+2],'little') for i,(name,_) in enumerate(values)}
    hardware_defines=''.join(f'#define H_{name} {value}\n' for name,value in definitions.items())
    if target!='attiny88':
        hardware_defines+=f'#define H_LPX_NATIVE_TARGET "{target}"\n'
        hardware_defines+=f'#define H_LPX_IRQ_SAMPLE {irq_registers[0] if asm_isr else 255}\n#define H_LPX_IRQ_SREG {irq_registers[1] if asm_isr else 255}\n'
    if nano_pwm:
        hardware_defines+='#define H_LPX_SAMPLE_VECTOR H_TIMER1_COMPA_vect_num\n#define H_LPX_SAMPLE_CLOCK H_TCCR1B\n#define H_LPX_SAMPLE_MASK H_TIMSK1\n#define H_LPX_PWM_REGISTER H_OCR2B\n'
    (output/'hardware.h').write_text('// Generated from the compiler-selected device header; observer only.\n'+hardware_defines,encoding='ascii')
    audited=audit_registers(output/'player.elf',output/'player.lss',asm_isr,irq_registers=irq_registers,
                            sample_irq=f"__vector_{definitions['TIMER1_COMPA_vect_num' if nano_pwm else 'TIMER0_COMPA_vect_num']}",
                            allow_hardware_mul=target!='attiny88')
    size=run('avr-size',path(output/'player.elf')).decode().splitlines()[1].split()
    image=(output/'player.bin').read_bytes()
    audio=[line.split() for line in (output/'player.nm').read_text().splitlines()
           if line.split() and re.fullmatch(r'_ZL5voice(?:\..*)?',line.split()[-1])]
    if len(audio)!=1 or len(audio[0])!=4:raise ValueError('Ambiguous embedded audio array')
    start,length=int(audio[0][0],16),int(audio[0][1],16)
    if length!=len(voice) or image[start:start+length]!=voice:raise ValueError('Embedded audio differs from input')
    if len(image)!=int(size[0])+int(size[1]):raise ValueError('Unexpected Flash image gaps')
    def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
    source_files=[player,*([register_map] if shared_irq else []),
        *sorted((ROOT/'src').glob('Lpx4*')),ROOT/'profiles/Lpx4Sram512.h']
    if target=='attiny88':source_files.append(DFP/'avr/iotn88.h')
    report=dict(target=target,cpu_hz=16000000,sample_hz=8000,queue=queue,prefill=queue*3//4,
        repeat=repeat,samples=samples*repeat,compact_version=compact_version,
        supported_profiles=[4,6,15] if compact_version==9 or sparse80 else [4,6],
        assembly=assembly,asm_isr=asm_isr,sparse80=sparse80,lpc_segments=lpc_segments,mul16_unroll=mul16_unroll,universal=universal,
        flash_bytes=int(size[0])+int(size[1]),static_ram_bytes=int(size[1])+int(size[2]),
        compiler=run('avr-g++','--version').decode().splitlines()[0],compiler_options=flags,
        source_sha256={str(p.relative_to(REPO)):sha(p) for p in source_files},
        image_sha256=sha(output/'player.bin'),input_sha256=sha(source),physical_board_measured=False,
        register_audit_passed=audited,irq_registers=[f'r{r}' for r in irq_registers] if asm_isr else [],
        flash_limit=flash_limit,
        embedded_audio_bytes=len(audio_data),program_excluding_audio_bytes=len(image)-len(audio_data),
        bootloader_application_bytes=6012 if target=='attiny88' else 30720,
        fits_standard_bootloader=len(image)<=(6012 if target=='attiny88' else 30720),
        requires_isp=len(image)>(6012 if target=='attiny88' else 30720),timing_verified=False)
    report['segment_bytes']=[len(data) for data in blobs]
    report['segment_sha256']=[sha(path) for path in sources]
    report['embedded_segment_ranges']=[]
    for data in blobs:
        report['embedded_segment_ranges'].append([start,start+len(data)])
        start+=len(data)
    (output/'build.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    if report['flash_bytes']>flash_limit:
        raise ValueError(f'Complete image is{report["flash_bytes"]} bytes; limit is{flash_limit} bytes')
    return report

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('input',type=Path);ap.add_argument('output',type=Path)
    ap.add_argument('--enable-asm',action='store_true');ap.add_argument('--wsl');ap.add_argument('--avr-bin')
    ap.add_argument('--queue',type=int,choices=(16,24,32,44),help='Default: 44 universal, 32 fixed-header')
    mode=ap.add_mutually_exclusive_group()
    mode.add_argument('--universal',dest='universal',action='store_true',help='Read all LPX parameters from the file (default)')
    mode.add_argument('--fixed-header',dest='universal',action='store_false',help='Legacy opt-in ROM specialization for one recording')
    ap.set_defaults(universal=True)
    ap.add_argument('--repeat',type=int,default=1)
    ap.add_argument('--lpc-segments',type=int,choices=(1,2,4),default=2)
    ap.add_argument('--asm-isr',action='store_true')
    ap.add_argument('--enable-sparse80',action='store_true')
    ap.add_argument('--mul16-unroll',type=int,choices=(1,2,4,8,16),help='Default: 2 universal, 16 fixed-header')
    ap.add_argument('--flash-limit',type=int,default=8192,help='Hard full-image cap, at most the physical 8192 bytes')
    a=ap.parse_args()
    r=build(a.input,a.output,assembly=a.enable_asm,queue=a.queue,repeat=a.repeat,wsl=a.wsl,avr_bin=a.avr_bin,lpc_segments=a.lpc_segments,asm_isr=a.asm_isr,flash_limit=a.flash_limit,sparse80=a.enable_sparse80,mul16_unroll=a.mul16_unroll,universal=a.universal)
    print(json.dumps({k:r[k] for k in ('flash_bytes','static_ram_bytes','samples','assembly')}))
    if r['requires_isp']:print('Warning: image exceeds the MH-ET LIVE standard USB bootloader limit (6012 bytes); load with an ISP programmer.')

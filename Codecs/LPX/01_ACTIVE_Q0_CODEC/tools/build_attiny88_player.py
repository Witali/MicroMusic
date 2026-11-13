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

def audit_registers(elf,listing,reserved):
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
    for line in Path(listing).read_text().splitlines():
        match=re.match(r'^\s*([0-9a-f]+):\s+(?:[0-9a-f]{2}\s+)+(.+)$',line)
        if not match:continue
        pc=int(match[1],16);instruction=match[2].split(';')[0].strip()
        owner=next((name for a,b,name in functions if a<=pc<b),None)
        if owner is None:continue
        if instruction.split()[0] in ('mul','muls','mulsu','fmul','fmuls','fmulsu'):
            raise ValueError('Hardware multiply in an AVR25 function')
        if reserved and re.search(r'\br[23]\b',instruction) and owner!='__vector_12':
            abi=(owner=='__prologue_saves__' and instruction.startswith('push')) or (
                 owner=='__epilogue_restores__' and instruction.startswith('ldd'))
            if not abi:raise ValueError('Foreground function uses ISR-reserved registers: '+owner)
    return True

def target_path(path,wsl):
    p=Path(path).resolve()
    if wsl and os.name=='nt':
        return '/mnt/'+p.drive[0].lower()+'/'+ '/'.join(p.parts[1:])
    return str(p)

def build(source,output,*,assembly=False,queue=None,repeat=1,wsl=None,avr_bin=None,lpc_segments=2,asm_isr=False,extra_flags=(),flash_limit=8192,sparse80=False,mul16_unroll=None,output_gain=128,universal=True):
    source,output=Path(source).resolve(),Path(output).resolve()
    if output==REPO/'build' or REPO/'build' not in output.parents or source==output or output.is_symlink():
        raise ValueError('Use an output subdirectory under ignored repository build/')
    names=('audio.inc','player.elf','player.bin','player.hex','player.nm','player.lss','build.json',
           'hardware.cpp','hardware.o','hardware.bin','hardware.h')
    if any((output/n).is_symlink() or (output/n).resolve()==source or
           ((output/n).exists() and (output/n).stat().st_nlink>1) for n in names):
        raise ValueError('Output aliases input or uses a symlink')
    blob=source.read_bytes()
    if type(universal) is not bool:raise ValueError('Universal selection must be boolean')
    if mul16_unroll is None:mul16_unroll=2 if universal else 16
    if universal and (output_gain!=128 or any(flag.startswith('-DLPX4_FIXED_') for flag in extra_flags)):
        raise ValueError('Universal playback reads stream parameters without per-record specialization')
    if not isinstance(sparse80,bool):raise ValueError('Sparse80 selection must be boolean')
    version=9 if blob[:2]==b'L9' else blob[4] if len(blob)>=16 else 0
    header_bytes=13 if version==9 else 22
    flags_at=2 if version==9 else 5
    if not header_bytes<=len(blob)<=65535 or not ((version==9 or blob[:5]==b'L4HY\x05') and (blob[flags_at]&127 in (4,6) or version==9 and blob[flags_at]==15) or
            sparse80 and blob[:6]==b'L4HY\x08\x0f'):
        raise ValueError('Expected compact v5/v9, or sparse80 with its explicit enable')
    compact_version=9 if version==9 else 5
    if queue is None:queue=32 if compact_version==9 or not universal else 44
    samples=int.from_bytes(blob[5:7] if version==9 else blob[8:12],'little')
    pre_at=7 if version==9 else 12
    if queue not in (16,24,32,44) or not 1<=repeat<=255 or lpc_segments not in (1,2,4):raise ValueError('Invalid playback geometry')
    if not 1<=flash_limit<=8192:raise ValueError('Flash limit must be1..8192 bytes')
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
    (output/'audio.inc').write_text(','.join(map(str,blob))+'\n',encoding='ascii')
    flags=['-mmcu=attiny88','-DF_CPU=16000000UL','-Os','-flto','-mcall-prologues','-mrelax',
           '-fno-jump-tables','-fno-exceptions','-fno-rtti','-ffunction-sections','-fdata-sections',
           '-std=gnu++11','-DLPX4_FUNCTION_TUNING=0',f'-DLPX4_ENABLE_ASM={int(assembly)}',f'-DLPX3_LPC_SEGMENTS={lpc_segments}',
           f'-DLPX25_QUEUE={queue}',f'-DLPX25_REPEAT={repeat}',f'-DPWM_GAIN_Q7={output_gain}',
           f'-DLPX4_AVR25_MUL16_UNROLL={mul16_unroll}',
           '-include',path(ROOT/'profiles/Lpx4Sram512.h'),'-I'+path(DFP),
           '-I'+path(ROOT/'src'),'-I'+path(output)]
    if asm_isr:flags+=['-DLPX25_ENABLE_ASM_ISR=1','-DLPX25_ISR_FIXED_REGS=1','-ffixed-r2','-ffixed-r3']
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
    flags+=list(extra_flags)
    run('avr-g++',*flags,path(ROOT/'examples/ATTINY88_V5_PLAYER/player.cpp'),
        path(ROOT/'src/Lpx4HybridCore.cpp'),'-Wl,--gc-sections','-o',path(output/'player.elf'))
    for fmt,name in [('binary','player.bin'),('ihex','player.hex')]:
        run('avr-objcopy','-O',fmt,'-R','.eeprom',path(output/'player.elf'),path(output/name))
    (output/'player.nm').write_bytes(run('avr-nm','-S',path(output/'player.elf')))
    (output/'player.lss').write_bytes(run('avr-objdump','-d','-C',path(output/'player.elf')))
    audited=audit_registers(output/'player.elf',output/'player.lss',asm_isr)
    registers='TCCR0A TCNT0 OCR0A OCR0B TIMSK0 TIFR0 TCCR1A TCCR1B TCNT1L TCNT1H OCR1AL OCR1AH OCR1BL OCR1BH ICR1L ICR1H TIMSK1 TIFR1 PORTB DDRB PINB SPL SPH CLKPR'.split()
    constants='CTC0 CS00 CS01 CS02 OCIE0A OCF0A TOIE0 TOV0 OCIE1A OCF1A TOIE1 TOV1 WGM10 WGM11 WGM12 WGM13 CS10 CS11 CS12 COM1A0 PB1 TIMER0_COMPA_vect_num TIMER0_OVF_vect_num TIMER1_COMPA_vect_num TIMER1_COMPB_vect_num TIMER1_OVF_vect_num RAMSTART RAMEND FLASHEND E2END LPX25_QUEUE'.split()
    values=[(name,'_SFR_MEM_ADDR('+name+')') for name in registers]+[(name,name) for name in constants]
    text='#include <avr/io.h>\nextern "C" const unsigned short hardware[] __attribute__((used,section(".lpx_meta")))={'+','.join(v for _,v in values)+'};\n'
    (output/'hardware.cpp').write_text(text,encoding='ascii')
    run('avr-g++',*[f for f in flags if f!='-flto'],'-c',path(output/'hardware.cpp'),'-o',path(output/'hardware.o'))
    run('avr-objcopy','-O','binary','-j','.lpx_meta',path(output/'hardware.o'),path(output/'hardware.bin'))
    hardware=(output/'hardware.bin').read_bytes()
    if len(hardware)!=2*len(values):raise ValueError('Invalid vendor metadata object')
    (output/'hardware.h').write_text('// Generated from the pinned vendor ATtiny88 header; observer only.\n'+''.join(
        '#define H_'+name+' '+str(int.from_bytes(hardware[2*i:2*i+2],'little'))+'\n'
        for i,(name,_) in enumerate(values)),encoding='ascii')
    size=run('avr-size',path(output/'player.elf')).decode().splitlines()[1].split()
    image=(output/'player.bin').read_bytes()
    audio=[line.split() for line in (output/'player.nm').read_text().splitlines()
           if line.split() and re.fullmatch(r'_ZL5voice(?:\..*)?',line.split()[-1])]
    if len(audio)!=1 or len(audio[0])!=4:raise ValueError('Ambiguous embedded audio array')
    start,length=int(audio[0][0],16),int(audio[0][1],16)
    if length!=len(blob) or image[start:start+length]!=blob:raise ValueError('Embedded audio differs from input')
    if len(image)!=int(size[0])+int(size[1]):raise ValueError('Unexpected Flash image gaps')
    def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
    report=dict(target='attiny88',cpu_hz=16000000,sample_hz=8000,queue=queue,prefill=queue*3//4,
        repeat=repeat,samples=samples*repeat,compact_version=compact_version,
        supported_profiles=[4,6,15] if compact_version==9 or sparse80 else [4,6],
        assembly=assembly,asm_isr=asm_isr,sparse80=sparse80,lpc_segments=lpc_segments,mul16_unroll=mul16_unroll,universal=universal,
        flash_bytes=int(size[0])+int(size[1]),static_ram_bytes=int(size[1])+int(size[2]),
        compiler=run('avr-g++','--version').decode().splitlines()[0],compiler_options=flags,
        source_sha256={str(p.relative_to(REPO)):sha(p) for p in [ROOT/'examples/ATTINY88_V5_PLAYER/player.cpp',
            *sorted((ROOT/'src').glob('Lpx4*')),ROOT/'profiles/Lpx4Sram512.h',DFP/'avr/iotn88.h']},
        image_sha256=sha(output/'player.bin'),input_sha256=sha(source),physical_board_measured=False,
        register_audit_passed=audited,flash_limit=flash_limit,
        embedded_audio_bytes=length,program_excluding_audio_bytes=len(image)-length,
        bootloader_application_bytes=6012,fits_standard_bootloader=len(image)<=6012,
        requires_isp=len(image)>6012,timing_verified=False)
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

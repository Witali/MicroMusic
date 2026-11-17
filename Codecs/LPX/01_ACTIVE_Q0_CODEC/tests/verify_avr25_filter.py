"""Extract actual math headers and prove Tiny88 Q14 products with IRQ and C.

Requires Python stdlib, Node, AVR-GCC, g++, and the retained AVR25 vendor headers.
Use --wsl Ubuntu on Windows to compile/run the native C oracle and AVR tools.
Output remains under ignored repository build/. This arithmetic proof does not
replace complete-player timing/underrun admission.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess

REL=Path('Codecs/LPX/01_ACTIVE_Q0_CODEC')
REPO=Path(__file__).resolve().parent
while not (REPO/REL/'src/Lpx4Math.h').is_file():
    parent=REPO.parent
    if parent==REPO:raise RuntimeError('Repository root not found')
    REPO=parent
ROOT=REPO/REL
HERE=Path(__file__).resolve().parent


def sha(data):return hashlib.sha256(data).hexdigest()


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('output',type=Path);ap.add_argument('--wsl')
    ap.add_argument('--avr-bin',type=Path);ap.add_argument('--cxx',default=os.environ.get('CXX','g++'))
    ap.add_argument('--node',default='node')
    args=ap.parse_args();out=args.output.resolve()
    if REPO/'build' not in out.parents or out.is_symlink():raise ValueError('Use an output subdirectory under ignored build/')
    out.mkdir(parents=True,exist_ok=True);extracted=out/'source';extracted.mkdir(exist_ok=True)
    source_hash={};extracted_hash={}
    for name in ('Lpx4Math.h','Lpx4MultiplyAvr.h','Lpx4MultiplyC.h'):
        original=ROOT/'src'/name;destination=extracted/name
        if destination.is_symlink() or destination.exists() and destination.stat().st_nlink>1:
            raise ValueError('Extracted output aliases another file')
        data=original.read_bytes();destination.write_bytes(data)
        source_hash[original.relative_to(REPO).as_posix()]=sha(data.replace(b'\r\n',b'\n'))
        extracted_hash[name]=sha(data.replace(b'\r\n',b'\n'))
    probe=HERE/'avr25_filter.cpp';probe_data=probe.read_bytes()
    (out/'probe.cpp').write_bytes(probe_data)
    prefix=['wsl','-d',args.wsl,'--'] if args.wsl else []
    def path(value):
        p=Path(value).resolve()
        if args.wsl and os.name=='nt':return '/mnt/'+p.drive[0].lower()+'/'+ '/'.join(p.parts[1:])
        return str(p)
    def run(*command):
        p=subprocess.run([*prefix,*map(str,command)],capture_output=True)
        if p.returncode:raise RuntimeError(p.stderr.decode(errors='replace'))
        return p.stdout
    def avr(tool):return str(args.avr_bin/tool) if args.avr_bin else tool
    dfp=REPO/'ATtiny88/Music/universal/vendor/ATtiny_DFP/3.4.278/include'
    flags=['-mmcu=attiny88','-DF_CPU=16000000UL','-Os','-std=gnu++11',
        '-ffunction-sections','-fdata-sections','-DLPX4_COMPACT_VERSION=9',
        '-I'+path(dfp),'-I'+path(extracted)]
    backends={}
    for backend,selection in (('asm',['-DLPX4_ENABLE_ASM=1']),('c',['-DLPX4_ENABLE_ASM=0']),
        ('generic',['-DLPX4_ENABLE_ASM=1','-DLPX4_ARCH=LPX4_ARCH_GENERIC'])):
        stem=out/backend
        run(avr('avr-g++'),*flags,*selection,path(out/'probe.cpp'),'-Wl,--gc-sections',
            '-Wl,--undefined=filter_prepare','-Wl,--undefined=filter_product','-o',path(stem.with_suffix('.elf')))
        run(avr('avr-objcopy'),'-O','binary',path(stem.with_suffix('.elf')),path(stem.with_suffix('.bin')))
        stem.with_suffix('.nm').write_bytes(run(avr('avr-nm'),'-S',path(stem.with_suffix('.elf'))))
        backends[backend]=dict(image_sha256=sha(stem.with_suffix('.bin').read_bytes()),defines=selection)
    compiler=shlex.split(args.cxx)
    run(*compiler,'-O2','-std=c++11','-DLPX4_ENABLE_ASM=0','-DLPX4_COMPACT_VERSION=9',
        '-I'+path(extracted),path(out/'probe.cpp'),'-o',path(out/'host-reference'))
    expected=run(path(out/'host-reference'))
    if len(expected)!=2*(13*65536+16385*7):raise AssertionError('Portable C oracle case count')
    (out/'expected.bin').write_bytes(expected)
    metadata=dict(schema='lpx-avr25-filter-probe-build-v1',target='attiny88',cpu_hz=16000000,
        source_lf_sha256=source_hash,extracted_source_lf_sha256=extracted_hash,
        probe_lf_sha256=sha(probe_data.replace(b'\r\n',b'\n')),backends=backends,
        oracle_sha256=sha(expected),vendor_header_lf_sha256=sha((dfp/'avr/iotn88.h').read_bytes().replace(b'\r\n',b'\n')),
        avr_compiler=run(avr('avr-g++'),'--version').decode().splitlines()[0],
        c_compiler=run(*compiler,'--version').decode().splitlines()[0])
    (out/'build.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8',newline='\n')
    subprocess.run([args.node,str(HERE/'verify_avr25_filter.mjs'),str(out)],check=True)
    for name,digest in source_hash.items():
        if sha((REPO/name).read_bytes().replace(b'\r\n',b'\n'))!=digest:raise AssertionError('Source changed during proof')
    print('PASS: portable C, every signed16 state, every coefficient, AVR C/ASM, active IRQ and ABI')


if __name__=='__main__':main()

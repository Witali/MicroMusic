#!/usr/bin/env python3
"""Build compact Speex WB 9.8 kbit/s, its C backend and independent oracle."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import build

C_SOURCES=['speex_wb1.c','wb_qmf.c','wb_iir.c','wb_fold.c']
ASM_SOURCES=['wb_iir.S','wb_qmf.S','wb_fold.S']
DEFINES=build.DEFINES+['SPEEX_AVR_COMPACT_LSP','SPEEX_AVR_TIGHT_EXC',
    'SPEEX_AVR_PROFILE','SPEEX_AVR_FAST_MUL','SPEEX_ENABLE_WB1=1']

def prepare():
    _,source=build.prepare('profile')
    path=source/'libspeex/high_lsp_tables.c'
    text,count=re.subn(r'(const signed char \w+\[512\])=',r'\1 AVR_TABLE=',path.read_text())
    if count!=2:raise RuntimeError('Unexpected high-band LSP tables')
    path.write_text('#include "avr_tables.h"\n'+text)
    return source

def sources(source):
    return [source/'libspeex'/(s+'.c') for s in build.PROFILE_SOURCES+['high_lsp_tables']]+[
        build.ROOT/'src'/s for s in ['speex_avr.c','bits.c']+C_SOURCES]

def flags(source,backend):
    return ['-std=c11','-fwrapv','-fno-strict-aliasing',
        *['-D'+d for d in DEFINES],'-DSPEEX_NB3_ENABLE_ASM='+str(int(backend=='asm')),
        '-I'+str(source/'include'),'-I'+str(source/'libspeex'),'-I'+str(build.ROOT/'src')]

def host(compiler):
    source=prepare();out=build.ROOT/'build/wb-native';out.mkdir(exist_ok=True)
    build.run([compiler,*flags(source,'c'),'-O2','-Wno-pointer-to-int-cast',
        '-D_CRT_SECURE_NO_WARNINGS',*sources(source),build.ROOT/'tests/wb_decode.c',
        '-o',out/('decode.exe' if sys.platform=='win32' else 'decode')])

def oracle(compiler):
    _,reference=build.prepare('reference')
    out=build.ROOT/'build/wb-reference';out.mkdir(exist_ok=True)
    source=out/'source';shutil.copytree(reference,source,dirs_exist_ok=True)
    path=source/'libspeex/sb_celp.c';text=path.read_text()
    if text.count('qmf_synth(')!=3:raise RuntimeError('Unexpected upstream QMF calls')
    path.write_text('#include "wb_oracle_qmf.h"\n'+text.replace('qmf_synth(','speex_wb_reference_qmf('))
    defs=[d for d in build.DEFINES if d!='DISABLE_WIDEBAND']
    units=build.SOURCES+['modes_wb','sb_celp','high_lsp_tables','hexc_table','hexc_10_32_table']
    build.run([compiler,'-O2','-fwrapv','-fno-strict-aliasing','-Wno-pointer-to-int-cast',
        '-D_CRT_SECURE_NO_WARNINGS',*['-D'+d for d in defs],
        '-I'+str(source/'include'),'-I'+str(source/'libspeex'),'-I'+str(build.ROOT/'tests'),
        *[source/'libspeex'/(s+'.c') for s in units],build.ROOT/'tests/wb_oracle_qmf.c',
        build.ROOT/'tests/decode_rates.c','-o',out/('decode.exe' if sys.platform=='win32' else 'decode')])

def avr(compiler,backend,stream=None,load=0,destination=None,kernels=False):
    if load<0 or load>320000 or (load and stream is None):raise ValueError('Load requires a player stream and 0..320000 cycles')
    source=prepare();out=destination or build.ROOT/'build'/('wb-'+backend+('-player' if stream else '-decoder'))
    out=out.resolve();out.mkdir(parents=True,exist_ok=True)
    options=flags(source,backend)+['-mmcu=atmega328p','-mcall-prologues','-mrelax',
        '-Os','-flto','-ffunction-sections','-fdata-sections','-fstack-usage','-I'+str(out)]
    main=build.ROOT/('tests/wb_kernels.c' if kernels else 'tests/wb_decode.c')
    if stream:
        data=stream.read_bytes()
        if not data or len(data)%25 or len(data)//25>65535 or any(
            data[i]>>3!=3 or data[i+20]>>4!=9 for i in range(0,len(data),25)):
            raise ValueError('Expected complete 25-byte NB3+HB1 raw packets')
        (out/'sample.h').write_text('#define SPEEX_SAMPLE_FRAMES '+str(len(data)//25)+
            '\nstatic const uint8_t sample_data[] PROGMEM={'+','.join(map(str,data))+'};\n')
        (out/'input.json').write_text(json.dumps(dict(file=stream.name,
            sha256=hashlib.sha256(data).hexdigest(),frames=len(data)//25,frameLoadCycles=load),indent=2)+'\n')
        main=build.ROOT/'src/wb_player.c'
        if load:options+=['-DSPEEX_AVR_FRAME_LOAD_CYCLES='+str(load)]
    units=sources(source)
    if backend=='asm':units +=[build.ROOT/'src'/s for s in build.ASM_SOURCES+ASM_SOURCES]
    executable=out/'wb.elf'
    build.run([compiler,*options,*units,main,'-Wl,--gc-sections,-Map='+str(out/'wb.map'),'-o',executable],cwd=out)
    prefix=str(Path(compiler).with_name('avr-'));extension='.exe' if str(compiler).endswith('.exe') else ''
    for format,suffix in [('binary','bin'),('ihex','hex')]:
        build.run([prefix+'objcopy'+extension,'-O',format,'-R','.eeprom',executable,out/('wb.'+suffix)])
    (out/'symbols.txt').write_text(subprocess.check_output([prefix+'nm'+extension,'-n',executable],text=True))
    (out/'backend.json').write_text(json.dumps(dict(backend=backend,
        handwrittenAssembly=backend=='asm',profile='WB1-Q7-16',sampleRate=16000,
        binarySha256=hashlib.sha256((out/'wb.bin').read_bytes()).hexdigest()),indent=2)+'\n')
    if (out/'wb.bin').stat().st_size>32768:raise ValueError('Firmware and stream exceed ATmega328P Flash')
    build.run([prefix+'size'+extension,'-C','--mcu=atmega328p',executable])
    return out

def export_c(destination):
    build.export_c(destination);source=prepare();private=destination/'src'
    shutil.copyfile(source/'libspeex/high_lsp_tables.c',private/'high_lsp_tables.c')
    for name in C_SOURCES:shutil.copyfile(build.ROOT/'src'/name,private/name)
    shutil.copyfile(build.ROOT/'src/speex_wb1.h',destination/'include/speex_wb1.h')
    path=destination/'sources.json';manifest=json.loads(path.read_text())
    manifest['sources']+=['src/high_lsp_tables.c']+['src/'+s for s in C_SOURCES]
    manifest['definitions']+=['SPEEX_ENABLE_WB1=1'];manifest['profiles']=['NB3','WB1-Q7-16']
    path.write_text(json.dumps(manifest,indent=2)+'\n')
    path=destination/'CMakeLists.txt';path.write_text(path.read_text()+
        '\ntarget_sources(speex_nb3 PRIVATE src/high_lsp_tables.c '+
        ' '.join('src/'+s for s in C_SOURCES)+')\n'+
        'target_compile_definitions(speex_nb3 PRIVATE SPEEX_ENABLE_WB1=1)\n')
    hashes={p.relative_to(destination).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(destination.rglob('*')) if p.is_file() and p.name!='SHA256.json'}
    (destination/'SHA256.json').write_text(json.dumps(hashes,indent=2)+'\n')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc');parser.add_argument('--reference',action='store_true')
    parser.add_argument('--avr-gcc');parser.add_argument('--backend',choices=['asm','c'],default='c')
    parser.add_argument('--stream',type=Path);parser.add_argument('--frame-load-cycles',type=int,default=0)
    parser.add_argument('--out',type=Path);parser.add_argument('--export-c',type=Path)
    parser.add_argument('--kernels',action='store_true',help='AVR mailbox comparing C and ASM kernels')
    args=parser.parse_args()
    if args.reference and not args.cc:parser.error('--reference requires --cc')
    if args.stream and not args.avr_gcc:parser.error('--stream requires --avr-gcc')
    if args.kernels and (not args.avr_gcc or args.backend!='asm' or args.stream):
        parser.error('--kernels requires --avr-gcc --backend asm and no stream')
    if args.cc:
        host(args.cc)
        if args.reference:oracle(args.cc)
    if args.avr_gcc:avr(args.avr_gcc,args.backend,args.stream,args.frame_load_cycles,args.out,args.kernels)
    if args.export_c:export_c(args.export_c.resolve())
    if not(args.cc or args.avr_gcc or args.export_c):parser.error('Select --cc, --avr-gcc or --export-c')
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Play an encoder manifest continuously through the full AVR IRQ queue.

The generated harness derives from profile.cpp with explicit segment switching.
All firmware/media stay in the supplied ignored build directory.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from batch_decoder import BatchSession
from profile_avr import linux_path


def run(source,output,avr_bin,runner,lib=None,wsl=None):
    source,output,avr_bin=map(Path,(source,output,avr_bin));output.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((source/'manifest.json').read_text(encoding='utf-8'))
    packets=[];count=0
    for item in manifest['segments']:
        path=(source/item['file']).resolve()
        if path.parent!=source.resolve():raise ValueError('Segment path escapes input directory')
        blob=path.read_bytes();samples=int.from_bytes(blob[8:12],'little')
        if blob[:6]!=b'L4HY\x02\x03' or len(blob)>65535 or samples!=item['samples'] or count!=item['offset_samples']:
            raise ValueError('Segment header/manifest mismatch')
        packets.append(blob);count+=samples
    if not 1<=len(packets)<=255 or count>64000 or count!=manifest['samples']:raise ValueError('Chain limit is 64000 samples / 255 files')
    header='#pragma once\n#include <stdint.h>\n#include <avr/pgmspace.h>\n'
    for i,blob in enumerate(packets):
        header+=f'static const uint8_t profile_voice_{i}[] PROGMEM={{'+','.join(map(str,blob))+'};\n'
    header+='static const uint8_t* const profile_voices[] PROGMEM={'+','.join('profile_voice_'+str(i) for i in range(len(packets)))+'};\n'
    header+='static const uint16_t profile_sizes[] PROGMEM={'+','.join(str(len(b)) for b in packets)+'};\n'
    original=(ROOT.parent/'validation/atmega328p/profile.cpp').read_text()
    def patch(text,old,new):
        if text.count(old)!=1:raise ValueError('Profiling harness changed: '+old)
        return text.replace(old,new)
    derived=patch(original,'static Lpx4HybridCore decoder;','''static Lpx4HybridCore decoder;
static uint8_t segment;
static bool beginSegment(){
    return decoder.begin((const uint8_t*)pgm_read_ptr(&profile_voices[segment]),pgm_read_word(&profile_sizes[segment]));
}''')
    derived=patch(derived,'const bool ok = decoder.next(value);',f'''if(decoder.finished() && segment+1<{len(packets)}){{
        ++segment;if(!beginSegment()){{profile_error=1;profile_decode_active=0;return false;}}
    }}
    const bool ok = decoder.next(value);''')
    derived=patch(derived,'decoder.begin(profile_voice, sizeof(profile_voice))','beginSegment()')
    derived=patch(derived,'const uint32_t total = decoder.samples();',f'const uint32_t total = {count}UL;')
    (output/'voice_data.h').write_bytes(header.encode());(output/'chain.cpp').write_bytes(derived.encode())
    exe='.exe' if os.name=='nt' else ''
    options=['-mmcu=atmega328p','-DF_CPU=16000000UL','-Os','-std=gnu++11','-DLPX4_ENABLE_ASM=1',
        '-DLPX4_AVR_DOT_UNROLL=3','-DLPX4_PROFILE_QUEUE=256','-DLPX4_PROFILE_PREFILL=160','-fno-exceptions','-fno-rtti']
    subprocess.run([str(avr_bin/('avr-g++'+exe)),*options,'-I'+str(ROOT/'src'),'-I'+str(output),
        str(output/'chain.cpp'),str(ROOT/'src/Lpx4HybridCore.cpp'),'-o',str(output/'chain.elf')],check=True,capture_output=True)
    if wsl:
        command=['wsl','-d',wsl,'--','env']
        if lib:command+=['LD_LIBRARY_PATH='+linux_path(lib)]
        command += [linux_path(runner),linux_path(output/'chain.elf'),linux_path(output/'valid.pcm8'),linux_path(output/'timing.json')]
        subprocess.run(command,check=True,capture_output=True)
    else:
        env=os.environ.copy()
        if lib:env['LD_LIBRARY_PATH']=str(Path(lib).resolve())
        subprocess.run([str(Path(runner).resolve()),str((output/'chain.elf').resolve()),
            str((output/'valid.pcm8').resolve()),str((output/'timing.json').resolve())],env=env,check=True,capture_output=True)
    with BatchSession('batch') as decoder:
        expected=b''.join(decoder.decode_one(b,int.from_bytes(b[8:12],'little')).tobytes() for b in packets)
    actual=(output/'valid.pcm8').read_bytes();report=json.loads((output/'timing.json').read_text())
    if actual!=expected or len(actual)!=count or report['underruns'] or report['decoder_error']:
        raise AssertionError('Continuous segment chain failed')
    report.update(segments=len(packets),samples=count,pwm_native_exact=True,queue_bytes=256,prefill_samples=160,
        compiler_options=options,segment_sha256=[hashlib.sha256(b).hexdigest() for b in packets],
        source_harness_sha256=hashlib.sha256(original.encode()).hexdigest(),
        derived_harness_sha256=hashlib.sha256(derived.encode()).hexdigest(),
        elf_sha256=hashlib.sha256((output/'chain.elf').read_bytes()).hexdigest())
    (output/'verification.json').write_bytes((json.dumps(report,indent=2)+'\n').encode())
    print('chain',len(packets),'files',count,'samples','underruns',report['underruns'],'exact',actual==expected)
    return report


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('source',type=Path);ap.add_argument('output',type=Path)
    ap.add_argument('--avr-bin',type=Path,required=True);ap.add_argument('--sim-runner',type=Path,required=True)
    ap.add_argument('--sim-lib-dir',type=Path);ap.add_argument('--wsl')
    a=ap.parse_args();run(a.source,a.output,a.avr_bin,a.sim_runner,a.sim_lib_dir,a.wsl)

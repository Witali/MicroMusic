"""Measure an actual linked v5-only AVR firmware containing a complete clip.

All reset segments and their Flash lookup tables are included. The existing
IRQ/profiling harness remains intact, with explicit segment switching. This
measures firmware size; timing admission is a separate optional simulation.
Generated media, source, logs and firmware must remain in ignored build storage.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

from benchmark_speech_flash import (CANDIDATES, HARNESS, canonical, command_flags,
    digest, environment, parse_symbols, source_hashes, srcdir, toolpath)
from output_paths import protect_outputs
from speech_compact import unpack, decode_model
from standard_metrics import pwm_duties
from profile_avr import linux_path

REPOSITORY=Path(__file__).resolve().parents[4]
ARTIFACT_NAMES=('voice_data.h','chain.cpp','profile.elf','program.bin','profile.map',
    'cost.json','verification.json','valid.pcm8','timing.json',
    'compile.stdout.log','compile.stderr.log')


def checked_output(path):
    path=Path(path).resolve()
    if not path.is_relative_to((REPOSITORY/'build').resolve()):
        raise ValueError('Firmware artifacts must stay inside this repository ignored build directory')
    return path


def guard_artifacts(folder, source=None, inputs=()):
    """Never follow pre-existing output aliases or overwrite build inputs."""
    folder=checked_output(folder)
    targets=[folder/name for name in ARTIFACT_NAMES]
    for path in targets:
        checked_output(path)
        if path.is_symlink() or (path.exists() and path.stat().st_nlink>1):
            raise ValueError('Firmware outputs must not be symlinks or hard links')
    sources=[Path(__file__),*(p for p in HARNESS.rglob('*') if p.is_file()),*inputs]
    if source is not None:
        sources.extend(p for p in Path(source).rglob('*') if p.is_file())
    protect_outputs(sources,targets)
    return folder


def chain_harness(sample_counts):
    """Identical reset geometry uses identical derived source and build identity."""
    original=(HARNESS/'profile.cpp').read_text(encoding='utf-8')
    def replace(old,new):
        nonlocal original
        if original.count(old)!=1:raise ValueError('Profiling harness contract changed')
        original=original.replace(old,new,1)
    replace('static Lpx4HybridCore decoder;','''static Lpx4HybridCore decoder;
static uint8_t segment;
static bool beginSegment(){
    return decoder.begin((const uint8_t*)pgm_read_ptr(&profile_voices[segment]),
                         pgm_read_word(&profile_sizes[segment]));
}''')
    replace('decoder.begin(profile_voice, sizeof(profile_voice))','beginSegment()')
    replace('const bool ok = decoder.next(value);',f'''if(decoder.finished() && segment+1<{len(sample_counts)}){{
        ++segment;
        if(!beginSegment()){{profile_error=1;profile_decode_active=0;return false;}}
    }}
    const bool ok = decoder.next(value);''')
    replace('const uint32_t total = decoder.samples();',f'const uint32_t total = {sum(sample_counts)}UL;')
    return original


def voice_header(streams):
    text='#pragma once\n#include <stdint.h>\n#include <avr/pgmspace.h>\n'
    for i,blob in enumerate(streams):
        text+=f'static const uint8_t profile_voice_{i}[] PROGMEM __attribute__((used))={{\n'
        text+='\n'.join(','.join(str(b) for b in blob[j:j+24])+',' for j in range(0,len(blob),24))+'\n};\n'
    text+='static const uint8_t* const profile_voices[] PROGMEM={'+','.join(f'profile_voice_{i}' for i in range(len(streams)))+'};\n'
    text+='static const uint16_t profile_sizes[] PROGMEM={'+','.join(str(len(b)) for b in streams)+'};\n'
    return text


def embedded_streams(elf,binary,avr_bin,streams,env):
    symbols=parse_symbols(subprocess.check_output([str(toolpath(avr_bin,'avr-nm')),'-S','--defined-only',str(elf)],text=True))
    if not set(env['required_symbols'])<=set(symbols) or not set(env['retained_profile_symbols'])<=set(symbols):
        raise ValueError('Linked image lacks retained profiling state')
    data=binary.read_bytes();ranges=[]
    for i,blob in enumerate(streams):
        matches=[entry for name,entry in symbols.items() if re.search(r'profile_voice_'+str(i)+r'(?:\.|$)',name) and entry['size']==len(blob)]
        matches=[entry for entry in matches if data[entry['address']:entry['address']+len(blob)]==blob]
        if len(matches)!=1:raise ValueError('Cannot prove exact embedded segment storage')
        entry=matches[0];start=entry['address'];end=start+len(blob)
        if start<0 or end>len(data) or any(start<b and a<end for a,b in ranges):
            raise ValueError('Embedded segment ranges overlap or escape Flash')
        ranges.append((start,end))
    # Address initializers are retained unchanged and read by the IRQ runner.
    sections=subprocess.check_output([str(toolpath(avr_bin,'avr-objdump')),'-h',str(elf)],text=True)
    match=re.search(r'^\s*\d+\s+\.data\s+([0-9a-f]+)\s+([0-9a-f]+)\s+([0-9a-f]+)',sections,re.M|re.I)
    if not match:raise ValueError('Cannot locate initialized hardware address data')
    _,vma,lma=(int(x,16) for x in match.groups());constants={}
    for name in ('profile_pwm_address','profile_spl_address','profile_sph_address'):
        entry=symbols[name];offset=lma+entry['address']-vma
        if entry['size']!=2 or not 0<=offset<=len(data)-2:raise ValueError('Invalid hardware address metadata')
        constants[name]=int.from_bytes(data[offset:offset+2],'little')
    return {'ranges':[list(pair) for pair in ranges],'hardware_address_constants':constants}


def measure(streams,output,avr_bin,*,source=None,assembly=True,irq=0):
    """Return stream-bound full-image cost evidence and optional cached artifacts."""
    if (not isinstance(streams,(list,tuple)) or not 1<=len(streams)<=255
            or any(not isinstance(b,(bytes,bytearray,memoryview)) for b in streams)):
        raise ValueError('Expected 1..255 bytes-like v5 reset segments')
    if not isinstance(assembly,bool):raise ValueError('assembly must be boolean')
    if isinstance(irq,bool) or not isinstance(irq,int) or not 0<=irq<=600:
        raise ValueError('IRQ load must be an integer from 0 to 600')
    streams=[bytes(b) for b in streams]
    sample_counts=[unpack(b)[0] for b in streams]
    if sum(sample_counts)>0xffffffff:raise ValueError('Complete clip exceeds32-bit sample count')
    folder=checked_output(output);avr_bin=Path(avr_bin)
    source=Path(source) if source is not None else Path(__file__).resolve().parents[1]
    src=srcdir(source);guard_artifacts(folder,src)
    env=environment(source,avr_bin,True)
    spec=CANDIDATES['unroll1-tune0-lto-call-relax'];flags=command_flags(env,spec,assembly,irq)
    derived=chain_harness(sample_counts);source_fingerprint=hashlib.sha256(canonical(env['source_sha256'])).hexdigest()
    build={'environment':env,'compiler_options':flags,'derived_harness_sha256':hashlib.sha256(derived.encode()).hexdigest(),
           'collector_sha256':digest(Path(__file__)),'segment_sample_counts':sample_counts}
    build_fingerprint=hashlib.sha256(canonical(build)).hexdigest();hashes=[hashlib.sha256(b).hexdigest() for b in streams]
    identity=hashlib.sha256(canonical([build_fingerprint,hashes])).hexdigest();cache=folder/'cost.json'
    if cache.exists():
        old=json.loads(cache.read_text());cost=old.get('cost',{})
        if (old.get('fingerprint')==identity and old.get('cost_sha256')==hashlib.sha256(canonical(cost)).hexdigest()
                and (folder/'profile.elf').is_file() and (folder/'program.bin').is_file()
                and digest(folder/'profile.elf')==cost.get('image_sha256')
                and digest(folder/'program.bin')==cost.get('binary_sha256')):
            if source_hashes(src)!=env['source_sha256']:raise ValueError('Decoder sources changed')
            return cost
    folder.mkdir(parents=True,exist_ok=True)
    (folder/'voice_data.h').write_text(voice_header(streams),encoding='utf-8',newline='\n')
    (folder/'chain.cpp').write_text(derived,encoding='utf-8',newline='\n')
    elf=folder/'profile.elf';binary=folder/'program.bin'
    command=[str(toolpath(avr_bin,'avr-g++')),*flags,'-I'+str(src),'-I'+str(folder),str(folder/'chain.cpp'),
             str(src/'Lpx4HybridCore.cpp'),'-Wl,-Map='+str(folder/'profile.map'),'-o',str(elf)]
    result=subprocess.run(command,capture_output=True)
    (folder/'compile.stdout.log').write_bytes(result.stdout);(folder/'compile.stderr.log').write_bytes(result.stderr)
    if result.returncode:raise RuntimeError('Firmware link failed; see ignored compile.stderr.log (target memory may be exceeded)')
    if source_hashes(src)!=env['source_sha256']:raise ValueError('Decoder sources changed during linking')
    subprocess.run([str(toolpath(avr_bin,'avr-objcopy')),'-O','binary','-R','.eeprom',str(elf),str(binary)],check=True,capture_output=True)
    sizes=subprocess.check_output([str(toolpath(avr_bin,'avr-size')),str(elf)],text=True)
    match=re.search(r'^\s*(\d+)\s+(\d+)\s+(\d+)\s+',sizes,re.M)
    if not match:raise ValueError('Cannot parse linked firmware sections')
    text,data,bss=map(int,match.groups());proof=embedded_streams(elf,binary,avr_bin,streams,env)
    cost={'schema':'lpx-v5-firmware-cost-v1','stream_sha256':hashes,'stream_bytes':sum(map(len,streams)),
          'flash_bytes':text+data,'program_flash_bytes':text+data-sum(map(len,streams)),
          'text_bytes':text,'data_bytes':data,'bss_bytes':bss,'static_sram_bytes':data+bss,
          'image_kind':'elf','image_sha256':digest(elf),'binary_sha256':digest(binary),
          'source_fingerprint':source_fingerprint,'build_fingerprint':build_fingerprint,
          'embedded_streams_exact':True,'complete_image':True,'measurement':'linked-elf-text-plus-data',
          'segments':len(streams),'samples':sum(sample_counts),'environment':env,'compiler_options':flags,
          'harness_sha256':build['derived_harness_sha256'],'hardware_address_constants':proof['hardware_address_constants'],
          'embedded_segment_ranges':proof['ranges'],'assembly_enabled':bool(assembly),'extra_irq_cycles':irq,
          'timing_verified':False,'physical_board_measured':False}
    cache.write_text(json.dumps({'fingerprint':identity,'cost_sha256':hashlib.sha256(canonical(cost)).hexdigest(),
                                'cost':cost},indent=2)+'\n',encoding='utf-8',newline='\n')
    return cost


def validate_timing(report,actual_pwm,expected_pwm,cost):
    """Validate complete-chain playback separately from bounded decode profiling.

    validation/atmega328p/sim_profile.c records at most 64000 decode durations:
    its durations[64000] array and decode_count guard cap all decode_wall_cycles
    statistics. Longer runs still verify every PWM byte, output tick, produced
    sample and underrun counter. A runner that counts every duration is accepted
    too. The returned coverage fields scope the decode statistics explicitly.
    This pure check can revalidate saved artifacts without rerunning simulation.
    """
    if not isinstance(report,dict) or not isinstance(cost,dict):
        raise ValueError('Timing report and firmware cost must be objects')
    if (not isinstance(actual_pwm,(bytes,bytearray,memoryview)) or
            not isinstance(expected_pwm,(bytes,bytearray,memoryview))):
        raise ValueError('Actual and expected PWM must be bytes-like')
    samples=cost.get('samples')
    if isinstance(samples,bool) or not isinstance(samples,int) or not 1<=samples<=0xffffffff:
        raise ValueError('Firmware sample count must be a positive 32-bit integer')
    counts=('played','produced','decode_calls','timer_ticks','underruns','decoder_error',
            'stack_margin_bytes','cpu_hz','audio_hz')
    if any(isinstance(report.get(k),bool) or not isinstance(report.get(k),int) for k in counts):
        raise ValueError('Timing counters must be integers')
    actual_pwm=bytes(actual_pwm);expected_pwm=bytes(expected_pwm)
    timed=report['decode_calls'];complete=timed==samples
    covered=complete or samples>64000 and timed==64000
    if (len(expected_pwm)!=samples or actual_pwm!=expected_pwm or report['underruns']
            or report['decoder_error'] or report.get('done')!=1
            or report['played']!=samples or report['produced']!=samples
            or not covered or report['timer_ticks']!=samples
            or report['stack_margin_bytes']<=0 or report['cpu_hz']!=16000000 or report['audio_hz']!=8000):
        raise AssertionError('Complete-chain IRQ/PWM/timing verification failed')
    verified={k:v for k,v in report.items() if k!='occupancy_trace'}
    verified.update(cost=cost,pwm_model_exact=True,pwm_sha256=hashlib.sha256(expected_pwm).hexdigest(),
        timing_verified=True,decode_timing_samples=timed,decode_timing_complete=complete,
        decode_timing_statistics_scope='complete-chain' if complete else 'first-64000-samples',
        decode_timing_limit_reason=None if complete else 'sim_profile.c decode duration buffer limit')
    return verified


def simulate(streams,output,avr_bin,runner,*,lib=None,wsl=None,source=None,irq=0):
    """Verify the entire chain against independent-model PWM with active IRQ."""
    folder=guard_artifacts(output,inputs=[runner])
    cost=measure(streams,folder,avr_bin,source=source,irq=irq)
    streams=[bytes(b) for b in streams]
    expected=b''.join(pwm_duties(decode_model(b)).tobytes() for b in streams)
    valid=folder/'valid.pcm8';timing=folder/'timing.json'
    if wsl:
        command=['wsl','-d',wsl,'--','env']
        if lib:command+=['LD_LIBRARY_PATH='+linux_path(lib)]
        command += [linux_path(runner),linux_path(folder/'profile.elf'),linux_path(valid),linux_path(timing)]
    else:
        import os
        env_vars=os.environ.copy()
        if lib:env_vars['LD_LIBRARY_PATH']=str(Path(lib).resolve())
        command=[str(Path(runner).resolve()),str(folder/'profile.elf'),str(valid),str(timing)]
    subprocess.run(command,check=True,capture_output=True,**({} if wsl else {'env':env_vars}))
    report=validate_timing(json.loads(timing.read_text()),valid.read_bytes(),expected,cost)
    (folder/'verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path);parser.add_argument('streams',type=Path,nargs='+')
    parser.add_argument('--avr-bin',type=Path,required=True);parser.add_argument('--source',type=Path)
    parser.add_argument('--runner',type=Path);parser.add_argument('--lib',type=Path);parser.add_argument('--wsl')
    parser.add_argument('--irq',type=int,default=0)
    args=parser.parse_args();folder=checked_output(args.output)
    guard_artifacts(folder,inputs=args.streams)
    streams=[p.read_bytes() for p in args.streams]
    report=(simulate(streams,folder,args.avr_bin,args.runner,lib=args.lib,wsl=args.wsl,source=args.source,irq=args.irq)
            if args.runner else measure(streams,folder,args.avr_bin,source=args.source,irq=args.irq))
    cost=report.get('cost',report)
    print(json.dumps({k:cost[k] for k in ('segments','samples','stream_bytes','flash_bytes','program_flash_bytes')}))


if __name__=='__main__':main()

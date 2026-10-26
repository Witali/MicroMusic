"""Bounded AVR program-Flash screen and full-PWM verification on fixed speech.

--source selects the actual src tree compiled, including immutable snapshots.
Reference output is the saved PCM WAV, never an active native decoder build.
All generated headers, binaries, logs and caches must stay in ignored build/.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, subprocess
from pathlib import Path
import numpy as np
import soundfile as sf
from benchmark_standards import save
from profile_avr import ROOT, HARNESS, linux_path
from speech_compact import unpack, pack, decode_model
from standard_metrics import pwm_duties

CASES=tuple(f'case-{i:02d}' for i in range(1,5))
PROFILES=(4,6)
BASE={'queue':512,'prefill':384,'cpu_hz':16000000,'audio_hz':8000,
      'v3_features':24,'speech':True,'speech_compact':True}


def candidate(unroll=9,tuning=7,*flags):
    return {'unroll':unroll,'tuning':tuning,'flags':list(flags)}


LTO=('-flto',)
GC=('-ffunction-sections','-fdata-sections','-Wl,--gc-sections')
CALL=('-mcall-prologues',)
RELAX=('-mrelax',)
CANDIDATES={
 'baseline':candidate(), 'unroll1':candidate(1), 'unroll3':candidate(3),
 'tune0':candidate(9,0), 'tune1':candidate(9,1), 'tune3':candidate(9,3),
 'lto':candidate(9,7,*LTO), 'sections':candidate(9,7,*GC),
 'call':candidate(9,7,*CALL), 'relax':candidate(9,7,*RELAX),
 'lto-sections':candidate(9,7,*LTO,*GC), 'lto-call':candidate(9,7,*LTO,*CALL),
 'lto-relax':candidate(9,7,*LTO,*RELAX), 'sections-relax':candidate(9,7,*GC,*RELAX),
 'lto-sections-relax':candidate(9,7,*LTO,*GC,*RELAX),
 'lto-call-relax':candidate(9,7,*LTO,*CALL,*RELAX),
 'lto-sections-call-relax':candidate(9,7,*LTO,*GC,*CALL,*RELAX),
 'unroll1-lto-sections-call-relax':candidate(1,7,*LTO,*GC,*CALL,*RELAX),
 'tune0-lto-sections-call-relax':candidate(9,0,*LTO,*GC,*CALL,*RELAX),
 'tune1-lto-sections-call-relax':candidate(9,1,*LTO,*GC,*CALL,*RELAX),
 'unroll1-tune0-lto-sections-call-relax':candidate(1,0,*LTO,*GC,*CALL,*RELAX),
 'unroll1-tune1-lto-sections-call-relax':candidate(1,1,*LTO,*GC,*CALL,*RELAX),
 'unroll3-tune0-lto-sections-call-relax':candidate(3,0,*LTO,*GC,*CALL,*RELAX),
 'unroll1-tune0-lto-call-relax':candidate(1,0,*LTO,*CALL,*RELAX),
}


def sha(data):return hashlib.sha256(data).hexdigest()
def digest(path):return sha(Path(path).read_bytes())
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def need(condition,message):
    if not condition:raise ValueError(message)


def srcdir(source):
    source=Path(source).resolve();src=source/'src' if (source/'src').is_dir() else source
    need((src/'Lpx4HybridCore.cpp').is_file(),'--source must contain src/Lpx4HybridCore.cpp or be that src directory')
    return src


def source_hashes(src):
    return {p.relative_to(src).as_posix():digest(p) for p in sorted(src.rglob('*')) if p.is_file()}


def external_symbols():
    runner=(HARNESS/'sim_profile.c').read_text(encoding='utf-8')
    required=set(re.findall(r'symbol\(&firmware,\s*"([A-Za-z_][A-Za-z_0-9]*)"\)',runner))
    block=(HARNESS/'profile.cpp').read_text(encoding='utf-8').split('extern "C" {',1)[1].split('}',1)[0]
    retained=sorted(set(re.findall(r'\bprofile_[A-Za-z_0-9]+\b',block))|{x for x in required if x.startswith('profile_')})
    need({'profile_pwm_address','profile_spl_address','profile_sph_address'}<=set(retained),'Harness address metadata inventory failed')
    return sorted(required),retained


def toolpath(avr_bin,name):return Path(avr_bin)/(name+('.exe' if os.name=='nt' else ''))


def environment(source,avr_bin,compact_only=False):
    src=srcdir(source);compiler=toolpath(avr_bin,'avr-g++')
    if compact_only:
        need('LPX4_COMPACT_ONLY' in (src/'Lpx4HybridCore.h').read_text(encoding='utf-8'),
             '--compact-only requested for a source without that profile')
    cc1=Path(subprocess.check_output([str(compiler),'-print-prog-name=cc1plus'],text=True).strip())
    files=[compiler,cc1,HARNESS/'profile.cpp',HARNESS/'sim_profile.c',Path(__file__),
           ROOT/'tools/standard_metrics.py',ROOT/'tools/speech_compact.py',ROOT/'tools/q0_model.py']
    files.extend(toolpath(avr_bin,n) for n in ('avr-as','avr-ld','avr-objcopy','avr-size','avr-nm','avr-objdump'))
    for name in ('libgcc.a','libc.a','crtatmega328p.o'):
        path=Path(subprocess.check_output([str(compiler),'-mmcu=atmega328p','-print-file-name='+name],text=True).strip())
        if path.is_file():files.append(path)
    vendor=Path(avr_bin).parent/'avr/include'
    for name in ('avr/io.h','avr/iom328p.h','avr/pgmspace.h','avr/interrupt.h','util/atomic.h'):
        if (vendor/name).is_file():files.append(vendor/name)
    required,retained=external_symbols()
    return {'source_sha256':source_hashes(src),'dependencies':{p.name:digest(p) for p in files},
        'compiler':subprocess.check_output([str(compiler),'--version'],text=True).splitlines()[0],
        'settings':BASE,'compact_only':bool(compact_only),'required_symbols':required,
        'retained_profile_symbols':retained}


def fixed_inputs(study,cases=CASES,profiles=PROFILES,model=True):
    study=Path(study);manifest=load(study/'manifest.json');result=[]
    for case in cases:
        for p in profiles:
            row=manifest['cases'][case]['profiles'][str(p)]['variants']['enhanced_v5']
            path=study/case/str(p)/'enhanced_v5.l4hy';blob=path.read_bytes()
            pcm,rate=sf.read(path.with_suffix('.wav'),dtype='int16')
            need(blob[:5]==b'L4HY\x05' and sha(blob)==row['stream_sha256'],'Fixed enhanced stream changed')
            need(rate==8000 and pcm.shape==(32000,) and sha(pcm.astype('<i2').tobytes())==row['pcm16_sha256'],
                 'Fixed enhanced PCM reference changed')
            if model:need(np.array_equal(pcm,decode_model(blob)),'Saved PCM/model mismatch')
            pwm=pwm_duties(pcm).tobytes();need(sha(pwm)==row['pwm_sha256'],'Saved PWM reference changed')
            result.append({'id':f'{case}-{p}','case':case,'profile':p,'path':path,'blob':blob,
                           'pwm':pwm,'samples':32000,'stream_sha256':sha(blob),'pcm_sha256':row['pcm16_sha256']})
    return result


def command_flags(env,spec,assembly=True,irq=0):
    flags=['-mmcu=atmega328p','-DF_CPU=16000000UL','-Os','-std=gnu++11','-fno-exceptions','-fno-rtti',
        '-DLPX4_PROFILE_QUEUE=512','-DLPX4_PROFILE_PREFILL=384',f'-DLPX4_PROFILE_IRQ_LOAD={irq}',
        f'-DLPX4_AVR_DOT_UNROLL={spec["unroll"]}',f'-DLPX4_FUNCTION_TUNING={spec["tuning"]}',
        '-DLPX4_V3_FEATURES=24','-DLPX4_ENABLE_SPEECH=1','-DLPX4_ENABLE_SPEECH_COMPACT=1',
        f'-DLPX4_COMPACT_ONLY={int(env["compact_only"])}',f'-DLPX4_ENABLE_ASM={int(assembly)}',*spec['flags']]
    # Use the same retention policy for baseline and all candidates. These
    # externally observed symbols are part of the measurement harness ABI.
    flags.extend('-Wl,-u,'+name for name in env['retained_profile_symbols'])
    return flags


def parse_symbols(text):
    result={}
    for line in text.splitlines():
        fields=line.split()
        if len(fields)>=3 and re.fullmatch(r'[0-9a-fA-F]+',fields[0]):
            size=int(fields[1],16) if len(fields)>=4 and re.fullmatch(r'[0-9a-fA-F]+',fields[1]) else None
            result[fields[-1]]={'address':int(fields[0],16),'size':size}
    return result


def embedded_audio_and_metadata(elf,binary,avr_bin,blob,env):
    text=subprocess.check_output([str(toolpath(avr_bin,'avr-nm')),'-S','--defined-only',str(elf)],text=True)
    symbols=parse_symbols(text)
    need(set(env['required_symbols'])<=set(symbols),'ELF lacks a simulator-required symbol')
    need(set(env['retained_profile_symbols'])<=set(symbols),'ELF stripped profiling state')
    state={name:symbols[name] for name in env['retained_profile_symbols']}
    for name,entry in state.items():
        need(entry['size'] in (1,2,4) and 0x100<=(entry['address']&0xffff)<=0x8ff,
             'Profiling state has invalid storage/size')
    voices=[v for name,v in symbols.items() if 'profile_voice' in name and v['size']==len(blob)]
    data=binary.read_bytes()
    need(any(data[v['address']:v['address']+len(blob)]==blob for v in voices),
         'Cannot prove exact embedded audio bytes; Flash subtraction is invalid')
    need(data.count(blob)==1,'Embedded audio has ambiguous duplicate storage')
    sections=subprocess.check_output([str(toolpath(avr_bin,'avr-objdump')),'-h',str(elf)],text=True)
    match=re.search(r'^\s*\d+\s+\.data\s+([0-9a-f]+)\s+([0-9a-f]+)\s+([0-9a-f]+)',sections,re.M|re.I)
    need(match is not None,'Cannot locate harness address initializer data')
    _,vma,lma=(int(x,16) for x in match.groups());constants={}
    for name in ('profile_pwm_address','profile_spl_address','profile_sph_address'):
        entry=state[name];offset=lma+entry['address']-vma
        need(entry['size']==2 and 0<=offset<=len(data)-2,'Invalid hardware-address metadata object')
        constants[name]=int.from_bytes(data[offset:offset+2],'little')
    return {'profile_symbol_count':len(state),'profile_state':state,
            'hardware_address_constants':constants,'embedded_audio_exact':True}


def same_harness(image,reference):
    need(image['hardware_address_constants']==reference['hardware_address_constants'],
         'Candidate changed hardware address metadata')
    need({k:v['size'] for k,v in image['profile_state'].items()}==
         {k:v['size'] for k,v in reference['profile_state'].items()},'Candidate changed harness state storage')


def compile_image(source,env,spec,item,folder,avr_bin,assembly=True,irq=0,require=False):
    src=srcdir(source);folder=Path(folder);flags=command_flags(env,spec,assembly,irq)
    identity=sha(canonical([env,spec,item['stream_sha256'],assembly,irq]));cache=folder/'compile.json'
    if cache.exists():
        old=load(cache)
        if old.get('fingerprint')==identity and old.get('metadata_sha256')==sha(canonical(old.get('image'))):
            image=old['image']
            if all((folder/name).exists() and digest(folder/name)==image[key] for name,key in
                   (('profile.elf','elf_sha256'),('profile.hex','hex_sha256'),('program.bin','program_sha256'))):
                need(source_hashes(src)==env['source_sha256'],'Source changed during study')
                return image
    need(not require,'Missing/stale compilation cache')
    need(source_hashes(src)==env['source_sha256'],'Source changed before compilation')
    folder.mkdir(parents=True,exist_ok=True);blob=item['blob']
    header='#pragma once\n#include <stdint.h>\n#include <avr/pgmspace.h>\nstatic const uint8_t profile_voice[] PROGMEM __attribute__((used)) = {\n'
    header+='\n'.join(','.join(str(x) for x in blob[i:i+24])+',' for i in range(0,len(blob),24))+'\n};\n'
    (folder/'voice_data.h').write_bytes(header.encode())
    elf=folder/'profile.elf';hexfile=folder/'profile.hex';binary=folder/'program.bin'
    command=[str(toolpath(avr_bin,'avr-g++')),*flags,'-I'+str(src),'-I'+str(folder),
        str(HARNESS/'profile.cpp'),str(src/'Lpx4HybridCore.cpp'),'-Wl,-Map='+str(folder/'profile.map'),'-o',str(elf)]
    run=subprocess.run(command,capture_output=True)
    (folder/'compile.stdout.log').write_bytes(run.stdout);(folder/'compile.stderr.log').write_bytes(run.stderr)
    if run.returncode:raise RuntimeError('Compiler rejected candidate; see its ignored compile.stderr.log')
    need(source_hashes(src)==env['source_sha256'],'Source changed during compilation')
    subprocess.run([str(toolpath(avr_bin,'avr-objcopy')),'-O','ihex','-R','.eeprom',str(elf),str(hexfile)],check=True,capture_output=True)
    subprocess.run([str(toolpath(avr_bin,'avr-objcopy')),'-O','binary','-R','.eeprom',str(elf),str(binary)],check=True,capture_output=True)
    sizes=subprocess.check_output([str(toolpath(avr_bin,'avr-size')),str(elf)],text=True)
    match=re.search(r'^\s*(\d+)\s+(\d+)\s+(\d+)\s+',sizes,re.M)
    need(match is not None,'Cannot parse avr-size');text,data,bss=map(int,match.groups())
    metadata=embedded_audio_and_metadata(elf,binary,avr_bin,blob,env)
    image={'input_bytes':len(blob),'input_sha256':item['stream_sha256'],'input_samples':item['samples'],
        'flash_bytes':text+data,'flash_excluding_stream_bytes':text+data-len(blob),
        'text_bytes':text,'data_bytes':data,'bss_bytes':bss,'static_sram_bytes':data+bss,
        'elf_sha256':digest(elf),'hex_sha256':digest(hexfile),'program_sha256':digest(binary),
        'compiler_options':flags,'assembly_enabled':bool(assembly),'extra_irq_cycles':irq,**metadata}
    save(cache,{'fingerprint':identity,'metadata_sha256':sha(canonical(image)),'environment':env,'image':image})
    return image


def screen(source,study,output,avr_bin,candidates=None,case='case-03',profile=4,compact_only=False):
    need(len(CANDIDATES)<=24,'Screen exceeds bounded candidate count')
    env=environment(source,avr_bin,compact_only);items=fixed_inputs(study,(case,),(profile,),model=False);item=items[0]
    output=Path(output);names=list(CANDIDATES) if candidates is None else list(dict.fromkeys(['baseline',*candidates]))
    report={'environment':env,'workload':{'id':item['id'],'stream_sha256':item['stream_sha256'],
        'samples':item['samples'],'input_bytes':len(item['blob'])},'candidates':{},
        'scope':'Compile/size screen only; no timing or real-time admission inferred.',
        'audio_exclusion':'Exact embedded array bytes/size proven from ELF+binary before subtraction.',
        'physical_hardware_measured':False}
    reference=None
    for name in names:
        try:
            image=compile_image(source,env,CANDIDATES[name],item,output/'screen'/item['id']/name,avr_bin)
            if reference is None:reference=image
            same_harness(image,reference)
            row={'status':'compiled','specification':CANDIDATES[name],**image}
            row['program_flash_saving_bytes']=reference['flash_excluding_stream_bytes']-image['flash_excluding_stream_bytes']
            row['program_flash_saving_percent']=100*row['program_flash_saving_bytes']/reference['flash_excluding_stream_bytes']
            print(name,image['flash_excluding_stream_bytes'],'program Flash bytes',flush=True)
        except (RuntimeError,ValueError,subprocess.CalledProcessError) as error:
            if name=='baseline':raise
            row={'status':'rejected','specification':CANDIDATES[name],'reason_type':type(error).__name__}
            print(name,'rejected; no valid size comparison',flush=True)
        report['candidates'][name]=row;save(output/'screen.json',report)
    return report


def runtime_fingerprint(runner,lib,wsl):
    result={'sim_runner_sha256':digest(runner),'wsl':wsl}
    if wsl:
        code='import pathlib,hashlib,json,sys; p=pathlib.Path(sys.argv[1]); print(json.dumps({q.name:{"sha256":hashlib.sha256(q.read_bytes()).hexdigest(),"target":q.resolve().name} for q in sorted(p.glob("*.so*")) if q.is_file()},sort_keys=True))'
        result['libraries']=json.loads(subprocess.check_output(['wsl','-d',wsl,'--','python3','-c',code,linux_path(lib)],text=True))
    else:result['libraries']={p.name:digest(p) for p in sorted(Path(lib).glob('*.so*')) if p.is_file()}
    return result


def simulate(source,env,spec,item,folder,avr_bin,runner,lib,wsl,runtime,assembly=True,irq=0):
    folder=Path(folder);image=compile_image(source,env,spec,item,folder,avr_bin,assembly,irq)
    identity=sha(canonical([env,spec,runtime,image['elf_sha256'],sha(item['pwm']),assembly,irq]));cache=folder/'verification.json'
    measured=None
    if cache.exists():
        old=load(cache);row=old.get('measurement',{})
        if old.get('fingerprint')==identity and old.get('measurement_sha256')==sha(canonical(row)):
            if (folder/'valid.pcm8').exists() and digest(folder/'valid.pcm8')==sha(item['pwm']):measured=row
    if measured is None:
        valid,timing=folder/'valid.pcm8',folder/'timing.json'
        if wsl:
            cmd=['wsl','-d',wsl,'--','env','LD_LIBRARY_PATH='+linux_path(lib),linux_path(runner),
                 linux_path(folder/'profile.elf'),linux_path(valid),linux_path(timing)]
            subprocess.run(cmd,check=True,capture_output=True)
        else:
            environment_vars=os.environ.copy();environment_vars['LD_LIBRARY_PATH']=str(Path(lib).resolve())
            subprocess.run([str(Path(runner).resolve()),str(folder/'profile.elf'),str(valid),str(timing)],
                           check=True,capture_output=True,env=environment_vars)
        measured=load(timing)
        need(valid.read_bytes()==item['pwm'],'Complete saved-WAV/AVR PWM mismatch')
        measured.update(image);measured['pwm_sha256']=sha(item['pwm']);measured['pwm_saved_reference_exact']=True
        measured['mean_decode_wall_cycles']=measured['decode_wall_cycles_total']/measured['decode_calls']
        measured['first_output_from_reset_ms']=measured['occupancy_trace'][0]['cycle']/16000
        measured['stack_high_water_bytes_after_ready']=2304-measured['minimum_stack_pointer']
        measured={k:v for k,v in measured.items() if k!='occupancy_trace'}
        save(cache,{'fingerprint':identity,'environment':env,'runtime':runtime,
                    'measurement_sha256':sha(canonical(measured)),'measurement':measured})
        print(folder.name,round(measured['mean_decode_wall_cycles'],3),measured['underruns'],'underruns',flush=True)
    need(measured['done'] and not measured['decoder_error'] and measured['stack_margin_bytes']>0,'AVR completion/error/stack failed')
    need(measured['played']==measured['produced']==measured['decode_calls']==item['samples'],'Incomplete useful AVR output')
    need(measured['timer_ticks']==item['samples']+measured['underruns'],'AVR timer accounting failed')
    need(measured['cpu_hz']==BASE['cpu_hz'] and measured['audio_hz']==BASE['audio_hz'],'Simulator clock profile differs')
    need(measured['flash_bytes']<=32768 and measured['pwm_saved_reference_exact'],'AVR Flash/PWM check failed')
    need(source_hashes(srcdir(source))==env['source_sha256'],'Source changed during verification')
    return measured


def repeated(item):
    n,p,spectra,params,pulses,pre,bright,extras=unpack(item['blob']);need(n==32000,'Expected a four-second stress source')
    blob=pack(64000,p,spectra*2,params*2,pulses*2,pre,bright,extras*2)[0]
    # The repeat uses continuous decoder state; it is not a concatenation of
    # two decoded WAVs. This independent integer model defines its reference.
    pcm=decode_model(blob)
    return {'id':'repeat-'+str(p),'case':item['case'],'profile':p,'blob':blob,'pwm':pwm_duties(pcm).tobytes(),
            'samples':64000,'stream_sha256':sha(blob),'pcm_sha256':sha(pcm.astype('<i2').tobytes())}


def verify(source,study,output,avr_bin,runner,lib,wsl,candidate='baseline',compact_only=False):
    env=environment(source,avr_bin,compact_only);runtime=runtime_fingerprint(runner,lib,wsl);items=fixed_inputs(study)
    output=Path(output);spec=CANDIDATES[candidate]
    reference=compile_image(source,env,CANDIDATES['baseline'],items[0],output/'reference'/items[0]['id'],avr_bin)
    report={'environment':env,'runtime':runtime,'candidate':candidate,'specification':spec,'images':{},'stress':{},
        'reference':'Complete useful PWM from fixed saved PCM16 WAVs; no active BatchSession.',
        'physical_hardware_measured':False,'wall_scope':'Includes active IRQ and instrumentation.',
        'stack_scope':'Observed after profile_ready, not a startup/worst-case proof.'}
    for item in items:
        row=simulate(source,env,spec,item,output/'verify'/candidate/item['id'],avr_bin,runner,lib,wsl,runtime)
        same_harness(row,reference)
        need(row['underruns']==0,'Main ASM workload underruns')
        report['images'][item['id']]=row;save(output/f'verification-{candidate}.json',report)
    for p in PROFILES:
        choices=[x for x in items if x['profile']==p]
        heaviest=max(choices,key=lambda x:report['images'][x['id']]['mean_decode_wall_cycles'])
        item=repeated(heaviest);row={'source_id':heaviest['id'],'source_stream_sha256':heaviest['stream_sha256'],
                                   'repeat_stream_sha256':item['stream_sha256'],'images':{}}
        for name,assembly,irq in (('normal',True,0),('extra_irq100',True,100),('c_fallback',False,0)):
            measured=simulate(source,env,spec,item,output/'verify'/candidate/'stress'/f'{p}-{name}',
                avr_bin,runner,lib,wsl,runtime,assembly,irq)
            same_harness(measured,reference)
            if assembly:need(measured['underruns']==0,'ASM continuous-state control underruns')
            row['images'][name]=measured
        report['stress'][str(p)]=row;save(output/f'verification-{candidate}.json',report)
    return report


def main():
    ap=argparse.ArgumentParser(description=__doc__);sub=ap.add_subparsers(dest='mode',required=True)
    for mode in ('screen','verify'):
        p=sub.add_parser(mode);p.add_argument('--source',type=Path,required=True)
        p.add_argument('--study',type=Path,default=Path('build/lpx-speech-compact/study'))
        p.add_argument('--output',type=Path,required=True);p.add_argument('--avr-bin',type=Path,required=True)
        p.add_argument('--compact-only',action='store_true')
        if mode=='screen':
            p.add_argument('--candidates',choices=tuple(CANDIDATES),nargs='+')
            p.add_argument('--case',choices=CASES,default='case-03');p.add_argument('--profile',choices=PROFILES,type=int,default=4)
        else:
            p.add_argument('--candidate',choices=tuple(CANDIDATES),default='baseline')
            p.add_argument('--runner',type=Path,required=True);p.add_argument('--lib',type=Path,required=True)
            p.add_argument('--wsl',default=None)
    args=vars(ap.parse_args());mode=args.pop('mode');globals()[mode](**args)


if __name__=='__main__':main()

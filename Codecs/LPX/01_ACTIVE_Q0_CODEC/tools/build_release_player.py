"""Build bare AVR v5 playback separately from diagnostic profiling firmware.

Generated media, images and observer sidecars stay in ignored build/. The
observer uses real playback state plus vendor-derived metadata outside the ELF.
"""
from __future__ import annotations
import argparse,hashlib,json,re,subprocess
from pathlib import Path
from benchmark_speech_flash import (CANDIDATES,canonical,command_flags,digest,
    environment,source_hashes,srcdir,toolpath,validation_provenance,build_provenance,artifact_provenance)
from measure_speech_firmware import voice_header
from output_paths import protect_outputs
from profile_avr import linux_path
from speech_compact import decode_model
from standard_metrics import pwm_duties
ROOT=Path(__file__).resolve().parents[1]
REPOSITORY=ROOT.parents[2]
EXAMPLE=ROOT/'examples/AVR_V5_PLAYER'
VALIDATION=ROOT.parent/'validation/atmega328p'
ARTIFACTS=('voice_data.h','player.elf','program.bin','player.hex','player.map','cost.json',
           'compile.stdout.log','compile.stderr.log','hardware.o','hardware.bin',
           'hardware-cache.json','observer.txt','valid.pcm8','observer.json','verification.json',
           'observer.stdout.log','observer.stderr.log')
def sha(data):return hashlib.sha256(data).hexdigest()
def save(path,value):
    tmp=path.with_suffix('.writing');tmp.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n');tmp.replace(path)
def guard(folder,inputs=()):
    folder=Path(folder).resolve()
    if not folder.is_relative_to((REPOSITORY/'build').resolve()) or folder==(REPOSITORY/'build').resolve():
        raise ValueError('Production artifacts must stay inside repository ignored build storage')
    targets=[folder/name for name in ARTIFACTS]
    targets += [(folder/name).with_suffix('.writing') for name in ('cost.json','hardware-cache.json','observer.json','verification.json')]
    for target in targets:
        if not target.resolve().is_relative_to((REPOSITORY/'build').resolve()) or target.is_symlink() or (target.exists() and target.stat().st_nlink>1):
            raise ValueError('Output aliases are not allowed')
    protect_outputs([Path(__file__),*EXAMPLE.glob('*'),VALIDATION/'player_hardware.cpp',VALIDATION/'sim_player.c',*inputs],targets)
    folder.mkdir(parents=True,exist_ok=True);return folder

def symbols(elf,avr_bin):
    output=subprocess.check_output([str(toolpath(avr_bin,'avr-nm')),'-S','--defined-only',str(elf)],text=True)
    result={}
    for line in output.splitlines():
        parts=line.split()
        if len(parts)>=3:
            result[parts[-1]]={'address':int(parts[0],16)&0xffff,'size':int(parts[1],16) if len(parts)>=4 else None}
    return result

def checked_image(folder,avr_bin,streams,queue):
    syms=symbols(folder/'player.elf',avr_bin);data=(folder/'program.bin').read_bytes();ranges=[]
    if any(name.startswith('profile_') for name in syms) or 'lpx_player_hardware' in syms:
        raise ValueError('Production image contains observer/profiler-only symbols')
    for i,blob in enumerate(streams):
        matches=[s for name,s in syms.items() if re.search('lpx_voice_'+str(i)+r'(?:\.|$)',name) and s['size']==len(blob) and data[s['address']:s['address']+len(blob)]==blob]
        if len(matches)!=1:raise ValueError('Cannot prove exact unique embedded audio segment')
        at=matches[0]['address'];end=at+len(blob)
        if end>len(data) or any(at<b and a<end for a,b in ranges):raise ValueError('Embedded audio regions overlap')
        ranges.append((at,end))
    needed={'lpx_player_queue':queue,'lpx_player_head':2 if queue>256 else 1,
            'lpx_player_tail':2 if queue>256 else 1,'lpx_player_eof':1,
            'lpx_player_error':1,'lpx_player_stopped':1}
    for name,size in needed.items():
        matches=[v for n,v in syms.items() if re.fullmatch(name+r'(?:\..*)?',n) and v['size']==size]
        if len(matches)!=1:raise ValueError('Missing or ambiguous actual playback state: '+name)
        syms[name]=matches[0]
    return syms,ranges

def build(streams,output,avr_bin,*,source=None,queue=256,prefill=None,irq=0,assembly=False):
    if not isinstance(streams,(list,tuple)) or not 1<=len(streams)<=255 or any(not isinstance(b,(bytes,bytearray,memoryview)) or not 1<=len(b)<=65535 for b in streams):
        raise ValueError('Expected 1..255 nonempty bounded byte streams')
    if isinstance(queue,bool) or not isinstance(queue,int) or queue not in (128,256,512):raise ValueError('Unsupported queue')
    prefill=queue*3//4 if prefill is None else prefill
    if isinstance(prefill,bool) or not isinstance(prefill,int) or not 1<=prefill<queue:raise ValueError('Invalid prefill')
    if isinstance(irq,bool) or not isinstance(irq,int) or not 0<=irq<=600 or not isinstance(assembly,bool):raise ValueError('Invalid backend or IRQ load')
    streams=[bytes(b) for b in streams];source=ROOT if source is None else Path(source);src=srcdir(source);avr_bin=Path(avr_bin)
    folder=guard(output,[*src.rglob('*')]);env=environment(source,avr_bin,True,harness=EXAMPLE/'player.cpp',required_symbols=(),retained_symbols=())
    env['settings']={**env['settings'],'queue':queue,'prefill':prefill}
    flags=command_flags(env,CANDIDATES['unroll1-tune0-lto-call-relax'],assembly,irq)
    flags=[f for f in flags if not f.startswith(('-DLPX4_PROFILE_QUEUE=','-DLPX4_PROFILE_PREFILL=','-DLPX4_PROFILE_IRQ_LOAD='))]
    flags += [f'-DLPX_PLAYER_QUEUE={queue}',f'-DLPX_PLAYER_PREFILL={prefill}',f'-DLPX_PLAYER_IRQ_LOAD={irq}',
              '-DLPX_PLAYER_DATA_HEADER="voice_data.h"']
    header=voice_header(streams).replace('profile_','lpx_')+f'#define LPX_PLAYER_SEGMENTS {len(streams)}\n'
    sample_counts=[int.from_bytes(b[8:12],'little') if len(b)>=12 else None for b in streams]
    layout=voice_header([b'' for _ in streams]).replace('profile_','lpx_')+f'#define LPX_PLAYER_SEGMENTS {len(streams)}\n'
    recipe={'environment':build_provenance(env),'compiler_options':flags,
            'player_config_sha256':digest(EXAMPLE/'player_config.h'),'voice_layout_sha256':sha(layout.encode()),
            'declared_segment_samples':sample_counts}
    build_fingerprint=sha(canonical(recipe));hashes=[sha(b) for b in streams]
    fingerprint=sha(canonical([build_fingerprint,hashes,sha(header.encode())]));cache=folder/'cost.json'
    proof_fingerprint=sha(canonical([artifact_provenance(avr_bin),digest(Path(__file__))]))
    cached_image=False
    (folder/'voice_data.h').write_text(header,encoding='utf-8',newline='\n')
    if cache.is_file():
        old=json.loads(cache.read_text());cost=old.get('cost',{})
        if old.get('fingerprint')==fingerprint and old.get('cost_sha256')==sha(canonical(cost)) and (folder/'player.elf').is_file() and (folder/'program.bin').is_file() and digest(folder/'player.elf')==cost.get('image_sha256') and digest(folder/'program.bin')==cost.get('binary_sha256'):
            if source_hashes(src)!=env['source_sha256']:raise ValueError('Sources changed')
            cached_image=True
            if old.get('proof_fingerprint')==proof_fingerprint and cost.get('source_fingerprint')==sha(canonical(env['source_sha256'])) and (folder/'player.hex').is_file() and digest(folder/'player.hex')==cost.get('hex_sha256'):
                checked_image(folder,avr_bin,streams,queue);return cost
    if not cached_image:
        command=[str(toolpath(avr_bin,'avr-g++')),*flags,'-I'+str(src),'-I'+str(EXAMPLE),'-I'+str(folder),str(EXAMPLE/'player.cpp'),str(src/'Lpx4HybridCore.cpp'),'-Wl,-Map='+str(folder/'player.map'),'-o',str(folder/'player.elf')]
        result=subprocess.run(command,capture_output=True)
        (folder/'compile.stdout.log').write_bytes(result.stdout);(folder/'compile.stderr.log').write_bytes(result.stderr)
        if result.returncode:raise RuntimeError('Production link failed; see ignored compile.stderr.log')
        if source_hashes(src)!=env['source_sha256']:raise ValueError('Sources changed during linking')
    subprocess.run([str(toolpath(avr_bin,'avr-objcopy')),'-O','binary','-R','.eeprom',str(folder/'player.elf'),str(folder/'program.bin')],check=True,capture_output=True)
    subprocess.run([str(toolpath(avr_bin,'avr-objcopy')),'-O','ihex','-R','.eeprom',str(folder/'player.elf'),str(folder/'player.hex')],check=True,capture_output=True)
    text=subprocess.check_output([str(toolpath(avr_bin,'avr-size')),str(folder/'player.elf')],text=True)
    match=re.search(r'^\s*(\d+)\s+(\d+)\s+(\d+)\s+',text,re.M)
    if not match:raise ValueError('Cannot parse linked image size')
    code,data,bss=map(int,match.groups());_,ranges=checked_image(folder,avr_bin,streams,queue)
    cost=dict(schema='lpx-v5-firmware-cost-v1',image_kind='elf',image_role='production-player',measurement='linked-elf-text-plus-data',complete_image=True,embedded_streams_exact=True,
              stream_sha256=hashes,stream_bytes=sum(map(len,streams)),segments=len(streams),
              samples=sum(n for n in sample_counts if n is not None),declared_segment_samples=sample_counts,
              flash_bytes=code+data,program_flash_bytes=code+data-sum(map(len,streams)),text_bytes=code,data_bytes=data,bss_bytes=bss,static_sram_bytes=data+bss,
              image_sha256=digest(folder/'player.elf'),binary_sha256=digest(folder/'program.bin'),hex_sha256=digest(folder/'player.hex'),source_fingerprint=sha(canonical(env['source_sha256'])),
              build_fingerprint=build_fingerprint,environment=env,compiler_options=flags,queue=queue,prefill=prefill,index_bytes=2 if queue>256 else 1,extra_irq_cycles=irq,
              embedded_segment_ranges=ranges,assembly_enabled=assembly,timing_verified=False,physical_board_measured=False)
    save(cache,dict(fingerprint=fingerprint,cost_sha256=sha(canonical(cost)),cost=cost,proof_fingerprint=proof_fingerprint));return cost

def observer_metadata(folder,cost,avr_bin):
    avr_bin=Path(avr_bin);syms=symbols(folder/'player.elf',avr_bin)
    # Metadata is a separate object and not an input to the production link.
    flags=[f for f in cost['compiler_options'] if f!='-flto' and not f.startswith('-Wl,')]
    fingerprint=sha(canonical([digest(VALIDATION/'player_hardware.cpp'),digest(EXAMPLE/'player_config.h'),flags,cost['environment']['dependencies']]))
    cache=folder/'hardware-cache.json';valid=False
    if cache.is_file() and (folder/'hardware.bin').is_file():
        old=json.loads(cache.read_text());valid=old.get('fingerprint')==fingerprint and old.get('binary_sha256')==digest(folder/'hardware.bin')
    if not valid:
        subprocess.run([str(toolpath(avr_bin,'avr-g++')),*flags,'-I'+str(EXAMPLE),'-c',str(VALIDATION/'player_hardware.cpp'),'-o',str(folder/'hardware.o')],check=True,capture_output=True)
        subprocess.run([str(toolpath(avr_bin,'avr-objcopy')),'-O','binary','-j','.progmem.data',str(folder/'hardware.o'),str(folder/'hardware.bin')],check=True,capture_output=True)
        save(cache,dict(fingerprint=fingerprint,binary_sha256=digest(folder/'hardware.bin')))
    data=(folder/'hardware.bin').read_bytes()
    if len(data)!=40:raise ValueError('Unexpected vendor metadata size')
    values=[int.from_bytes(data[i:i+2],'little') for i in range(0,40,2)]
    def address(name):
        matches=[v['address'] for n,v in syms.items() if re.fullmatch(name+r'(?:\..*)?',n)]
        if len(matches)!=1:raise ValueError('Ambiguous observer symbol: '+name)
        return matches[0]
    values += [address(n) for n in ('lpx_player_head','lpx_player_tail','lpx_player_eof','lpx_player_error','lpx_player_stopped','lpx_player_queue','__bss_end')]
    (folder/'observer.txt').write_text(' '.join(map(str,values))+'\n',encoding='utf-8')
    return values

def validate(report,actual,expected,*,expected_error=0):
    fields=('stopped','eof','decoder_error','observer_errors','underruns','played','produced',
            'timer_ticks','timer_events','queued_at_stop','timer_started','stack_margin_all_bytes')
    if (not isinstance(report,dict) or any(isinstance(report.get(k),bool) or not isinstance(report.get(k),int) for k in fields)
            or not isinstance(actual,(bytes,bytearray,memoryview)) or not isinstance(expected,(bytes,bytearray,memoryview))
            or isinstance(expected_error,bool) or not isinstance(expected_error,int) or not 0<=expected_error<=4):return False
    good=(isinstance(report,dict) and report.get('stopped')==1 and report.get('eof')==1 and report.get('decoder_error')==expected_error and
          report.get('observer_errors')==0 and report.get('observer_exit_code',0)==0 and report.get('underruns')==0 and actual==expected and report.get('played')==len(expected) and
          report.get('timer_ticks')==len(expected) and report.get('timer_events')==len(expected) and report.get('stack_margin_all_bytes',0)>0)
    if expected_error==0:good=good and report.get('produced')==len(expected) and report.get('queued_at_stop')==0 and report.get('timer_started')==1
    return bool(good)

def simulate(streams,output,avr_bin,runner,*,source=None,queue=256,prefill=None,irq=0,assembly=False,lib=None,wsl=None,expected_pwm=None,expected_error=0,require_valid=True):
    folder=guard(output,[runner]);cost=build(streams,folder,avr_bin,source=source,queue=queue,prefill=prefill,irq=irq,assembly=assembly)
    observer_metadata(folder,cost,avr_bin)
    expected=b''.join(pwm_duties(decode_model(b)).tobytes() for b in streams) if expected_pwm is None else bytes(expected_pwm)
    provenance=validation_provenance(runner,lib,wsl,sources=(Path(__file__),VALIDATION/'sim_player.c',VALIDATION/'player_hardware.cpp',EXAMPLE/'player_config.h'))
    provenance['runner_sources']={'sim_player.c':digest(VALIDATION/'sim_player.c')}
    fingerprint=sha(canonical([provenance,cost['image_sha256'],digest(folder/'observer.txt'),sha(expected),expected_error]))
    cache=folder/'verification.json';report=None
    if cache.is_file() and (folder/'observer.json').is_file() and (folder/'valid.pcm8').is_file():
        old=json.loads(cache.read_text())
        if old.get('fingerprint')==fingerprint and old.get('report_sha256')==digest(folder/'observer.json') and old.get('pwm_sha256')==digest(folder/'valid.pcm8'):
            report=json.loads((folder/'observer.json').read_text())
    if report is None:
        if wsl:
            command=['wsl','-d',wsl,'--','env']
            if lib:command+=['LD_LIBRARY_PATH='+linux_path(lib)]
            command += [linux_path(runner),linux_path(folder/'player.elf'),linux_path(folder/'valid.pcm8'),linux_path(folder/'observer.json'),linux_path(folder/'observer.txt')]
        else:
            import os
            runtime_env=os.environ.copy()
            if lib:runtime_env['LD_LIBRARY_PATH']=str(Path(lib).resolve())
            command=[str(runner),str(folder/'player.elf'),str(folder/'valid.pcm8'),str(folder/'observer.json'),str(folder/'observer.txt')]
        # A failed runner must not reuse evidence from an earlier validation.
        for name in ('observer.json','valid.pcm8'):
            (folder/name).unlink(missing_ok=True)
        result=subprocess.run(command,capture_output=True,**({} if wsl else {'env':runtime_env}))
        (folder/'observer.stdout.log').write_bytes(result.stdout)
        (folder/'observer.stderr.log').write_bytes(result.stderr)
        if not (folder/'observer.json').is_file() or not (folder/'valid.pcm8').is_file():
            raise RuntimeError('Observer failed before writing evidence; see ignored observer.stderr.log')
        report=json.loads((folder/'observer.json').read_text());report['observer_exit_code']=result.returncode
        save(folder/'observer.json',report)
    actual=(folder/'valid.pcm8').read_bytes();passed=validate(report,actual,expected,expected_error=expected_error)
    verified=dict(fingerprint=fingerprint,report_sha256=digest(folder/'observer.json'),pwm_sha256=sha(actual),cost=cost,report=report,passed=passed,validation_provenance=provenance)
    save(cache,verified)
    if require_valid and not passed:raise AssertionError('Production player validation failed; inspect ignored observer report')
    return verified

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);p.add_argument('streams',nargs='+',type=Path);p.add_argument('--avr-bin',required=True,type=Path)
    p.add_argument('--source',type=Path);p.add_argument('--queue',type=int,default=256);p.add_argument('--prefill',type=int);p.add_argument('--irq',type=int,default=0);p.add_argument('--enable-asm',action='store_true')
    p.add_argument('--observer',type=Path);p.add_argument('--lib',type=Path);p.add_argument('--wsl');a=p.parse_args();guard(a.output,a.streams);streams=[f.read_bytes() for f in a.streams]
    if a.observer:r=simulate(streams,a.output,a.avr_bin,a.observer,source=a.source,queue=a.queue,prefill=a.prefill,irq=a.irq,assembly=a.enable_asm,lib=a.lib,wsl=a.wsl);cost=r['cost']
    else:cost=build(streams,a.output,a.avr_bin,source=a.source,queue=a.queue,prefill=a.prefill,irq=a.irq,assembly=a.enable_asm)
    print(json.dumps({k:cost[k] for k in ('flash_bytes','program_flash_bytes','static_sram_bytes','segments','queue','prefill')}))
if __name__=='__main__':main()

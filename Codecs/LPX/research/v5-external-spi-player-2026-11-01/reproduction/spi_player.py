"""Exact linked SPI images and interrupt-active physical-output verification."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

THIS=Path(__file__).resolve()
ROOT=THIS.parents[5]
ACTIVE=ROOT/'Codecs/LPX/01_ACTIVE_Q0_CODEC'
TOOLS=ACTIVE/'tools'
EXAMPLE=ACTIVE/'examples/AVR_V5_SPI_PLAYER'
SHARED=ROOT/'Codecs/shared/avr-spi-flash'
HOST=ROOT/'Codecs/LPX/validation/atmega328p/spi'
PACKAGE=THIS.parents[1]
sys.path.insert(0,str(TOOLS))
import benchmark_speech_flash as bench
import build_release_player as rom
from profile_avr import linux_path

sha=lambda raw:hashlib.sha256(raw).hexdigest()
load=lambda path:json.loads(Path(path).read_bytes())


def save(path,value):
    path=Path(path).resolve()
    if not path.is_relative_to(ROOT/'build') or path.is_symlink() or path.exists() and path.stat().st_nlink>1:
        raise ValueError('SPI output must be a distinct ignored build file')
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.writing')
    if temporary.exists() or temporary.is_symlink():raise ValueError('Preserve an existing incomplete write')
    temporary.write_bytes(json.dumps(value,indent=2,allow_nan=False).encode()+b'\n')
    for attempt in range(6):
        try:
            temporary.replace(path)
            return
        except PermissionError as exc:
            if getattr(exc,'winerror',None) not in (5,32) or attempt==5:raise
            time.sleep(.01*(attempt+1))


def require(value,message):
    if not value:raise ValueError(message)


def source_inventory():
    files=[p for p in (ACTIVE/'src').rglob('*') if p.is_file()]
    files += list(TOOLS.glob('*.py'))+list(rom.EXAMPLE.glob('*'))
    files += [rom.VALIDATION/'sim_player.c',rom.VALIDATION/'player_hardware.cpp']
    files += list(EXAMPLE.glob('*.cpp'))+list(SHARED.glob('*.h'))
    files += [p for p in HOST.iterdir() if p.suffix in ('.c','.h','.py')]
    files += [ROOT/'tools/spi-flash-model'/name for name in ('w25q128_readonly.c','w25q128_readonly.h')]
    files += [THIS,PACKAGE/'PROTOCOL.md']
    files += [ROOT/'Codecs/LPX/research/v5-adaptive-target-player-2026-10-30/reproduction'/name
              for name in ('admit.py','player_evidence.py')]
    for name in ('run_player.py','prepare_cases.py','native_inputs.py','test_cases.py','test_player_plan.py'):
        path=THIS.parent/name
        if path.is_file():files.append(path)
    return {p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in sorted(set(files)) if p.is_file()}


def row_settings(row):
    require(type(row['assembly']) is bool and row['extra_irq_cycles'] in (0,100),'Unsupported fixed player settings')
    require(row['storage'] in ('spi','rom'),'Unsupported storage backend')


def header(chain):
    offsets=chain['offsets'];sizes=chain['sizes']
    require(1<=len(offsets)==len(sizes)<=255 and all(type(n) is int and 1<=n<=65535 for n in sizes),
            'Unsupported reset metadata')
    require(all(type(at) is int and 0<=at<16777216 and n<=16777216-at for at,n in zip(offsets,sizes)),
            'External image offset/span is out of bounds')
    return ('#include <avr/pgmspace.h>\n'
        '#define LPX_PLAYER_SEGMENTS %d\n'%len(offsets)+
        'extern "C" const uint32_t lpx_spi_offsets[] PROGMEM={'+','.join(str(n)+'UL' for n in offsets)+'};\n'+
        'extern "C" const uint16_t lpx_spi_sizes[] PROGMEM={'+','.join(map(str,sizes))+'};\n')


def one_symbol(symbols,name):
    matches=[value for key,value in symbols.items() if re.fullmatch(name+r'(?:\..*)?',key)]
    require(len(matches)==1,'Missing or ambiguous player symbol: '+name)
    return matches[0]


def checked_image(folder,avr_bin,chain):
    symbols=rom.symbols(folder/'player.elf',avr_bin)
    raw=(folder/'program.bin').read_bytes()
    require(not any(name.startswith('profile_') or re.search(r'lpx_voice_\d',name) for name in symbols)
            and 'lpx_player_hardware' not in symbols,'Diagnostic or embedded-audio symbols in SPI image')
    for name,size in (('lpx_player_queue',256),('lpx_player_head',1),('lpx_player_tail',1),
                      ('lpx_player_eof',1),('lpx_player_error',1),('lpx_player_stopped',1)):
        require(one_symbol(symbols,name)['size']==size,'Playback state size changed')
    ranges=[]
    for name,values,width in (('lpx_spi_offsets',chain['offsets'],4),('lpx_spi_sizes',chain['sizes'],2)):
        symbol=one_symbol(symbols,name)
        data=b''.join(n.to_bytes(width,'little') for n in values)
        begin=symbol['address'];end=begin+len(data)
        require(symbol['size']==len(data) and end<=len(raw) and raw[begin:end]==data,'External metadata bytes differ')
        require(not any(begin<b and a<end for a,b in ranges),'External metadata regions overlap')
        ranges.append((begin,end))
    return symbols,ranges


def build(chain,row,folder,avr_bin):
    row_settings(row);folder=Path(folder).resolve();avr_bin=Path(avr_bin).resolve()
    require(row['storage']=='spi' and not folder.exists() and folder.is_relative_to(ROOT/'build'),
            'Inspect a previous image attempt; use the fixed fresh SPI image path')
    before=source_inventory();folder.mkdir(parents=True)
    text=header(chain);(folder/'spi_data.h').write_bytes(text.encode())
    env=bench.environment(ACTIVE,avr_bin,True,harness=EXAMPLE/'player.cpp',required_symbols=(),retained_symbols=())
    env['settings']={**env['settings'],'queue':256,'prefill':192}
    flags=bench.command_flags(env,bench.CANDIDATES['unroll1-tune0-lto-call-relax'],row['assembly'],row['extra_irq_cycles'])
    flags=[f for f in flags if not f.startswith(('-DLPX4_PROFILE_QUEUE=','-DLPX4_PROFILE_PREFILL=','-DLPX4_PROFILE_IRQ_LOAD='))]
    flags += ['-DLPX4_ENABLE_INPUT_CALLBACK=1','-DLPX_PLAYER_QUEUE=256','-DLPX_PLAYER_PREFILL=192',
              '-DLPX_PLAYER_IRQ_LOAD='+str(row['extra_irq_cycles']),'-DLPX_PLAYER_DATA_HEADER="spi_data.h"']
    recipe=dict(environment=bench.build_provenance(env),compiler_options=flags,source_inventory=before,
        metadata_header_sha256=sha(text.encode()),external_image_sha256=chain['external_image_sha256'])
    command=[str(bench.toolpath(avr_bin,'avr-g++')),*flags,'-I'+str(ACTIVE/'src'),'-I'+str(EXAMPLE),
        '-I'+str(rom.EXAMPLE),'-I'+str(folder),str(EXAMPLE/'player.cpp'),str(ACTIVE/'src/Lpx4HybridCore.cpp'),
        '-Wl,-Map='+str(folder/'player.map'),'-o',str(folder/'player.elf')]
    result=subprocess.run(command,capture_output=True)
    (folder/'compile.stdout.log').write_bytes(result.stdout);(folder/'compile.stderr.log').write_bytes(result.stderr)
    if result.returncode:raise RuntimeError('Exact SPI firmware link failed; preserve compile logs')
    require(before==source_inventory(),'Source changed during exact SPI link')
    for form,name in (('binary','program.bin'),('ihex','player.hex')):
        subprocess.run([str(bench.toolpath(avr_bin,'avr-objcopy')),'-O',form,'-R','.eeprom',str(folder/'player.elf'),str(folder/name)],
                       check=True,capture_output=True)
    size=subprocess.check_output([str(bench.toolpath(avr_bin,'avr-size')),str(folder/'player.elf')],text=True)
    match=re.search(r'^\s*(\d+)\s+(\d+)\s+(\d+)\s+',size,re.M);require(match,'Cannot parse SPI image size')
    code,data,bss=map(int,match.groups());_,ranges=checked_image(folder,avr_bin,chain)
    cost=dict(schema='lpx-external-spi-firmware-cost-v1',complete_image=True,external_streams_exact=True,
        embedded_stream_bytes=0,external_stream_bytes=chain['stream_bytes'],external_capacity_bytes=16777216,
        external_metadata_bytes=6*len(chain['sizes']),segments=len(chain['sizes']),samples=chain['samples'],
        flash_bytes=code+data,program_flash_bytes=code+data,text_bytes=code,data_bytes=data,bss_bytes=bss,static_sram_bytes=data+bss,
        image_sha256=sha((folder/'player.elf').read_bytes()),binary_sha256=sha((folder/'program.bin').read_bytes()),
        hex_sha256=sha((folder/'player.hex').read_bytes()),build_fingerprint=sha(bench.canonical(recipe)),recipe=recipe,
        environment=env,compiler_options=flags,metadata_ranges=ranges,assembly_enabled=row['assembly'],
        extra_irq_cycles=row['extra_irq_cycles'],queue=256,prefill=192,index_bytes=1,physical_board_measured=False)
    save(folder/'cost-private.json',cost)
    return cost


def reopen_spi(chain,row,folder,avr_bin,runner):
    verified=load(folder/'verification-private.json');cost=load(folder/'cost-private.json')
    require(verified['cost']==cost and verified['passed'],'SPI proof is not a positive exact image')
    checked_image(folder,avr_bin,chain)
    require((folder/'spi_data.h').read_bytes()==header(chain).encode(),'Generated external metadata changed')
    env=bench.environment(ACTIVE,avr_bin,True,harness=EXAMPLE/'player.cpp',required_symbols=(),retained_symbols=())
    env['settings']={**env['settings'],'queue':256,'prefill':192}
    flags=bench.command_flags(env,bench.CANDIDATES['unroll1-tune0-lto-call-relax'],row['assembly'],row['extra_irq_cycles'])
    flags=[f for f in flags if not f.startswith(('-DLPX4_PROFILE_QUEUE=','-DLPX4_PROFILE_PREFILL=','-DLPX4_PROFILE_IRQ_LOAD='))]
    flags += ['-DLPX4_ENABLE_INPUT_CALLBACK=1','-DLPX_PLAYER_QUEUE=256','-DLPX_PLAYER_PREFILL=192',
              '-DLPX_PLAYER_IRQ_LOAD='+str(row['extra_irq_cycles']),'-DLPX_PLAYER_DATA_HEADER="spi_data.h"']
    recipe=dict(environment=bench.build_provenance(env),compiler_options=flags,source_inventory=source_inventory(),
        metadata_header_sha256=sha(header(chain).encode()),external_image_sha256=chain['external_image_sha256'])
    require(cost['recipe']==recipe and cost['environment']==env and cost['compiler_options']==flags
            and cost['build_fingerprint']==sha(bench.canonical(recipe)),'SPI source/recipe/backend changed')
    for name,key in (('player.elf','image_sha256'),('program.bin','binary_sha256'),('player.hex','hex_sha256')):
        require(sha((folder/name).read_bytes())==cost[key],'A linked SPI artifact changed')
    size=subprocess.check_output([str(bench.toolpath(avr_bin,'avr-size')),str(folder/'player.elf')],text=True)
    match=re.search(r'^\s*(\d+)\s+(\d+)\s+(\d+)\s+',size,re.M);require(match,'Cannot reopen linked SPI size')
    code,data,bss=map(int,match.groups())
    require((cost['text_bytes'],cost['data_bytes'],cost['bss_bytes'])==(code,data,bss)
            and cost['flash_bytes']==cost['program_flash_bytes']==code+data<=32768
            and cost['static_sram_bytes']==data+bss,'Reopened complete SPI cost differs')
    report=load(folder/'observer.json');actual=(folder/'valid.pcm8').read_bytes()
    expected=Path(chain['expected_pwm_path']).read_bytes()
    require(report==verified['report'] and sha((folder/'observer.json').read_bytes())==verified['report_sha256']
            and sha(actual)==verified['actual_pwm_sha256'] and sha(expected)==verified['expected_pwm_sha256']
            and sha((folder/'observer.txt').read_bytes())==verified['observer_metadata_sha256']
            and sha(Path(runner).read_bytes())==verified['runner_sha256']
            and sha(Path(chain['external_image_path']).read_bytes())==verified['external_image_sha256']
            and validate(chain,report,actual,expected),'SPI image/runtime/output proof changed')
    return verified


def reopen_rom(chain,row,folder,avr_bin,runner,lib,wsl,record):
    helpers=ROOT/'Codecs/LPX/research/v5-adaptive-target-player-2026-10-30/reproduction'
    sys.path.insert(0,str(helpers))
    from admit import Epoch
    from player_evidence import PlayerEvidence
    epoch=Epoch(ROOT)
    env=bench.environment(ACTIVE,avr_bin,True,harness=rom.EXAMPLE/'player.cpp',required_symbols=(),retained_symbols=())
    env['settings']={**env['settings'],'queue':256,'prefill':192}
    validation=bench.validation_provenance(runner,lib,wsl)
    # This constructs a current-source checker, not historical receipt reuse.
    # PlayerEvidence then independently reopens every source/recipe/data/image/
    # metadata/runtime/output proof on these newly measured short ROM controls.
    prepared=dict(avr_bin=str(avr_bin),runner=str(runner),lib=str(lib),wsl=wsl,
        build_environment=env,decoder_source_sha256=env['source_sha256'],validation=validation)
    class CurrentRomEvidence(PlayerEvidence):
        def recipe(self,streams,irq):
            # The retained historical checker measured ASM only. These new
            # matched controls explicitly select either backend per bound row.
            flags=self.bench.command_flags(self.env,self.bench.CANDIDATES['unroll1-tune0-lto-call-relax'],row['assembly'],irq)
            flags=[f for f in flags if not f.startswith(('-DLPX4_PROFILE_QUEUE=','-DLPX4_PROFILE_PREFILL=','-DLPX4_PROFILE_IRQ_LOAD='))]
            flags += ['-DLPX_PLAYER_QUEUE=256','-DLPX_PLAYER_PREFILL=192','-DLPX_PLAYER_IRQ_LOAD='+str(irq),
                      '-DLPX_PLAYER_DATA_HEADER="voice_data.h"']
            suffix='#define LPX_PLAYER_SEGMENTS %d\n'%len(streams)
            text=rom.voice_header(streams).replace('profile_','lpx_')+suffix
            layout=rom.voice_header([b'' for _ in streams]).replace('profile_','lpx_')+suffix
            recipe=dict(environment=self.bench.build_provenance(self.env),compiler_options=flags,
                player_config_sha256=self.bench.digest(self.player.EXAMPLE/'player_config.h'),
                voice_layout_sha256=sha(layout.encode()),declared_segment_samples=[int.from_bytes(blob[8:12],'little') for blob in streams])
            build_id=sha(self.bench.canonical(recipe))
            return build_id,sha(self.bench.canonical([build_id,[sha(blob) for blob in streams],sha(text.encode())])),flags
    proof=CurrentRomEvidence(epoch,prepared)
    streams=[Path(part['path']).read_bytes() for part in chain['segments']]
    verified=proof.reuse(record,streams,Path(chain['expected_pwm_path']).read_bytes(),row['extra_irq_cycles'])[0]
    require(verified['cost']['assembly_enabled']==row['assembly'],'Matched ROM backend label differs')
    return verified


def metadata(folder,cost,avr_bin):
    symbols=rom.symbols(folder/'player.elf',avr_bin)
    flags=[f for f in cost['compiler_options'] if f!='-flto' and not f.startswith('-Wl,')]
    command=[str(bench.toolpath(avr_bin,'avr-g++')),*flags,'-I'+str(rom.EXAMPLE),'-c',str(HOST/'player_hardware.cpp'),
             '-o',str(folder/'hardware.o')]
    result=subprocess.run(command,capture_output=True)
    (folder/'hardware-compile.stdout.log').write_bytes(result.stdout);(folder/'hardware-compile.stderr.log').write_bytes(result.stderr)
    if result.returncode:raise RuntimeError('Vendor SPI observer object failed')
    subprocess.run([str(bench.toolpath(avr_bin,'avr-objcopy')),'-O','binary','-j','.progmem.data',
                    str(folder/'hardware.o'),str(folder/'hardware.bin')],check=True,capture_output=True)
    raw=(folder/'hardware.bin').read_bytes();require(len(raw)==74,'Unexpected vendor SPI metadata width')
    values=[int.from_bytes(raw[at:at+2],'little') for at in range(0,len(raw),2)]
    values += [one_symbol(symbols,name)['address'] for name in
        ('lpx_player_head','lpx_player_tail','lpx_player_eof','lpx_player_error','lpx_player_stopped','lpx_player_queue','__bss_end')]
    require(len(values)==44,'Unexpected observer field population')
    (folder/'observer.txt').write_bytes((' '.join(map(str,values))+'\n').encode())
    return values


def validate(chain,report,actual,expected):
    if not rom.validate(report,actual,expected):return False
    spi=report.get('spi',{})
    resets=len(chain['sizes']);payload=chain['expected_payload_bytes'];completed=payload+5*resets
    wanted=dict(bytes_started=completed,bytes_completed=completed,clock_cycles_total=16*completed,
        scheduled_byte_cycles=16,command_bytes=resets,address_bytes=3*resets,dummy_bytes=resets,payload_bytes=payload,
        cs_assertions=resets,cs_deassertions=resets,unsupported_commands=0,bridge_errors=0,cs_high_at_stop=True)
    if any(spi.get(name)!=value for name,value in wanted.items()):return False
    if not (16<=spi['completion_delay_min_cycles']<=spi['completion_delay_max_cycles']<=20
            and 0<=spi['dispatch_lateness_min_cycles']<=spi['dispatch_lateness_max_cycles']<=4):return False
    if chain['kind']=='long' and spi['starts_with_interrupts_enabled']<=0:return False
    return payload<=chain['stream_bytes'] and sum(chain['payload_bytes_by_segment'])==payload


def simulate(chain,row,folder,avr_bin,runner,lib,wsl):
    folder=Path(folder).resolve();cost=build(chain,row,folder,avr_bin);metadata(folder,cost,avr_bin)
    image=Path(chain['external_image_path']);expected_path=Path(chain['expected_pwm_path'])
    expected=expected_path.read_bytes()
    require(sha(image.read_bytes())==chain['external_image_sha256'] and image.stat().st_size==16777216
            and sha(expected)==chain['expected_pwm_sha256'] and len(expected)==chain['samples'],'Prepared SPI reference changed')
    if wsl:
        command=['wsl','-d',wsl,'--','env','LD_LIBRARY_PATH='+linux_path(lib),linux_path(runner),
            linux_path(folder/'player.elf'),linux_path(folder/'valid.pcm8'),linux_path(folder/'observer.json'),
            linux_path(folder/'observer.txt'),linux_path(image),str(chain['samples'])]
    else:
        command=['env','LD_LIBRARY_PATH='+str(lib),str(runner),str(folder/'player.elf'),str(folder/'valid.pcm8'),
            str(folder/'observer.json'),str(folder/'observer.txt'),str(image),str(chain['samples'])]
    # stdout is an ignored live checkpoint log, not capture_output: each emitted
    # 640k-sample progress record must be visible without ending this attempt.
    with (folder/'observer.stdout.log').open('wb') as stdout,(folder/'observer.stderr.log').open('wb') as stderr:
        result=subprocess.run(command,stdout=stdout,stderr=stderr)
    require((folder/'observer.json').is_file() and (folder/'valid.pcm8').is_file(),'SPI observer produced no final evidence')
    report=load(folder/'observer.json');report['observer_exit_code']=result.returncode;save(folder/'observer.json',report)
    actual=(folder/'valid.pcm8').read_bytes()
    require(sha(image.read_bytes())==chain['external_image_sha256'],'External image changed during playback')
    passed=cost['flash_bytes']<=32768 and validate(chain,report,actual,expected)
    result=dict(status='passed' if passed else 'failed',passed=passed,cost=cost,report=report,
        external_image_sha256=chain['external_image_sha256'],expected_pwm_sha256=chain['expected_pwm_sha256'],
        observer_metadata_sha256=sha((folder/'observer.txt').read_bytes()),report_sha256=sha((folder/'observer.json').read_bytes()),
        actual_pwm_sha256=sha(actual),runner_sha256=sha(Path(runner).read_bytes()))
    save(folder/'verification-private.json',result)
    return result

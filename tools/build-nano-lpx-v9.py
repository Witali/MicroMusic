"""Repack and verify all public Nano LPX phrases and the Owl dialogue as v9."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys
import wave

ROOT=Path(__file__).resolve().parents[1]
CODEC=ROOT/'Codecs/LPX/01_ACTIVE_Q0_CODEC'
WEB=ROOT/'web-player'
sys.path.insert(0,str(CODEC/'tools'))
from speech_v9 import repack
from verify_attiny88_player import verify


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wsl')
    parser.add_argument('--jobs',type=int,default=1)
    parser.add_argument('--retain',action='store_true')
    args=parser.parse_args()
    if args.jobs<1:raise ValueError('jobs must be positive')
    previous=read(WEB/'firmware-atmega328p.json')
    dialogue=read(WEB/'audio/lpx-dialogue/manifest.json')
    clips=read(WEB/'audio/lpx-speech/manifest.json')['clips']
    clips.append(dict(read(WEB/'audio/lpx-bread/manifest.json'),clipId='bread'))
    jobs=[]
    for clip in clips:
        clip['variants']=[v for v in clip['variants'] if v['id'] in ('compact','quality')]
        for variant in clip['variants']:
            old=next(v for v in previous['variants'] if v['clipId']==clip['clipId'] and v['id']==variant['id'])
            jobs.append((clip['clipId']+'-'+variant['id'],clip,variant,old,[variant['stream']],variant['audio']))
    jobs.append(('dialogue-quality',None,None,dialogue,
        [s['stream'].replace('.v9.lpx','.lpx') for s in dialogue['segments']],dialogue['audio']))
    assert len(jobs)==9
    sources=[Path(__file__),CODEC/'tools/build_atmega328p_player.py',
        CODEC/'tools/build_attiny88_player.py',CODEC/'tools/verify_attiny88_player.py',
        CODEC/'tools/speech_v9.py',CODEC/'tests/verify_web_asm_equivalence.py',
        CODEC/'examples/ATTINY88_V5_PLAYER/player.cpp',
        CODEC/'examples/ATTINY88_V5_PLAYER/irq_registers.inc',
        CODEC/'profiles/Lpx4Sram512.h',CODEC.parent/'validation/attiny88/sim_player.c',
        ROOT/'Codecs/common/pwm_gain.h',ROOT/'tools/pwm_output_level.py',
        *sorted((CODEC/'src').glob('Lpx4*'))]
    hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
        for p in sources if p.is_file()}
    creation_sources=[ROOT/'ATmega328/Sound/lpx-dialogue/recipe.json',
        ROOT/'tools/build-nano-dialogue.py',ROOT/'tools/dialogue_source.py']
    creation_hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
        for p in creation_sources}
    out=ROOT/'build/nano-v9-release'

    def build_job(job):
        name,clip,variant,old,paths,audio=job
        folder=out/name
        folder.mkdir(parents=True,exist_ok=True)
        streams=[]
        retained=[]
        for i,path in enumerate(paths):
            packed,stats=repack((WEB/path).read_bytes())
            assert len(packed)<stats['input_bytes'],name
            stream=folder/f'{i:02d}.v9.lpx'
            stream.write_bytes(packed)
            streams.append(stream)
            retained.append((stream,WEB/Path(path).with_suffix('.v9.lpx')))
        result=verify(streams,folder/'avr',target='atmega328p',nano_pwm=True,
            queue=32,flash_limit=30720,rom_output_gain=True,normalize_output=True,wsl=args.wsl)
        assert result['accepted'] and result['pwm_exact'] and result['underruns']==0,name
        baseline=old.get('legacy',old)
        assert result['flash_bytes']<baseline['flashBytes'],name
        assert result['outputLevel']['after']['pcmSha256']==old['outputLevel']['after']['pcmSha256'],name
        with wave.open(str(WEB/audio),'rb') as wav:
            assert wav.getparams()[:3]==(1,2,8000)
            public=wav.readframes(wav.getnframes())
        pwm=(folder/'avr/actual.pwm').read_bytes()
        assert b''.join(struct.pack('<h',(value-128)*256) for value in pwm)==public,name
        cost=read(folder/'avr/build.json')
        image=folder/'avr/player.hex'
        retained.append((image,WEB/('firmware/arduino-nano/lpx-nano-'+name+'.hex')))
        timing=dict(simulator='simavr 1.6',playedSamples=result['samples'],underruns=0,
            minTickCycles=result['output_gap_min'],maxTickCycles=result['output_gap_max'],
            maxIrqCycles=result['irq_max'],irqEntryCycles=result['irq_entry_cycles'],
            irqRetiComplete=result['irq_reti_complete'],stackMarginBytes=result['stack_margin'],
            minQueuedSamplesBeforeOutput=result['min_queue'],
            activeDecodeAndIrqCyclesPerSample=result['decode_active_cpu_mean']+result['irq_max'])
        common=dict(flashBytes=result['flash_bytes'],programFlashBytes=result['program_excluding_audio_bytes'],
            staticSramBytes=result['static_ram_bytes'],peakStackBytes=result['stack_bytes'],
            hexSha256=digest(image),outputLevel=result['outputLevel'],
            legacy=dict(flashBytes=baseline['flashBytes'],programFlashBytes=baseline['programFlashBytes'],
                hexSha256=baseline['hexSha256']))
        if variant is not None:
            variant.pop('flashMeasurement',None)
            variant.update(stream=retained[0][1].relative_to(WEB).as_posix(),bytes=cost['embedded_audio_bytes'],
                bitrateBps=cost['embedded_audio_bytes']*64000/clip['samples'],codec='lpx-v9',formatVersion=9,
                outputLevel=result['outputLevel'])
            row=dict(common,id=variant['id'],clipId=clip['clipId'],
                source=retained[-1][1].relative_to(WEB).as_posix(),streamSha256=digest(streams[0]),timing=timing)
        else:
            row=dict(old,**common,compactVersion=9,universalDecoder=True,romOutputGain=True,queue=32,prefill=24,
                streamBytes=cost['embedded_audio_bytes'],sourceHashEncoding='text-lf',
                sourceSha256={**old.get('sourceSha256',{}),**creation_hashes,**hashes})
            for segment,stream,rom in zip(row['segments'],retained,cost['embedded_segment_ranges']):
                segment.update(stream=stream[1].relative_to(WEB).as_posix(),streamBytes=stream[0].stat().st_size,
                    streamSha256=digest(stream[0]),romOffset=rom[0],romEnd=rom[1])
            row['timing']=dict(played=result['samples'],underruns=0,timer_ticks=result['ticks'],
                timer_events=result['timer_events'],queued_at_stop=0,
                tick_interval_min_cycles=result['output_gap_min'],tick_interval_max_cycles=result['output_gap_max'],
                pwm_interval_min_cycles=result['output_gap_min'],pwm_interval_max_cycles=result['output_gap_max'],
                irq_cycles_max=result['irq_max'],irq_entry_cycles=result['irq_entry_cycles'],
                irq_reti_complete=result['irq_reti_complete'],stack_margin_all_bytes=result['stack_margin'])
        print(name,baseline['flashBytes'],'->',result['flash_bytes'],'exact samples',result['samples'],flush=True)
        return row,retained

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        built=list(pool.map(build_job,jobs))
    for path,expected in hashes.items():
        assert hashlib.sha256((ROOT/path).read_bytes().replace(b'\r\n',b'\n')).hexdigest()==expected,path
    catalog=dict(schema='micromusic-lpx-avr-firmware-v2',device='atmega328p',
        cpuHz=16000000,sampleHz=8000,pwmHz=62500,pwmOutput='D3 / PD3 / OC2B',queue=32,prefill=24,
        assemblyEnabled=True,cFallbackSelectable=True,physicalBoardMeasured=False,
        compactVersion=9,universalDecoder=True,romOutputGain=True,
        sourceHashEncoding='text-lf',sourceSha256=hashes,clips=clips,variants=[r for r,_ in built[:-1]])
    save(out/'catalog.json',catalog)
    save(out/'dialogue.json',built[-1][0])
    if args.retain:
        for _,files in built:
            for source,destination in files:
                destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(source,destination)
        save(WEB/'firmware-atmega328p.json',catalog)
        save(WEB/'audio/lpx-dialogue/manifest.json',built[-1][0])
    print('PASS nine smaller universal Nano v9 images, exact public PWM and zero IRQ underruns')


if __name__=='__main__':
    main()

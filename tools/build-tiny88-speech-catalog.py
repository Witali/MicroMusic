"""Build smaller universal LPX v9 Tiny88 images with bit-exact IRQ playback.

Repack the canonical LPX inputs losslessly and verify each full image against
the legacy fixed-header player, the portable C oracle and the public WAV.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys
import wave
from concurrent.futures import ThreadPoolExecutor

ROOT=Path(__file__).resolve().parents[1]
CODEC=ROOT/'Codecs/LPX/01_ACTIVE_Q0_CODEC'
sys.path.insert(0,str(CODEC/'tools'))
from verify_attiny88_player import verify
from speech_v9 import repack

RELEASE_FLAGS=('-fno-gcse','-fno-code-hoisting','-fno-move-loop-invariants',
    '-morder2','-fno-tree-loop-im','-fno-tree-ccp')
RELEASE_FLASH_LIMIT=6656  # 6.5 KiB, including LPX and the gain byte


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(path,text=False):
    data=path.read_bytes()
    return hashlib.sha256(data.replace(b'\r\n',b'\n') if text else data).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--wsl');p.add_argument('--retain',action='store_true',help='Copy verified HEX/catalog into the local web player')
    p.add_argument('--queue',type=int,choices=(24,32),default=32)
    p.add_argument('--mul16-unroll',type=int,choices=(1,2,4,8,16),default=2)
    p.add_argument('--jobs',type=int,default=1)
    args=p.parse_args()
    web=ROOT/'web-player'
    sources=[Path(__file__),CODEC/'tools/build_attiny88_player.py',CODEC/'tools/verify_attiny88_player.py',
        CODEC/'tools/speech_v9.py',
        CODEC/'profiles/Lpx4Sram512.h',CODEC/'examples/ATTINY88_V5_PLAYER/player.cpp',
        CODEC/'examples/ATTINY88_V5_PLAYER/irq_registers.inc',
        CODEC.parent/'validation/attiny88/sim_player.c',
        *sorted((CODEC/'src').glob('Lpx4*')),
        ROOT/'ATtiny88/Music/universal/vendor/ATtiny_DFP/3.4.278/include/avr/iotn88.h',ROOT/'Codecs/common/pwm_gain.h',ROOT/'tools/pwm_output_level.py']
    sources.append(CODEC/'tests/verify_web_asm_equivalence.py')
    hashes={path.relative_to(ROOT).as_posix():sha(path,True) for path in sources if path.is_file()}
    clips=read(web/'audio/lpx-speech/manifest.json')['clips']
    clips.append(dict(read(web/'audio/lpx-bread/manifest.json'),clipId='bread'))
    out=ROOT/'build/tiny88-v9-release'
    jobs=[(clip,variant) for clip in clips for variant in clip['variants']]
    assert len(jobs)==9

    def build_variant(job):
        clip,variant=job
        name=clip['clipId']+'-'+variant['id']
        folder=out/name
        folder.mkdir(parents=True,exist_ok=True)
        original=web/variant['stream']
        packed,stats=repack(original.read_bytes())
        assert stats['file_bytes']<stats['input_bytes'],name
        stream=folder/'audio-v9.lpx'
        stream.write_bytes(packed)
        baseline=verify(original,folder/'legacy',wsl=args.wsl,queue=24,mul16_unroll=2,
            sparse80=variant['id']=='low15',normalize_output=True,universal=False)
        result=verify(stream,folder/'v9',wsl=args.wsl,queue=args.queue,mul16_unroll=args.mul16_unroll,
            flash_limit=RELEASE_FLASH_LIMIT,normalize_output=True,rom_output_gain=True,extra_flags=RELEASE_FLAGS)
        assert baseline['accepted'] and result['accepted'],name
        assert result['flash_bytes']<baseline['flash_bytes'],name
        assert result['decode_active_cpu_mean']+result['irq_max']<=baseline['decode_active_cpu_mean']+baseline['irq_max'],name
        assert result['outputLevel']==dict(baseline['outputLevel'],implementation='producer-rom-q7'),name
        assert result['samples']==clip['samples'],name
        pwm=(folder/'v9/actual.pwm').read_bytes()
        assert pwm==(folder/'legacy/actual.pwm').read_bytes(),name
        with wave.open(str(web/variant['audio']),'rb') as f:
            assert (f.getnchannels(),f.getsampwidth(),f.getframerate(),f.getnframes())==(1,2,8000,clip['samples'])
            published=f.readframes(f.getnframes())
        actual=b''.join(struct.pack('<h',(value-128)*256) for value in pwm)
        assert actual==published,'Firmware must preserve the exact existing public WAV: '+name
        stream_path=Path(variant['stream']).with_suffix('.v9.lpx').as_posix()
        variant.update(stream=stream_path,bytes=len(packed),bitrateBps=len(packed)*64000/clip['samples'],
            codec='lpx-v9',formatVersion=9)
        variant.pop('flashMeasurement',None)
        source='firmware/attiny88/lpx-tiny88-'+name+'.hex'
        hexfile=folder/'v9/player.hex'
        # Include section tail padding counted by avr-size in the same
        # conservative, exclusive stack gap used by the WebUI catalog.
        stack_margin=511-result['static_ram_bytes']-result['stack_bytes']
        assert 0<stack_margin<=result['stack_margin'],name
        row=dict(id=variant['id'],clipId=clip['clipId'],source=source,
            hexSha256=sha(hexfile),streamSha256=sha(stream),flashBytes=result['flash_bytes'],
            programFlashBytes=result['program_excluding_audio_bytes'],staticSramBytes=result['static_ram_bytes'],
            peakStackBytes=result['stack_bytes'],stackMarginBytes=stack_margin,outputLevel=result['outputLevel'],
            fitsStandardBootloader=result['fits_standard_bootloader'],requiresIsp=result['requires_isp'],
            timing=dict(playedSamples=result['samples'],underruns=result['underruns'],
                minTickCycles=result['output_gap_min'],maxTickCycles=result['output_gap_max'],
                irqEntryCycles=result['irq_entry_cycles'],irqRetiComplete=result['irq_reti_complete'],
                minQueuedSamplesBeforeOutput=result['min_queue'],maxIrqCycles=result['irq_max'],
                activeDecodeAndIrqCyclesPerSample=result['decode_active_cpu_mean']+result['irq_max']),
            legacy=dict(hexSha256=sha(folder/'legacy/player.hex'),flashBytes=baseline['flash_bytes'],
                streamBytes=stats['input_bytes'],activeDecodeAndIrqCyclesPerSample=baseline['decode_active_cpu_mean']+baseline['irq_max']))
        print('Verified',name,'Flash',baseline['flash_bytes'],'->',row['flashBytes'],
            'samples',len(pwm),'stack margin',row['stackMarginBytes'],flush=True)
        return row,[(hexfile,web/source),(stream,web/stream_path)]

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        built=list(pool.map(build_variant,jobs))
    variants=[row for row,_ in built]
    retained=[entry for _,files in built for entry in files]
    for name,digest in hashes.items():assert sha(ROOT/name,True)==digest,name
    manifest=dict(schema='micromusic-lpx-attiny88-firmware-v1',device='attiny88',cpuHz=16000000,
        sampleHz=8000,pwmHz=62500,pwmOutput='D9 / PB1 / OC1A',flashLimitBytes=8192,bootloaderLimitBytes=6012,
        sampleRateSelection='compile-time',supportedSampleRates=[8000],
        physicalBoardMeasured=False,arithmeticBackend='avr25-asm',cFallbackSelectable=True,
        queueBytes=args.queue,prefillSamples=args.queue*3//4,mul16Unroll=args.mul16_unroll,
        compactVersion=9,universalDecoder=True,romOutputGain=True,releaseFlashLimitBytes=RELEASE_FLASH_LIMIT,
        compilerOptions=list(RELEASE_FLAGS),
        sourceHashEncoding='text-lf',sourceSha256=hashes,clips=clips,variants=variants)
    path=out/'catalog.json';path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    if args.retain:
        for src,dst in retained:dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
        shutil.copyfile(path,ROOT/'web-player/firmware-lpx-attiny88.json')
    print('PASS nine smaller LPX v9 images with exact public PWM and zero underruns')


if __name__=='__main__':main()

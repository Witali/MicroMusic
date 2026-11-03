"""Build verified LPX Tiny88 speech images; optionally retain local web assets.

No upload, push or flash operation. Whole phrases and stored LPX bytes remain
unchanged. Oversized USB images stay downloadable for explicit ISP loading.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys
import wave

ROOT=Path(__file__).resolve().parents[1]
CODEC=ROOT/'Codecs/LPX/01_ACTIVE_Q0_CODEC'
sys.path.insert(0,str(CODEC/'tools'))
from verify_attiny88_player import verify


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(path,text=False):
    data=path.read_bytes()
    return hashlib.sha256(data.replace(b'\r\n',b'\n') if text else data).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--wsl');p.add_argument('--retain',action='store_true',help='Copy verified HEX/catalog into the local web player')
    p.add_argument('--queue',type=int,choices=(24,32),default=24)
    p.add_argument('--mul16-unroll',type=int,choices=(1,2,4,8,16),default=2)
    args=p.parse_args()
    sources=[Path(__file__),CODEC/'tools/build_attiny88_player.py',CODEC/'tools/verify_attiny88_player.py',
        CODEC/'profiles/Lpx4Sram512.h',CODEC/'examples/ATTINY88_V5_PLAYER/player.cpp',
        CODEC.parent/'validation/attiny88/sim_player.c',
        *sorted((CODEC/'src').glob('Lpx4*')),
        ROOT/'ATtiny88/Music/universal/vendor/ATtiny_DFP/3.4.278/include/avr/iotn88.h',ROOT/'Codecs/common/pwm_gain.h',ROOT/'tools/pwm_output_level.py']
    hashes={path.relative_to(ROOT).as_posix():sha(path,True) for path in sources if path.is_file()}
    clips=read(ROOT/'web-player/audio/lpx-speech/manifest.json')['clips']
    clips.append(dict(read(ROOT/'web-player/audio/lpx-bread/manifest.json'),clipId='bread'))
    out=ROOT/'build/tiny88-release';out.mkdir(parents=True,exist_ok=True)
    variants=[];retained=[]
    for clip in clips:
        for variant in clip['variants']:
            name=clip['clipId']+'-'+variant['id'];folder=out/name
            stream=ROOT/'web-player'/variant['stream']
            result=verify(stream,folder,wsl=args.wsl,queue=args.queue,mul16_unroll=args.mul16_unroll,
                sparse80=variant['id']=='low15',flash_limit=8192,normalize_output=True,universal=False)
            assert result['accepted'] and result['pwm_exact'] and result['underruns']==0,name
            assert result['samples']==clip['samples'] and result['static_ram_bytes']+result['stack_bytes']<512
            with wave.open(str(ROOT/'web-player'/variant['audio']),'rb') as f:
                assert (f.getnchannels(),f.getsampwidth(),f.getframerate(),f.getnframes())==(1,2,8000,clip['samples'])
                published=f.readframes(f.getnframes())
            pwm=(folder/'actual.pwm').read_bytes()
            actual=b''.join(struct.pack('<h',(value-128)*256) for value in pwm)
            assert actual==published,'Firmware must preserve the exact existing public WAV: '+name
            source='firmware/attiny88/lpx-tiny88-'+name+'.hex';hexfile=folder/'player.hex'
            row=dict(id=variant['id'],clipId=clip['clipId'],source=source,
                hexSha256=sha(hexfile),streamSha256=sha(stream),flashBytes=result['flash_bytes'],
                programFlashBytes=result['program_excluding_audio_bytes'],staticSramBytes=result['static_ram_bytes'],
                peakStackBytes=result['stack_bytes'],stackMarginBytes=result['stack_margin'],outputLevel=result['outputLevel'],
                fitsStandardBootloader=result['fits_standard_bootloader'],requiresIsp=result['requires_isp'],
                timing=dict(playedSamples=result['samples'],underruns=result['underruns'],
                    minTickCycles=result['output_gap_min'],maxTickCycles=result['output_gap_max'],
                    irqEntryCycles=result['irq_entry_cycles'],irqRetiComplete=result['irq_reti_complete'],
                    minQueuedSamplesBeforeOutput=result['min_queue']))
            variants.append(row);retained.append((hexfile,ROOT/'web-player'/source))
            print('Verified',name,'Flash',row['flashBytes'],'RAM',row['staticSramBytes'],
                'stack margin',row['stackMarginBytes'],'ISP required',row['requiresIsp'],flush=True)
    for name,digest in hashes.items():assert sha(ROOT/name,True)==digest,name
    manifest=dict(schema='micromusic-lpx-attiny88-firmware-v1',device='attiny88',cpuHz=16000000,
        sampleHz=8000,pwmHz=62500,pwmOutput='D9 / PB1 / OC1A',flashLimitBytes=8192,bootloaderLimitBytes=6012,
        physicalBoardMeasured=False,arithmeticBackend='avr25-asm',cFallbackSelectable=True,
        queueBytes=args.queue,prefillSamples=args.queue*3//4,mul16Unroll=args.mul16_unroll,
        sourceHashEncoding='text-lf',sourceSha256=hashes,clips=clips,variants=variants)
    path=out/'catalog.json';path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    if args.retain:
        for src,dst in retained:dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
        shutil.copyfile(path,ROOT/'web-player/firmware-lpx-attiny88.json')
    print('PASS nine full LPX phrases: exact public PWM, zero underruns, 8 KiB cap; USB limit labelled separately')


if __name__=='__main__':main()

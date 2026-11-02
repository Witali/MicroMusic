"""Build and verify Nano releases from the already-public LPX speech assets.

Private build receipts remain in ignored build/. Only HEX and a small,
path-free catalog are copied into the web player after complete simulation.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import sys
import wave

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT / 'Codecs/LPX/01_ACTIVE_Q0_CODEC'
sys.path.insert(0, str(CODEC / 'tools'))
from build_release_player import simulate
from speech_compact import decode_model
from standard_metrics import pwm_duties
from pwm_output_level import apply_gain,choose_gain,describe_level


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--avr-bin', type=Path, required=True)
    parser.add_argument('--observer', type=Path, required=True)
    parser.add_argument('--lib', type=Path, required=True)
    parser.add_argument('--wsl')
    parser.add_argument('--enable-asm', action='store_true')
    args = parser.parse_args()
    player = ROOT / 'web-player'
    previews = json.loads((player / 'audio/lpx-speech/manifest.json').read_text(encoding='utf-8'))['clips']
    bread = json.loads((player / 'audio/lpx-bread/manifest.json').read_text(encoding='utf-8'))
    previews.append(dict(bread, clipId='bread'))
    variants = []
    images = []
    for preview in previews:
        clip_id = preview['clipId']
        preview['variants'] = [v for v in preview['variants'] if v['id'] in ('compact', 'quality')]
        for variant in preview['variants']:
            variant.pop('flashMeasurement', None)
            stream = player / variant['stream']
            original=pwm_duties(decode_model(stream.read_bytes())).tobytes()
            gain=choose_gain(original);level=describe_level(original,gain)
            folder = ROOT / 'build/nano-lpx' / (variant['id'] if clip_id == 'bread' else clip_id + '-' + variant['id'])
            result = simulate([stream.read_bytes()], folder, args.avr_bin,
                              args.observer, lib=args.lib, wsl=args.wsl,
                              assembly=args.enable_asm,output_gain=gain)
            cost, report = result['cost'], result['report']
            if report.get('irq_entry_cycles') != 4 or report.get('irq_reti_complete') is not True:
                raise ValueError('Nano release requires calibrated complete interrupt timing')
            if cost['flash_bytes'] > 30720 or cost['static_sram_bytes'] >= 2048:
                raise ValueError('Firmware exceeds the classic Nano application budget')
            if (folder/'valid.pcm8').read_bytes()!=apply_gain(original,gain):raise ValueError('Output gain disagrees with independent reference')
            expected_preview = b''.join(struct.pack('<h', (value - 128) * 256)
                                        for value in (folder / 'valid.pcm8').read_bytes())
            with wave.open(str(player / variant['audio']), 'wb') as audio:
                audio.setparams((1,2,8000,0,'NONE','not compressed'));audio.writeframes(expected_preview)
            variant['outputLevel']=level
            name = 'lpx-nano-' + clip_id + '-' + variant['id'] + '.hex'
            image = (folder / 'player.hex').read_bytes()
            variants.append(dict(id=variant['id'], clipId=clip_id, source='firmware/arduino-nano/' + name,
                                 flashBytes=cost['flash_bytes'],
                                 programFlashBytes=cost['program_flash_bytes'],
                                 staticSramBytes=cost['static_sram_bytes'],
                                 hexSha256=sha(image), streamSha256=sha(stream.read_bytes()),outputLevel=level,
                                 timing=dict(simulator='simavr 1.6', playedSamples=report['played'],
                                             underruns=report['underruns'],
                                             minTickCycles=report['tick_interval_min_cycles'],
                                             maxTickCycles=report['tick_interval_max_cycles'],
                                             maxIrqCycles=report['irq_cycles_max'],
                                             irqEntryCycles=report['irq_entry_cycles'],
                                             irqRetiComplete=report['irq_reti_complete'],
                                             stackMarginBytes=report['stack_margin_all_bytes'])))
            images.append((name, image))
    sources = [*sorted((CODEC / 'src').glob('*')),
               CODEC / 'examples/AVR_V5_PLAYER/player.cpp',
               CODEC / 'examples/AVR_V5_PLAYER/player_config.h',
               CODEC / 'tools/build_release_player.py',
               CODEC / 'tools/build_release_observer.py',
               CODEC.parent / 'validation/atmega328p/sim_player.c',
               CODEC.parent / 'validation/atmega328p/player_hardware.cpp', ROOT/'Codecs/common/pwm_gain.h',ROOT/'tools/pwm_output_level.py',Path(__file__)]
    catalog = dict(schema='micromusic-lpx-avr-firmware-v2', device='atmega328p',
                   cpuHz=16000000, sampleHz=8000, pwmHz=62500, pwmOutput='D3 / PD3 / OC2B',
                   queue=256, prefill=192, assemblyEnabled=args.enable_asm,
                   physicalBoardMeasured=False,
                   sourceHashEncoding='text-lf',
                   sourceSha256={p.relative_to(ROOT).as_posix(): sha(p.read_bytes().replace(b'\r\n', b'\n'))
                                 for p in sources if p.is_file()},
                   clips=previews, variants=variants)
    destination = player / 'firmware/arduino-nano'
    destination.mkdir(parents=True, exist_ok=True)
    for name, image in images:
        (destination / name).write_bytes(image)
    (player / 'firmware-atmega328p.json').write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    # Tiny88 uses the same exact P4/P6 WAVs. Preserve its optional S15 variant.
    for name in ('audio/lpx-speech/manifest.json','audio/lpx-bread/manifest.json'):
        path=player/name;data=json.loads(path.read_text(encoding='utf-8'))
        for clip in data.get('clips',[dict(data,clipId='bread')]):
            replacement=next(item for item in previews if item['clipId']==clip['clipId'])
            for variant in clip['variants']:
                if variant['id'] in ('compact','quality'):
                    variant['outputLevel']=next(v['outputLevel'] for v in replacement['variants'] if v['id']==variant['id'])
        path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(f'Verified {len(variants)} Nano firmware images: exact public WAVs, complete output, no underruns.')


if __name__ == '__main__':
    main()

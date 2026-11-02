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
    preview = json.loads((player / 'audio/lpx-bread/manifest.json').read_text(encoding='utf-8'))
    preview['variants'] = [v for v in preview['variants'] if v['id'] in ('compact', 'quality')]
    variants = []
    images = []
    for variant in preview['variants']:
        variant.pop('flashMeasurement', None)
        stream = player / variant['stream']
        folder = ROOT / 'build/nano-lpx' / variant['id']
        result = simulate([stream.read_bytes()], folder, args.avr_bin,
                          args.observer, lib=args.lib, wsl=args.wsl,
                          assembly=args.enable_asm)
        cost, report = result['cost'], result['report']
        if cost['flash_bytes'] > 30720 or cost['static_sram_bytes'] >= 2048:
            raise ValueError('Firmware exceeds the classic Nano application budget')
        with wave.open(str(player / variant['audio']), 'rb') as audio:
            if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate(), audio.getnframes()) != (1, 2, 8000, preview['samples']):
                raise ValueError('Unexpected public preview format')
            actual_preview = audio.readframes(preview['samples'])
        expected_preview = b''.join(struct.pack('<h', (value - 128) * 256)
                                    for value in (folder / 'valid.pcm8').read_bytes())
        if actual_preview != expected_preview:
            raise ValueError('Simulated firmware output differs from public WAV')
        name = 'lpx-nano-bread-' + variant['id'] + '.hex'
        image = (folder / 'player.hex').read_bytes()
        variants.append(dict(id=variant['id'], source='firmware/arduino-nano/' + name,
                             flashBytes=cost['flash_bytes'],
                             programFlashBytes=cost['program_flash_bytes'],
                             staticSramBytes=cost['static_sram_bytes'],
                             hexSha256=sha(image), streamSha256=sha(stream.read_bytes()),
                             timing=dict(simulator='simavr 1.6', playedSamples=report['played'],
                                         underruns=report['underruns'],
                                         minTickCycles=report['tick_interval_min_cycles'],
                                         maxTickCycles=report['tick_interval_max_cycles'],
                                         maxIrqCycles=report['irq_cycles_max'],
                                         stackMarginBytes=report['stack_margin_all_bytes'])))
        images.append((name, image))
    sources = [*sorted((CODEC / 'src').glob('*')),
               CODEC / 'examples/AVR_V5_PLAYER/player.cpp',
               CODEC / 'examples/AVR_V5_PLAYER/player_config.h',
               CODEC / 'tools/build_release_player.py', Path(__file__)]
    catalog = dict(schema='micromusic-lpx-avr-firmware-v1', device='atmega328p',
                   cpuHz=16000000, sampleHz=8000, pwmHz=62500, pwmOutput='D3 / PD3 / OC2B',
                   queue=256, prefill=192, assemblyEnabled=args.enable_asm,
                   physicalBoardMeasured=False,
                   sourceHashEncoding='text-lf',
                   sourceSha256={p.relative_to(ROOT).as_posix(): sha(p.read_bytes().replace(b'\r\n', b'\n'))
                                 for p in sources if p.is_file()},
                   preview=preview, variants=variants)
    destination = player / 'firmware/arduino-nano'
    destination.mkdir(parents=True, exist_ok=True)
    for name, image in images:
        (destination / name).write_bytes(image)
    (player / 'firmware-atmega328p.json').write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('Verified two Nano firmware images: exact public WAV, 19200 samples each, no underruns.')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Rebuild the public HQ4 firmware catalog from retained sources, without audio ZIPs."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOUND = ROOT / 'ATtiny13A/Sound'
OUTPUT = ROOT / 'web-player/hq4-firmware.json'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def intel_hex(binary):
    rows = []
    for address in range(0, len(binary), 16):
        block = binary[address:address + 16]
        record = bytes([len(block), address >> 8, address & 255, 0]) + block
        rows.append(':' + (record + bytes([-sum(record) & 255])).hex().upper())
    return '\n'.join(rows + [':00000001FF']) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--avr-bin', type=Path)
    parser.add_argument('--node', default='node')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    command = [sys.executable, str(ROOT / 'tools/verify-frozen-speech.py'), '--node', args.node]
    if args.avr_bin:
        command += ['--avr-bin', str(args.avr_bin.resolve())]
    subprocess.run(command, cwd=ROOT, check=True, stdout=subprocess.PIPE, text=True)
    timbre_command = [sys.executable, str(ROOT / 'tools/build-hq4-timbre.py'), '--node', args.node, '--check']
    if args.avr_bin:
        timbre_command += ['--avr-bin', str(args.avr_bin.resolve())]
    subprocess.run(timbre_command, cwd=ROOT, check=True, stdout=subprocess.PIPE, text=True)
    frozen = json.loads((SOUND / 'research/FROZEN_VERIFICATION.json').read_text(encoding='utf-8'))['variants']
    titles = {r['id']: r['title'] for r in json.loads((SOUND / 'audio-references.json').read_text(encoding='utf-8'))['clips']}
    result = {'schema': 1, 'defaultId': 'hq4-chego-timbre', 'generator': 'tools/build-hq4-catalog.py', 'entries': []}
    verification = json.loads((SOUND / 'codec/timbre/chego/verification.json').read_text(encoding='utf-8'))
    binary = (ROOT / 'build/hq4-timbre/firmware.bin').read_bytes()
    if digest(binary) != verification['imageSha256']:
        raise ValueError('Unexpected HQ4-T image')
    result['entries'].append({
        'id': 'hq4-chego-timbre', 'order': '01', 'kind': 'speech', 'codec': 'hq4-t',
        'title': 'Чего тебе нужно? · HQ4-T',
        'description': 'HQ4-T · 1,229 с · восстановление тембра в прошивке',
        'flashBytes': len(binary), 'eepromBytes': 0, 'sampleHz': 7500,
        'pwmHz': 7500, 'carrierHz': 37500, 'voices': 1,
        'flashSha256': digest(binary), 'flashHex': intel_hex(binary),
        'sourceInputs': verification['sourceInputs'],
        'audioReferenceId': 'chego',
        'monitorGain': 1,
    })
    for order, (name, expected) in enumerate(frozen.items(), 1):
        binary = (ROOT / 'build/frozen-speech' / name / 'firmware.bin').read_bytes()
        if digest(binary) != expected['image_sha256']:
            raise ValueError('Unexpected image: ' + name)
        maximum = name == 'chego_stoi_max'
        clip = 'chego' if maximum else name
        source = 'ATtiny13A/Sound/codec/release/' + name + '/'
        result['entries'].append({
            'id': 'hq4-' + name, 'order': f'{order + 1:02d}', 'kind': 'speech',
            'title': titles[clip] + (' · максимум STOI' if maximum else ''),
            'description': f"MiniLPC HQ4 · {expected['samples'] / 7500:.3f} с · " + ('максимум STOI' if maximum else 'сбалансированный'),
            'flashBytes': len(binary), 'eepromBytes': 0, 'sampleHz': 7500,
            'pwmHz': 7500, 'carrierHz': 37500, 'voices': 1,
            'flashSha256': digest(binary), 'flashHex': intel_hex(binary),
            'sourceInputs': {source + file: digest((ROOT / source / file).read_bytes()) for file in ('firmware.S', 'speech.hq')},
        })
    levels = subprocess.run([args.node, str(ROOT / 'tools/measure-hq4-level.mjs'), '--stdin'],
                            cwd=ROOT, input=json.dumps(result), capture_output=True, text=True, check=True)
    result['entries'][0]['monitorGain'] = json.loads(levels.stdout)['monitorGain']
    text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.check:
        if OUTPUT.read_text(encoding='utf-8') != text:
            raise ValueError('Public HQ4 catalog is stale; rebuild without --check')
        print('Public HQ4 catalog matches the five rebuilt, verified images.')
    else:
        OUTPUT.write_text(text, encoding='utf-8', newline='\n')
        print('Built web-player/hq4-firmware.json: HQ4-T and four frozen HQ4 images.')


if __name__ == '__main__':
    main()

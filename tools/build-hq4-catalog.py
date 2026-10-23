#!/usr/bin/env python3
"""Rebuild three selected speech examples and retain the legacy research catalog."""
import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOUND = ROOT / 'ATtiny13A/Sound'
OUTPUT = ROOT / 'web-player/hq4-firmware.json'
ARCHIVE = SOUND / 'research/hq4-catalog-archive.json'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def intel_hex(binary):
    rows = []
    for address in range(0, len(binary), 16):
        block = binary[address:address + 16]
        record = bytes([len(block), address >> 8, address & 255, 0]) + block
        rows.append(':' + (record + bytes([-sum(record) & 255])).hex().upper())
    return '\n'.join(rows + [':00000001FF']) + '\n'


def original_audio(clip):
    path = ROOT/'web-player/audio/originals'/(clip['id']+'.wav')
    if path.stat().st_size != clip['bytes'] or digest(path.read_bytes()) != clip['sha256']:
        raise ValueError('Public original WAV differs from canonical reference: '+clip['id'])
    with wave.open(str(path), 'rb') as audio:
        if (audio.getnframes(), audio.getframerate(), audio.getnchannels(), audio.getsampwidth()*8,
                audio.getcomptype()) != (clip['samples'], clip['sample_rate'], clip['channels'],
                                        clip['bits_per_sample'], 'NONE'):
            raise ValueError('Unexpected public original WAV format: '+clip['id'])
    return dict(audioReferenceId=clip['id'], originalAudioUrl='./audio/originals/'+clip['id']+'.wav',
                originalAudioSha256=clip['sha256'])


def listening_levels(catalog, node):
    levels = subprocess.run([node, str(ROOT/'tools/measure-hq4-level.mjs'), '--stdin'],
                            cwd=ROOT, input=json.dumps(catalog), capture_output=True, text=True, check=True)
    for entry in catalog['entries']:
        gain = json.loads(levels.stdout)['monitorGains'].get(entry['id'])
        if gain is not None:
            entry['monitorGain'] = gain


def tiny_entry(clip, original, avr_bin, node):
    folder = SOUND/'research/tiny-speech'/clip['id']
    model = folder/'model.json'
    quality = json.loads((folder/'quality.json').read_text(encoding='utf-8'))
    retained = json.loads((folder/'build.json').read_text(encoding='utf-8'))
    spec = importlib.util.spec_from_file_location('build_tiny_speech_catalog', ROOT/'tools/build-tiny-speech.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    output = ROOT/'build/speech-showcase'/clip['id']
    report = builder.build(model, output, avr_bin, node)
    if (report['status'] != 'verified' or report['verifiedLoops'] != 3 or
            report['modelSha256'] != quality['model_sha256'] or
            report['imageSha256'] != retained['imageSha256'] or
            report['eepromSha256'] != retained['eepromSha256'] or
            digest((output/'actual.raw').read_bytes()[:clip['samples']]) != quality['pcm_sha256']):
        raise ValueError('Selected speech does not match its retained model, quality or AVR verification: '+clip['id'])
    sources = [SOUND/'codec/tiny/firmware.S', SOUND/'codec/tiny_period.py',
               SOUND/'codec/fixed_period.py', SOUND/'codec/dc_blocker.py',
               model]
    binary, eeprom = (output/'firmware.bin').read_bytes(), (output/'eeprom.bin').read_bytes()
    return dict(id='hq4-'+clip['id']+'-tiny', kind='speech', codec='tiny-period',
                title=clip['title'], description=f"Tiny Speech · {clip['samples']/7500:.3f} с",
                flashBytes=len(binary), eepromBytes=len(eeprom), sampleHz=7500, pwmHz=7500,
                carrierHz=37500, voices=1, phraseSamples=clip['samples'],
                flashSha256=digest(binary), flashHex=intel_hex(binary),
                eepromSha256=digest(eeprom), eepromHex=intel_hex(eeprom),
                sourceInputs={str(path.relative_to(ROOT)).replace('\\','/'):digest(path.read_bytes()) for path in sources},
                verification='../'+str((folder/'build.json').relative_to(ROOT)).replace('\\','/'),
                research='../'+str((folder/'README.md').relative_to(ROOT)).replace('\\','/'), **original)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--avr-bin', type=Path)
    parser.add_argument('--node', default='node')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    clips = json.loads((SOUND/'audio-references.json').read_text(encoding='utf-8'))['clips']
    originals = {clip['id']: original_audio(clip) for clip in clips}
    command = [sys.executable, str(ROOT / 'tools/verify-frozen-speech.py'), '--node', args.node]
    if args.avr_bin:
        command += ['--avr-bin', str(args.avr_bin.resolve())]
    subprocess.run(command, cwd=ROOT, check=True, stdout=subprocess.PIPE, text=True)
    variants = [
        ('chego-auto', 'hq4-chego-auto', 'Чего тебе нужно? · Auto', 'Автоподбор · STOI ≥0,9005'),
        ('chego-spectrum', 'hq4-chego-spectrum', 'Чего тебе нужно? · Спектр', 'Автоподбор спектра · STOI ≥0,89'),
        ('chego', 'hq4-chego-timbre', 'Чего тебе нужно? · HQ4-T', 'HQ4-T · восстановление тембра в прошивке'),
    ]
    for variant, _, _, _ in variants:
        timbre_command = [sys.executable, str(ROOT / 'tools/build-hq4-timbre.py'),
                          '--node', args.node, '--check', '--variant', variant]
        if args.avr_bin:
            timbre_command += ['--avr-bin', str(args.avr_bin.resolve())]
        subprocess.run(timbre_command, cwd=ROOT, check=True, stdout=subprocess.PIPE, text=True)
    frozen = json.loads((SOUND / 'research/FROZEN_VERIFICATION.json').read_text(encoding='utf-8'))['variants']
    titles = {clip['id']: clip['title'] for clip in clips}
    result = {'schema': 1, 'defaultId': 'hq4-chego-auto', 'generator': 'tools/build-hq4-catalog.py', 'entries': []}
    for order, (variant, entry_id, title, description) in enumerate(variants, 1):
        verification = json.loads((SOUND / 'codec/timbre' / variant / 'verification.json').read_text(encoding='utf-8'))
        folder = ROOT / 'build/hq4-timbre'
        if variant != 'chego':
            folder /= variant
        binary = (folder / 'firmware.bin').read_bytes()
        if digest(binary) != verification['imageSha256']:
            raise ValueError('Unexpected HQ4-T image: ' + variant)
        result['entries'].append({
            'id': entry_id, 'order': f'{order:02d}', 'kind': 'speech', 'codec': 'hq4-t', 'variant': variant,
            'title': title, 'description': description + ' · 1,229 с',
            'flashBytes': len(binary), 'eepromBytes': 0, 'sampleHz': 7500,
            'pwmHz': 7500, 'carrierHz': 37500, 'voices': 1,
            'flashSha256': digest(binary), 'flashHex': intel_hex(binary),
            'sourceInputs': verification['sourceInputs'], **originals['chego'], 'monitorGain': 1,
            'research': '../ATtiny13A/Sound/codec/' + ('timbre/README.md' if variant == 'chego' else 'AUTO_ENCODER.md'),
        })
    for order, (name, expected) in enumerate(frozen.items(), 1):
        binary = (ROOT / 'build/frozen-speech' / name / 'firmware.bin').read_bytes()
        if digest(binary) != expected['image_sha256']:
            raise ValueError('Unexpected image: ' + name)
        maximum = name == 'chego_stoi_max'
        clip = 'chego' if maximum else name
        source = 'ATtiny13A/Sound/codec/release/' + name + '/'
        result['entries'].append({
            'id': 'hq4-' + name, 'order': f'{order + len(variants):02d}', 'kind': 'speech',
            'title': titles[clip] + (' · максимум STOI' if maximum else ''),
            'description': f"MiniLPC HQ4 · {expected['samples'] / 7500:.3f} с · " + ('максимум STOI' if maximum else 'сбалансированный'),
            'flashBytes': len(binary), 'eepromBytes': 0, 'sampleHz': 7500,
            'pwmHz': 7500, 'carrierHz': 37500, 'voices': 1,
            'flashSha256': digest(binary), 'flashHex': intel_hex(binary),
            'sourceInputs': {source + file: digest((ROOT / source / file).read_bytes()) for file in ('firmware.S', 'speech.hq')},
            **originals[clip],
        })
    archive = result
    listening_levels(archive, args.node)
    selected = [tiny_entry(clip, originals[clip['id']], args.avr_bin, args.node)
                for clip in clips if clip['id'] in ('chego','otvechaesh')]
    selected.append(dict(next(entry for entry in archive['entries'] if entry['id']=='hq4-vinni'), codec='hq4'))
    for order, entry in enumerate(selected, 1):
        entry['order'] = f'{order:02d}'
    winners = {entry['audioReferenceId']:entry['id'] for entry in selected}
    result = dict(schema=1, defaultId=winners['chego'], generator='tools/build-hq4-catalog.py',
                  entries=selected, archive='../ATtiny13A/Sound/research/hq4-catalog-archive.json',
                  aliases={entry['id']:winners[entry['audioReferenceId']] for entry in archive['entries']
                           if entry['id'] != winners[entry['audioReferenceId']]})
    listening_levels(dict(entries=selected, referenceEntries=archive['entries']), args.node)
    for path, catalog in ((OUTPUT,result),(ARCHIVE,archive)):
        text = json.dumps(catalog, ensure_ascii=False, indent=2)+'\n'
        if args.check:
            if path.read_text(encoding='utf-8') != text:
                raise ValueError(str(path.relative_to(ROOT))+' is stale; rebuild without --check')
        else:
            path.write_text(text, encoding='utf-8', newline='\n')
    print('Verified three selected speech examples and seven archived HQ4/HQ4-T images.')


if __name__ == '__main__':
    main()

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
    playback = json.loads((ROOT/'web-player/audio/originals/playback/manifest.json').read_text(encoding='utf-8'))
    copy = next(row for row in playback['clips'] if row['id'] == clip['id'])
    path = ROOT/'web-player'/copy['url']
    if copy['sourceSha256'] != clip['sha256'] or digest(path.read_bytes()) != copy['sha256']:
        raise ValueError('Playback WAV does not match its source manifest: '+clip['id'])
    return dict(audioReferenceId=clip['id'], originalAudioUrl='./audio/originals/'+clip['id']+'.wav',
                originalAudioSha256=clip['sha256'], originalPlaybackUrl=copy['url'],
                originalPlaybackSha256=copy['sha256'])


def retain_report(report, clip, check):
    path = SOUND/'research/speech-showcase'/clip/'build.json'
    if check:
        retained = json.loads(path.read_text(encoding='utf-8'))
        for key in ('status','playbackMode','flashBytes','imageSha256','eepromSha256','phraseSamples','verifiedLoops'):
            if retained[key] != report[key]:
                raise ValueError('Stale selected speech verification: '+clip+' / '+key)
        for key in ('actualPcmSha256','verifiedSamples','silenceSamplesVerified','pass'):
            if retained['verification'][key] != report['verification'][key]:
                raise ValueError('Stale selected speech PCM verification: '+clip+' / '+key)
        if retained.get('outputLevel') != report.get('outputLevel'):
            raise ValueError('Stale firmware output level: '+clip)
    else:
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    return '../'+str(path.relative_to(ROOT)).replace('\\','/')


def tiny_entry(clip, original, avr_bin, node, check):
    folder = SOUND/'research/tiny-speech'/clip['id']
    model = folder/'model.json'
    quality = json.loads((folder/'quality.json').read_text(encoding='utf-8'))
    retained = json.loads((folder/'build.json').read_text(encoding='utf-8'))
    spec = importlib.util.spec_from_file_location('build_tiny_speech_catalog', ROOT/'tools/build-tiny-speech.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    output = ROOT/'build/speech-showcase'/clip['id']
    report = builder.build(model, output, avr_bin, node, play_once=True, maximize_output=True)
    if (report['status'] != 'verified' or report['verifiedLoops'] != 1 or
            report['modelSha256'] != quality['model_sha256'] or
            report['eepromSha256'] != retained['eepromSha256'] or
            report['outputLevel']['before']['pcmSha256'] != quality['pcm_sha256'] or
            digest((output/'actual.raw').read_bytes()[:clip['samples']]) != report['outputLevel']['after']['pcmSha256']):
        raise ValueError('Selected speech does not match its retained model, quality or AVR verification: '+clip['id'])
    sources = [SOUND/'codec/tiny/firmware.S', SOUND/'codec/tiny_period.py',
               SOUND/'codec/fixed_period.py', SOUND/'codec/dc_blocker.py',
               SOUND/'codec/output_level.py', model]
    binary, eeprom = (output/'firmware.bin').read_bytes(), (output/'eeprom.bin').read_bytes()
    return dict(id='hq4-'+clip['id']+'-tiny', kind='speech', codec='tiny-period',
                title=clip['title'], description=f"Tiny Speech · {clip['samples']/7500:.3f} с",
                flashBytes=len(binary), eepromBytes=len(eeprom), sampleHz=7500, pwmHz=7500,
                carrierHz=37500, voices=1, phraseSamples=clip['samples'],
                playOnce=True,
                outputLevel=report['outputLevel'],
                flashSha256=digest(binary), flashHex=intel_hex(binary),
                eepromSha256=digest(eeprom), eepromHex=intel_hex(eeprom),
                sourceInputs={str(path.relative_to(ROOT)).replace('\\','/'):digest(path.read_bytes()) for path in sources},
                verification=retain_report(report,clip['id'],check),
                research='../'+str((folder/'README.md').relative_to(ROOT)).replace('\\','/'), **original)


def hq4_once_entry(clip, original, avr_bin, node, check):
    spec = importlib.util.spec_from_file_location('build_hq4_oneshot_catalog',ROOT/'tools/build-hq4-oneshot.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    output = ROOT/'build/speech-showcase'/clip['id']
    report = builder.build(clip['id'],output,avr_bin,node,maximize_output=True)
    if report['status']!='verified' or report['verifiedLoops']!=1:
        raise ValueError('One-shot HQ4 verification failed: '+clip['id'])
    binary = (output/'firmware.bin').read_bytes()
    sources = [SOUND/'codec/oneshot/hq4.S',SOUND/'codec/release'/clip['id']/'speech.hq',
               SOUND/'codec/output_level.py']
    return dict(id='hq4-'+clip['id'],kind='speech',codec='hq4',title=clip['title'],
                description=f"MiniLPC HQ4 · {clip['samples']/7500:.3f} с",order='03',
                flashBytes=len(binary),eepromBytes=0,sampleHz=7500,pwmHz=7500,carrierHz=37500,
                voices=1,phraseSamples=clip['samples'],playOnce=True,
                outputLevel=report['outputLevel'],
                flashSha256=digest(binary),flashHex=intel_hex(binary),
                sourceInputs={str(path.relative_to(ROOT)).replace('\\','/'):digest(path.read_bytes()) for path in sources},
                verification=retain_report(report,clip['id'],check),
                research='../ATtiny13A/Sound/codec/SPEECH_SHOWCASE.md',**original)


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
            'sourceInputs': verification['sourceInputs'], **originals['chego'],
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
    selected = [tiny_entry(clip, originals[clip['id']], args.avr_bin, args.node,args.check)
                for clip in clips if clip['id'] in ('chego','otvechaesh')]
    selected.append(hq4_once_entry(next(clip for clip in clips if clip['id']=='vinni'),originals['vinni'],args.avr_bin,args.node,args.check))
    for order, entry in enumerate(selected, 1):
        entry['order'] = f'{order:02d}'
    winners = {entry['audioReferenceId']:entry['id'] for entry in selected}
    result = dict(schema=1, defaultId=winners['chego'], generator='tools/build-hq4-catalog.py',
                  entries=selected, archive='../ATtiny13A/Sound/research/hq4-catalog-archive.json',
                  aliases={entry['id']:winners[entry['audioReferenceId']] for entry in archive['entries']
                           if entry['id'] != winners[entry['audioReferenceId']]})
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

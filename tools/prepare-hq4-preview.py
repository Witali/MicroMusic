#!/usr/bin/env python3
"""Restore verified HQ4 listening assets into ignored build/hq4-preview."""
import argparse
import base64
import hashlib
import io
import json
import re
import wave
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOUND = ROOT / 'ATtiny13A/Sound'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def checked(data, expected, label):
    if digest(data) != expected:
        raise ValueError('SHA-256 mismatch: ' + label)
    return data


def hex_image(text):
    image = bytearray()
    for row in text.split():
        record = bytes.fromhex(row[1:]) if row.startswith(':') else b''
        if len(record) < 5 or len(record) != record[0] + 5 or sum(record) & 255:
            raise ValueError('Invalid Intel HEX record')
        if record[3] == 1:
            break
        if record[3] != 0:
            raise ValueError('Unsupported HEX record type')
        address = int.from_bytes(record[1:3], 'big')
        end = address + record[0]
        if end > 1024:
            raise ValueError('ATtiny13A flash overflow')
        image.extend(b'\xff' * max(0, end - len(image)))
        image[address:end] = record[4:-1]
    return bytes(image)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True, type=Path)
    args = parser.parse_args()
    manifest = json.loads((SOUND / 'audio-references.json').read_text(encoding='utf-8'))
    frozen = json.loads((SOUND / 'research/FROZEN_VERIFICATION.json').read_text(encoding='utf-8'))['variants']
    archive = manifest['archive']
    checked(args.archive.read_bytes(), archive['sha256'], str(args.archive))
    with zipfile.ZipFile(args.archive) as source:
        player = checked(source.read(archive['player_entry']), archive['player_sha256'], 'ChatGPT player')
    match = re.search(r'const CLIPS=(.*?);</script>', player.decode('utf-8'), re.S)
    if not match:
        raise ValueError('Missing HQ4 player data')
    data = json.loads(match.group(1))
    references = {row['id']: row for row in manifest['clips']}
    # Validate everything before creating outputs. No arbitrary ZIP paths are extracted.
    assets = []
    for name in ('chego', 'otvechaesh', 'vinni', 'chego_stoi_max'):
        clip = 'chego' if name == 'chego_stoi_max' else name
        item = data[clip]
        maximum = name == 'chego_stoi_max'
        binary = checked(base64.b64decode(item['binMax' if maximum else 'bin']), frozen[name]['image_sha256'], name + ' flash')
        raw = checked(base64.b64decode(item['expectedMax' if maximum else 'expected']), frozen[name]['sha256'], name + ' PCM')
        hex_text = item['hexMax' if maximum else 'hex']
        if hex_image(hex_text) != binary:
            raise ValueError('HEX differs from frozen binary: ' + name)
        original = checked(base64.b64decode(item['sound']['original']), references[clip]['sha256'], clip + ' original WAV')
        with wave.open(io.BytesIO(original)) as wav:
            ref = references[clip]
            if (wav.getnframes(), wav.getframerate(), wav.getnchannels(), wav.getsampwidth() * 8) != (ref['samples'], ref['sample_rate'], ref['channels'], ref['bits_per_sample']):
                raise ValueError('Unexpected WAV format: ' + clip)
        assets.append((name, clip, item, maximum, binary, raw, hex_text, original))
    output = ROOT / 'build/hq4-preview'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'chatgpt-player.html').write_bytes(player)
    catalog = {'schema': 1, 'defaultId': 'hq4-chego', 'entries': []}
    for order, (name, clip, item, maximum, binary, raw, hex_text, original) in enumerate(assets, 1):
        folder = output / name
        folder.mkdir(exist_ok=True)
        (folder / 'firmware.bin').write_bytes(binary)
        (folder / 'firmware.hex').write_text(hex_text, encoding='ascii', newline='\n')
        (folder / 'expected.raw').write_bytes(raw)
        (folder / 'original.wav').write_bytes(original)
        (folder / 'hq4.wav').write_bytes(base64.b64decode(item['sound']['max' if maximum else 'new']))
        prefix = '../build/hq4-preview/' + name + '/'
        catalog['entries'].append({
            'id': 'hq4-' + name, 'order': f'{order:02d}', 'kind': 'speech',
            'title': references[clip]['title'] + (' · максимум STOI' if maximum else ''),
            'description': f'MiniLPC HQ4 · {len(raw) / 7500:.3f} с · ' + ('максимум STOI' if maximum else 'сбалансированный'),
            'flashBytes': len(binary), 'eepromBytes': 0, 'sampleHz': 7500,
            # The renderer consumes OCR0B writes: one speech sample per five PWM periods.
            'pwmHz': 7500, 'carrierHz': 37500, 'voices': 1,
            'flashSha256': digest(binary), 'flashHex': hex_text, 'source': prefix + 'firmware.hex',
            'preview': prefix + 'hq4.wav', 'reference': prefix + 'original.wav',
            'originalPlayer': '../build/hq4-preview/chatgpt-player.html',
        })
    (output / 'firmware.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('Verified 3 originals and 4 frozen HQ4 images.')
    print('Open /web-player/?collection=hq4 on the repository local server.')


if __name__ == '__main__':
    main()

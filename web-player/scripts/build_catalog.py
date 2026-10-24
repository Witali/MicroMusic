"""Verify every retained firmware image without executing embedded code."""
from pathlib import Path
from zipfile import ZipFile
import hashlib
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
MUSIC = ROOT / 'ATtiny13A' / 'Music'
OUTPUT = ROOT / 'web-player' / 'firmware.json'
SPECS = [
    ('rhythmic', '01', 'Люмьер · Экспедиция 33', 'Полная аранжировка из Expedition 33, 3:42. Автоупаковка повторов, общая сетка нот и ударных, мягкие тембры FluidR3.', 'variants/rhythmic', 'release'),
    ('alicia', '02', 'Алисия · Экспедиция 33', 'Четыре партии: мягкий рояль/скрипка в мелодии, фортепианное сопровождение, виолончель и внутренняя скрипка. Все 169 нот и 55 тактов, исходные 3/4, 4/4, триоли и 78/58/87 BPM; повторное арпеджио упрощено.', 'variants/alicia', 'release'),
    ('turkish-march', '03', 'Турецкий марш · фортепиано', 'Моцарт: фортепиано правой и левой руки, 151 BPM. Фрагмент с каденцией; узнаваемое вступление и выключения нот сохранены.', 'variants/turkish-march', 'release'),
    ('children', '04', 'Children · Robert Miles', 'Четыре партии: основное пиано, фортепианное эхо, fretless-бас и мягкие струнные FluidR3. Вся ведущая мелодия и 345 басовых атак, 3:05 при 140 BPM. Сопровождение упрощено; два резервных канала.', 'variants/children', 'release'),
    ('greensleeves', '05', 'Greensleeves', 'Полная мелодия: флейта, скрипка и виолончель. Размер 6/8 с исходным затактом; 48 секунд и пауза перед повтором.', 'variants/greensleeves', 'release'),
    ('lumiere-stereo', '06', 'Люмьер · стерео', 'Четыре голоса, два PWM-выхода и полная композиция 3:42. Скрипка левее, гитара правее, пианино и ударные по центру.', 'variants/lumiere-stereo', 'release'),
    ('cancion-del-mariachi', '07', 'Canción del Mariachi · все ноты', '30 секунд без вступления при 126 BPM. Обе исходные нейлоновые гитары, все 1027 нот и полные аккорды. Мягкое и более тихое сопровождение подчёркивает мелодию. Восемь тональных генераторов; в этом фрагменте звучат до семи нот одновременно. Начала и выключения нот сохранены.', 'variants/cancion-del-mariachi-polyphonic', 'release'),
    ('cancion-del-mariachi-ensemble', '08', 'Mariachi · бас и ударные', 'Предыдущая сокращённая аранжировка для сравнения: ведущая и ритмическая гитары, бас и тихие ударные. 30 секунд и пауза перед повтором; часть исходных аккордовых нот опущена.', 'variants/cancion-del-mariachi', 'release'),
    ('cancion-del-mariachi-sparse', '09', 'Mariachi · соло и редкие аккорды', 'Минута музыки без вступления: все 261 исходная нота солирующей гитары. Редкий бас и короткие аккорды, тихие бас-барабан и хай-хэт из прежней аранжировки. Все гитарные ноты сохранены, общий уровень нормализован вместе с ударными.', 'variants/cancion-del-mariachi-sparse', 'release'),
]


def decode(text, limit=1024):
    result = bytearray()
    seen = set()
    eof = False
    for line in text.strip().split():
        assert not eof and re.fullmatch(r':(?:[\da-fA-F]{2})+', line), 'Invalid HEX'
        b = bytes.fromhex(line[1:])
        assert len(b) == b[0] + 5 and sum(b) % 256 == 0, 'HEX checksum/length'
        address = int.from_bytes(b[1:3], 'big')
        if b[3] == 1:
            assert b[0] == address == 0
            eof = True
            continue
        assert b[3] == 0 and address + b[0] <= limit
        assert not seen.intersection(range(address, address + b[0]))
        seen.update(range(address, address + b[0]))
        result.extend(b'\xff' * max(0, address + b[0] - len(result)))
        result[address:address + b[0]] = b[4:4 + b[0]]
    assert eof and result and len(seen) == len(result)
    return bytes(result)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def build():
    entries = []
    by_key = {}
    for id_, order, title, description, folder, status in SPECS:
        directory = MUSIC / folder
        flash = (directory / 'synth.hex').read_text(encoding='utf-8')
        ep = directory / 'eeprom.hex'
        eeprom = ep.read_text(encoding='utf-8') if ep.exists() else None
        binary = decode(flash)
        report=json.loads((directory/'build-report.json').read_text(encoding='utf-8'))
        assignments=report.get('instrumentAssignments',{})
        voices=sum(p.get('instrument')!='off' and p.get('level',0)>0 for p in assignments.values())
        entry = dict(id=id_, order=order, title=title, description=description, status=status,
                     voices=report.get('activePrimaryVoices',voices or 4),instruments=assignments,releaseTailSlots=report.get('releaseChannels',{}).get('tailSlots',0),
                     flashBytes=len(binary), eepromBytes=64 if eeprom else 0,
                     cpuHz=9600000, pwmHz=37500, sampleHz=37500, synthesisHz=18750,
                     flashSha256=digest(binary), eepromSha256=digest(decode(eeprom, 64)) if eeprom else None,
                     flashHex=flash, eepromHex=eeprom, sources=[],
                     originalPlayer=f'../ATtiny13A/Music/{folder}/player.html',
                     source=f'../ATtiny13A/Music/{folder}/synth.hex',
                     eepromSource=f'../ATtiny13A/Music/{folder}/eeprom.hex' if eeprom else None,
                     preview=f'../ATtiny13A/Music/{folder}/preview.wav' if (directory / 'preview.wav').exists() else None)
        key = (entry['flashSha256'], entry['eepromSha256'])
        entry['audioChannels']=report.get('audioChannels',1)
        if entry['audioChannels']==2:
            entry['outputs']=report['outputs']
            entry['panorama']=report['panorama']
        entry['referenceCore'] = f'../ATtiny13A/Music/{folder}/avr_core.js'
        assert key not in by_key
        by_key[key] = entry
        entries.append(entry)

    def inspect(name, content, read_sibling):
        if name.endswith('/synth.hex'):
            ep = read_sibling('eeprom.hex')
            key = (digest(decode(content.decode())), digest(decode(ep.decode(), 64)) if ep else None)
        elif name.endswith('/player.html'):
            text = content.decode('utf-8')
            flash = re.search(r'const\s+FIRMWARE_HEX\s*=\s*`(.*?)`', text, re.S)
            eeprom = re.search(r'const\s+EEPROM_HEX\s*=\s*`(.*?)`', text, re.S)
            if not flash or not flash[1].strip().startswith(':'):
                return
            key = (digest(decode(flash[1])), digest(decode(eeprom[1], 64)) if eeprom else None)
        elif name.endswith(('/synth.bin', '/new.bin')):
            ep = read_sibling('eeprom.bin')
            key = (digest(content), digest(ep) if ep else None)
        else:
            return
        assert key in by_key, f'Uncatalogued image: {name}, {key}'
        by_key[key]['sources'].append(name)

    for path in sorted(MUSIC.rglob('*')):
        if not path.is_file() or 'conversation' in path.relative_to(MUSIC).parts:
            continue
        inspect(path.relative_to(ROOT).as_posix(), path.read_bytes(),
                lambda n, p=path: p.with_name(n).read_bytes() if p.with_name(n).exists() else None)
        if path.parent.name == 'releases' and path.suffix == '.zip':
            with ZipFile(path) as z:
                assert z.testzip() is None
                for name in sorted(z.namelist()):
                    if name.endswith('/'):
                        continue
                    def sibling(n, name=name):
                        target = name.rsplit('/', 1)[0] + '/' + n
                        return z.read(target) if target in z.namelist() else None
                    inspect(path.relative_to(ROOT).as_posix() + '!/' + name, z.read(name), sibling)
    return dict(schema=1, defaultId='lumiere-stereo', entries=entries,
                sourceOnly=[dict(title='Исходный C-прототип · 2016',
                                 source='../ATtiny13A/Music/00_original/attiny13a_initial_2016.c',
                                 reason='Сохранён исходник C; готового HEX / BIN в архиве нет.')])


if __name__ == '__main__':
    catalog = build()
    text = json.dumps(catalog, ensure_ascii=False, indent=2) + '\n'
    if '--check' in sys.argv:
        assert OUTPUT.read_text(encoding='utf-8') == text, 'Run build_catalog.py to update catalog'
    else:
        OUTPUT.write_text(text, encoding='utf-8', newline='\n')
    print(f"Catalog verified: {len(catalog['entries'])} unique images; every retained HEX/BIN/HTML image covered.")

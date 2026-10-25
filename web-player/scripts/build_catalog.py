"""Verify every retained firmware image without executing embedded code."""
from pathlib import Path
from zipfile import ZipFile
import argparse
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[2]
MUSIC = ROOT / 'ATtiny13A' / 'Music'
OUTPUT = ROOT / 'web-player' / 'firmware.json'
TINY88_OUTPUT = ROOT / 'web-player' / 'firmware-attiny88.json'
SPECS = [
    ('rhythmic', '01', 'Люмьер · Экспедиция 33', 'Все 3:42 сохранённой аранжировки. Скрипка, трёхголосное пианино, отдельная гитара и ударные: пять тональных генераторов и один ударный. Добавлены внутренние тоны аккордов; F# отличается от F#m.', 'variants/rhythmic', 'release'),
    ('alicia', '02', 'Алисия · Экспедиция 33', 'Все 169 нот мелодии и 55 тактов, 2:38. Восстановлено повторное двухтоновое арпеджио пианино: 488 атак сопровождения вместе с виолончелью и внутренней скрипкой. Исходные размеры, триоли и 78/58/87 BPM сохранены; третий тон аккордов опущен. Четыре основных и два резервных голоса.', 'variants/alicia', 'release'),
    ('turkish-march', '03', 'Турецкий марш · фортепиано', 'Моцарт: 74 исходных такта 2/4 и каденция, 60,4 секунды при 151 BPM. Три фортепианных голоса: мелодия и два выбранных тона левой руки. Фрагмент продлён на четыре такта; добавлено 37 внутренних нот аккордов. Полная исходная полифония сокращена.', 'variants/turkish-march', 'release'),
    ('children', '04', 'Children · Robert Miles', 'Продолжено с 3:05 до 4:02 при 140 BPM. Все 256 нот ведущего пиано, 458 басовых атак и ещё 448 поздних струнных нот из источника. Пять музыкальных партий по ходу пьесы, четыре основных голоса и два резервных. Эхо, ранние струнные и исходная полифония сокращены.', 'variants/children', 'release'),
    ('greensleeves', '05', 'Greensleeves', 'Все 235 нот четырёх исходных партий: флейта, скрипка, восстановленный кларнет и виолончель. Все начала и выключения нот сохранены. Полные 48 секунд, исходные 6/8 и затакт; уровень PWM нормализован.', 'variants/greensleeves', 'release'),
    ('lumiere-stereo', '06', 'Люмьер · стерео', 'Пять тональных голосов и ударные, два PWM-выхода, все 3:42 аранжировки. Добавлены полные качества аккордов: скрипка левее, отдельная гитара правее, трёхголосное пианино и ударные по центру.', 'variants/lumiere-stereo', 'release'),
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


def build_attiny88_legacy():
    """Keep the shipped comparison catalog pinned to its actual retained ROMs."""
    catalog=json.loads(TINY88_OUTPUT.with_name('firmware-attiny88-legacy.json').read_text(encoding='utf-8'))
    for entry in catalog['entries']:
        directory=ROOT/'ATtiny88/Music/variants'/Path(entry['source']).parent.name
        assert digest((directory/'synth.bin').read_bytes())==entry['flashSha256']
        assert digest((directory/'eeprom.bin').read_bytes())==entry['eepromSha256']
        assert decode(entry['flashHex'],8192)==(directory/'synth.bin').read_bytes()
        assert decode(entry['eepromHex'],64)==(directory/'eeprom.bin').read_bytes()
    return catalog


def build_attiny88():
    """Publish only fully audited UM88 images, with one code image for all songs."""
    catalog=build_attiny88_legacy()
    common_hash=None
    for entry in catalog['entries']:
        directory=ROOT/'ATtiny88/Music/universal/songs'/Path(entry['source']).parent.name
        report=json.loads((directory/'build-report.json').read_text(encoding='utf-8'))
        verification=json.loads((directory/'verification.json').read_text(encoding='utf-8'))
        binary=(directory/'synth.bin').read_bytes();ep=(directory/'eeprom.bin').read_bytes()
        flash=(directory/'synth.hex').read_text(encoding='utf-8');eeprom=(directory/'eeprom.hex').read_text(encoding='utf-8')
        assert report['engine']=='UM88' and report['backend']=='avr-asm'
        assert report['cpuHz']==8000000,'The published internal-RC board profile is 8 MHz; keep custom-clock images separate'
        assert decode(flash,8192)==binary and decode(eeprom,64)==ep
        assert report['flashSha256']==verification['flashSha256']==digest(binary)
        assert report['eepromSha256']==verification['eepromSha256']==digest(ep)
        assert verification['allControlFramesMatch'] and verification['allTonalMixesMatch']
        assert verification['fifoUnderruns']==verification['lostInterrupts']==0
        assert report['engineSha256']==verification['engineSha256']==digest(binary[:report['engineBytes']])
        common_hash=common_hash or report['engineSha256'];assert common_hash==report['engineSha256']
        relative=directory.relative_to(ROOT).as_posix()
        entry.update(firmwareEngine='UM88',flashBytes=len(binary),flashSha256=digest(binary),eepromSha256=digest(ep),
                     cpuHz=report['cpuHz'],pwmHz=report['pwmHz'],sampleHz=report['pwmHz'],synthesisHz=report['synthesisHz'],
                     flashHex=flash,eepromHex=eeprom,source=f'../{relative}/synth.hex',eepromSource=f'../{relative}/eeprom.hex',
                     sourceAssembly='../ATtiny88/Music/universal/render-avr.S',buildReport=f'../{relative}/build-report.json',
                     verificationSource=f'../{relative}/verification.json',
                     sources=[f'{relative}/{name}' for name in ('synth.hex','synth.bin','eeprom.hex','eeprom.bin','score.json')])
    catalog['hardwareProfile'].update(firmwareEngine='UM88',cpuHz=catalog['entries'][0]['cpuHz'],
                                     pwmHz=catalog['entries'][0]['pwmHz'],synthesisHz=catalog['entries'][0]['synthesisHz'],
                                     readme='../ATtiny88/Music/universal/README.md')
    return catalog


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=('attiny13a', 'attiny88'), default='attiny13a')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--legacy', action='store_true', help='Retain the specialized ATtiny88 comparison catalog')
    args = parser.parse_args()
    catalog = (build_attiny88_legacy() if args.legacy else build_attiny88()) if args.target == 'attiny88' else build()
    output = (TINY88_OUTPUT.with_name('firmware-attiny88-legacy.json') if args.legacy else TINY88_OUTPUT) if args.target == 'attiny88' else OUTPUT
    text = json.dumps(catalog, ensure_ascii=False, indent=2) + '\n'
    if args.check:
        assert output.read_text(encoding='utf-8') == text, f'Run build_catalog.py --target {args.target} to update catalog'
    else:
        output.write_text(text, encoding='utf-8', newline='\n')
    print(f"{args.target} catalog verified: {len(catalog['entries'])} unique images; every retained target image covered.")

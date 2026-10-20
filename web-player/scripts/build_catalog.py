"""Discover firmware in the retained archive without executing archive code."""
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
    ('four-voice', '01', 'Четыре голоса', 'Первый полный синтезатор: скрипка, пианино, гитара и ударные.', 'snapshots/attiny13-synth', 'release'),
    ('spectral', '02', 'Спектр по регистрам', 'Тембр и затухание зависят от высоты ноты.', 'snapshots/attiny13-spectral', 'release'),
    ('acoustic', '03', 'Акустические тембры', 'Гармоники настроены по инструментальным сэмплам.', 'snapshots/attiny13-acoustic', 'release'),
    ('bipolar', '04', 'Биполярный синтез', 'Общий генератор гармоник и смешивание вокруг PWM 128.', 'snapshots/attiny13-refined', 'release'),
    ('measured', '05', 'Измеренные спектры', 'Компактные таблицы волн и приближения измеренных огибающих.', 'snapshots/attiny13-real-instruments/firmware', 'release'),
    ('final', '06', 'EEPROM-волны и note-off', 'Табличные тембры, независимый note-off и переходы attack / sustain.', 'final/attiny13a_synth_release', 'release'),
    ('fluid-violin', '07', 'Скрипка FluidR3', 'Спектр FluidR3 GM, плавная атака, связные ноты и мягкое затухание.', 'variants/fluid-violin', 'release'),
    ('fluid-instruments', '08', 'Мягкие тембры FluidR3', 'Мягкие спектры скрипки, пианино и гитары; огибающие и ударные по FluidR3 GM.', 'variants/fluid-instruments', 'release'),
    ('foreground-pwm', '09', 'Синтез в основном цикле', 'Мягкие тембры FluidR3; прерывание выводит готовый PWM за 12 тактов.', 'variants/foreground-pwm', 'release'),
    ('smoke', 'T1', 'Тестовая мелодия', 'Короткая проверочная партитура C4–D4–E4; три повтора секции.', 'snapshots/attiny13-final/alternate-test', 'experimental'),
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
        entry = dict(id=id_, order=order, title=title, description=description, status=status,
                     flashBytes=len(binary), eepromBytes=64 if eeprom else 0,
                     cpuHz=9600000, pwmHz=37500, sampleHz=18750 if eeprom else 37500,
                     flashSha256=digest(binary), eepromSha256=digest(decode(eeprom, 64)) if eeprom else None,
                     flashHex=flash, eepromHex=eeprom, sources=[],
                     originalPlayer=f'../ATtiny13A/Music/{folder}/player.html',
                     source=f'../ATtiny13A/Music/{folder}/synth.hex',
                     eepromSource=f'../ATtiny13A/Music/{folder}/eeprom.hex' if eeprom else None,
                     preview=f'../ATtiny13A/Music/{folder}/preview.wav' if (directory / 'preview.wav').exists() else None)
        key = (entry['flashSha256'], entry['eepromSha256'])
        if id_ == 'foreground-pwm':
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
    return dict(schema=1, defaultId='foreground-pwm', entries=entries,
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
    print(f"Catalog verified: {len(catalog['entries'])} unique images, all retained HEX/BIN/HTML and 6 ZIP releases covered.")

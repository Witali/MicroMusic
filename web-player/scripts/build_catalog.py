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
TINY88_BOARD_OUTPUT = ROOT / 'web-player' / 'firmware-attiny88-16mhz.json'
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


def build_attiny88():
    """Catalog the real port images; retain music metadata from their verified sources."""
    music = ROOT / 'ATtiny88' / 'Music'
    variant_names = {Path(spec[4]).name for spec in SPECS}
    assert {p.name for p in (music / 'variants').iterdir() if p.is_dir()} == variant_names
    entries = []
    seen = set()
    for id_, order, title, description, folder, status in SPECS:
        directory = music / folder
        source_directory = MUSIC / folder
        report = json.loads((directory / 'build-report.json').read_text(encoding='utf-8'))
        source_report = json.loads((source_directory / 'build-report.json').read_text(encoding='utf-8'))
        verification = json.loads((directory / 'verification.json').read_text(encoding='utf-8'))
        flash = (directory / 'synth.hex').read_text(encoding='utf-8')
        eeprom = (directory / 'eeprom.hex').read_text(encoding='utf-8')
        binary, ep_binary = decode(flash, 8192), decode(eeprom, 64)
        flash_hash, ep_hash = digest(binary), digest(ep_binary)
        assert binary == (directory / 'synth.bin').read_bytes(), f'{folder}: Flash HEX/BIN mismatch'
        assert ep_binary == (directory / 'eeprom.bin').read_bytes(), f'{folder}: EEPROM HEX/BIN mismatch'
        assert report['target'] == verification['target'] == 'ATtiny88'
        assert report['sourceVariant'] == verification['variant'] == directory.name
        assert report['sourceFolder'] == source_directory.relative_to(ROOT).as_posix()
        assert report['flashBytes'] == len(binary) <= 8192
        assert report['eepromBytes'] == len(ep_binary) == 64
        assert report['flashSha256'] == verification['port']['flashSha256'] == flash_hash
        assert report['eepromSha256'] == verification['port']['eepromSha256'] == ep_hash
        assert report['sourceFlashSha256'] == source_report['flashSha256'] == verification['original']['flashSha256']
        assert report['sourceEepromSha256'] == source_report['eepromSha256'] == verification['original']['eepromSha256']
        assert digest(decode((source_directory / 'synth.hex').read_text(encoding='utf-8'))) == report['sourceFlashSha256']
        assert digest(decode((source_directory / 'eeprom.hex').read_text(encoding='utf-8'), 64)) == report['sourceEepromSha256']
        for source_name, source_hash in report['sourceInputs'].items():
            assert digest((ROOT / source_name).read_bytes()) == source_hash, f'Stale port input: {source_name}'
        assert report['musicalDataVerified'] is True
        assert verification['allMusicalStatesMatch'] is True
        assert verification['allMusicalCommandsMatch'] is True
        assert verification['tables']['allOtherMusicTableBytesIdentical'] is True
        assert verification['tables']['allWavetablesIdentical'] is True
        for field in ('controlTicks', 'firstRestartControlTick', 'snapshotSha256', 'commandSha256'):
            assert verification['original'][field] == verification['port'][field], f'{folder}: {field}'
        for field in ('fifoUnderruns', 'lostTimerEvents', 'lostWorkEvents'):
            assert verification['port'][field] == 0, f'{folder}: {field}'
        assert report['cpuHz'] == 8000000 and report['pwmHz'] == 31250 and report['synthesisHz'] == 15625
        assert report['memory']['flashCapacity'] == 8192 and report['memory']['eepromCapacity'] == 64
        assert report['memory']['sramStart'] == 0x100 and report['memory']['sramEnd'] == 0x2ff
        assert report['hardware']['timer'] == 'Timer1' and report['hardware']['mode'] == 5
        assert report['hardware']['monoPin'] == 'PB2/OC1B'
        assert report['hardware']['stereoLeftPin'] == 'PB1/OC1A'
        assert report['hardware']['stereoRightPin'] == 'PB2/OC1B'
        assert report['requiredFuses'] == dict(low='0xEE', high='0xDF', extended='0xFF')
        assert (flash_hash, ep_hash) not in seen, f'Duplicate port image: {folder}'
        seen.add((flash_hash, ep_hash))
        assignments = source_report.get('instrumentAssignments', {})
        voices = sum(p.get('instrument') != 'off' and p.get('level', 0) > 0 for p in assignments.values())
        channels = report['audioChannels']
        assert channels == source_report.get('audioChannels', 1) == verification['port']['channels']
        relative = directory.relative_to(ROOT).as_posix()
        outputs = [dict(channel='R' if channels == 2 else 'mono', pin='PB2', compare='OC1B',
                        register='OCR1B', packagePin=16)]
        if channels == 2:
            outputs.insert(0, dict(channel='L', pin='PB1', compare='OC1A', register='OCR1A', packagePin=15))
        entry = dict(id=id_, order=order, title=title, description=description, status=status,
                     device='attiny88', voices=source_report.get('activePrimaryVoices', voices or 4),
                     instruments=assignments,
                     releaseTailSlots=source_report.get('releaseChannels', {}).get('tailSlots', 0),
                     flashCapacity=8192, eepromCapacity=64, sramCapacity=512,
                     flashBytes=len(binary), eepromBytes=len(ep_binary),
                     cpuHz=8000000, pwmHz=31250, sampleHz=31250, synthesisHz=15625,
                     flashSha256=flash_hash, eepromSha256=ep_hash, flashHex=flash, eepromHex=eeprom,
                     audioChannels=channels, outputs=outputs,
                     source=f'../{relative}/synth.hex', eepromSource=f'../{relative}/eeprom.hex',
                     sourceAssembly=f'../{relative}/synth.S', buildReport=f'../{relative}/build-report.json',
                     verificationSource=f'../{relative}/verification.json',
                     sources=[f'{relative}/{name}' for name in ('synth.hex', 'synth.bin', 'eeprom.hex', 'eeprom.bin')])
        if channels == 2:
            entry['panorama'] = source_report['panorama']
        entries.append(entry)
    return dict(schema=1, device='attiny88', defaultId='lumiere-stereo', entries=entries, sourceOnly=[],
                hardwareProfile=dict(name='ATtiny88', flashCapacity=8192, eepromCapacity=64, sramCapacity=512,
                                     cpuHz=8000000, pwmHz=31250, synthesisHz=15625,
                                     requiredFuses=dict(low='0xEE', high='0xDF', extended='0xFF'),
                                     outputs=dict(mono=dict(pin='PB2/OC1B', pdip28=16),
                                                  stereoLeft=dict(pin='PB1/OC1A', pdip28=15),
                                                  stereoRight=dict(pin='PB2/OC1B', pdip28=16)),
                                     readme='../ATtiny88/Music/README.txt',
                                     hardwareReview='../ATtiny88/Music/HARDWARE_REVIEW_RU.md'))


def build_attiny88_micronucleus():
    """USB-only board images: all musical data and timbres reside in Flash."""
    catalog = build_attiny88()
    entries = []
    for previous in catalog['entries']:
        name = Path(previous['source']).parent.name
        directory = ROOT / 'ATtiny88/Music/variants-micronucleus' / name
        report = json.loads((directory / 'build-report.json').read_text(encoding='utf-8'))
        verification = json.loads((directory / 'verification.json').read_text(encoding='utf-8'))
        flash = (directory / 'synth.hex').read_text(encoding='utf-8')
        binary = decode(flash, 6012)
        bank = (directory / 'wave-bank.bin').read_bytes()
        assert binary == (directory / 'synth.bin').read_bytes()
        assert report['target'] == verification['target'] == 'ATtiny88'
        assert report['board'] == verification['board'] == 'mh-et-live-16mhz'
        assert report['sourceVariant'] == verification['variant'] == name
        assert report['cpuHz'] == 16000000 and report['pwmHz'] == 62500 and report['synthesisHz'] == 31250
        assert report['flashBytes'] == len(binary) <= report['applicationFlashLimit'] == 6012
        assert report['eepromBytes'] == 0 and report['eepromSha256'] is None
        assert report['requiredFuses'] is None
        assert report['flashSha256'] == verification['port']['flashSha256'] == digest(binary)
        storage = report['wavetableStorage']
        assert storage['space'] == 'flash' and storage['bytes'] == len(bank) == 64
        assert storage['address'] % 256 == 0
        assert binary[storage['address']:storage['address'] + 64] == bank
        assert storage['sha256'] == digest(bank)
        for source_name, source_hash in report['sourceInputs'].items():
            assert digest((ROOT / source_name).read_bytes()) == source_hash, f'Stale board input: {source_name}'
        assert report['musicalDataVerified'] is True
        assert verification['allMusicalStatesMatch'] and verification['allMusicalCommandsMatch']
        assert verification['tables']['allOtherMusicTableBytesIdentical']
        assert verification['tables']['allWavetablesIdentical']
        for field in ('controlTicks', 'firstRestartControlTick', 'snapshotSha256', 'commandSha256'):
            assert verification['original'][field] == verification['port'][field], f'{name}: {field}'
        for field in ('fifoUnderruns', 'lostTimerEvents', 'lostWorkEvents'):
            assert verification['port'][field] == 0, f'{name}: {field}'
        assert verification['port']['eepromSha256'] is None
        assert report['sourceFlashSha256'] == verification['original']['flashSha256']
        assert report['sourceEepromSha256'] == verification['original']['eepromSha256']
        relative = directory.relative_to(ROOT).as_posix()
        outputs = [dict(channel=output['channel'], pin=output['pin'], compare=output['compare'],
                        register=output['register'], boardPin='D9' if output['channel'] == 'L' else 'D10')
                   for output in previous['outputs']]
        entry = dict(previous, board='mh-et-live-16mhz', uploadProtocol='micronucleus',
                     applicationFlashLimit=6012, cpuHz=16000000, pwmHz=62500, sampleHz=62500, synthesisHz=31250,
                     flashBytes=len(binary), flashHex=flash, flashSha256=digest(binary),
                     eepromBytes=0, eepromHex=None, eepromSha256=None, eepromSource=None,
                     wavetableStorage=storage, outputs=outputs,
                     source=f'../{relative}/synth.hex', sourceAssembly=f'../{relative}/synth.S',
                     buildReport=f'../{relative}/build-report.json', verificationSource=f'../{relative}/verification.json',
                     sources=[f'{relative}/{file}' for file in ('synth.hex', 'synth.bin', 'wave-bank.bin')])
        entries.append(entry)
    profile = dict(catalog['hardwareProfile'], name='MH-ET LIVE Tiny88', board='mh-et-live-16mhz',
                   cpuHz=16000000, pwmHz=62500, synthesisHz=31250, applicationFlashLimit=6012,
                   oscillator='external', bootloader='Micronucleus', uploadProtocol='micronucleus',
                   requiredFuses=None, eepromRequired=False, readme='../ATtiny88/Music/MH_ET_LIVE_RU.md',
                   outputs=dict(mono=dict(pin='PB2/OC1B', boardPin='D10'),
                                stereoLeft=dict(pin='PB1/OC1A', boardPin='D9'),
                                stereoRight=dict(pin='PB2/OC1B', boardPin='D10')))
    return dict(catalog, board='mh-et-live-16mhz', entries=entries, hardwareProfile=profile)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=('attiny13a', 'attiny88'), default='attiny13a')
    parser.add_argument('--board', choices=('bare-8mhz', 'mh-et-live-16mhz'), default='bare-8mhz')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.board != 'bare-8mhz' and args.target != 'attiny88':
        parser.error('--board mh-et-live-16mhz requires --target attiny88')
    board = args.board == 'mh-et-live-16mhz'
    catalog = build_attiny88_micronucleus() if board else build_attiny88() if args.target == 'attiny88' else build()
    output = TINY88_BOARD_OUTPUT if board else TINY88_OUTPUT if args.target == 'attiny88' else OUTPUT
    text = json.dumps(catalog, ensure_ascii=False, indent=2) + '\n'
    if args.check:
        assert output.read_text(encoding='utf-8') == text, f'Run build_catalog.py --target {args.target} to update catalog'
    else:
        output.write_text(text, encoding='utf-8', newline='\n')
    print(f"{args.target} catalog verified: {len(catalog['entries'])} unique images; every retained target image covered.")

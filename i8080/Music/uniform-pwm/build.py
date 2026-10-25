#!/usr/bin/env python3
"""Reconstruct two ROM scores and explicitly opt in to the 8080 PWM backend."""
from pathlib import Path
from functools import lru_cache
import argparse
import hashlib
import importlib.util
import json
import math

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
spec = importlib.util.spec_from_file_location('voice_build', REPO / 'i8080/Sound/dual-crc-voice/build.py')
voice = importlib.util.module_from_spec(spec)
spec.loader.exec_module(voice)
Code = voice.Code
BASES = {'uniform26': ('8085bef215f1108d9009082689554ffba36985b4717fb620791906ad49a847d0', 539),
         'balanced27': ('33da178192bd2c464c30045b995e4e25cd4b14da3f7ff1107b50b0bf759a094a', 523)}


def save(path, data, check=False):
    data = data.encode('utf-8') if isinstance(data, str) else bytes(data)
    if check:
        actual = path.read_bytes()
        if isinstance(data, bytes) and path.suffix in ('.json', '.asm', '.h'):
            actual = actual.replace(b'\r\n', b'\n')
        assert actual == data, f'Stale generated file: {path.name}'
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def source_score(name):
    digest, group = BASES[name]
    rom = (REPO / f'i8080/Emulator/tests/roms/{name}.bin').read_bytes()
    assert hashlib.sha256(rom).hexdigest() == digest
    word = lambda at: int.from_bytes(rom[at:at+2], 'little')

    def step(at, pair):
        block = rom[at:at+8]
        low, high, add, adc = {'bc': (0x0e, 0x06, 0x81, 0x88), 'de': (0x1e, 0x16, 0x83, 0x8a)}[pair]
        if block == bytes([high, 0x80, low, 0, 0xeb, 0xeb, 0, 0]):
            return None
        assert block[0] == block[4] == 0x3e and block[2] == add and block[6] == adc, (name, hex(at), block.hex())
        assert block[3] == (0x4f if pair == 'bc' else 0x5f)
        assert block[7] == (0x47 if pair == 'bc' else 0x57)
        return block[1] | block[5] << 8

    cursor, notes = word(12), []
    while True:
        bc, de, repeat, following = [word(cursor + n) for n in (0, 2, 4, 6)]
        assert de == bc - 12 and repeat == bc - 22
        assert rom[bc+8:bc+12] == bytes([0x7c, 0x26, 0x2d, 0xe9])
        assert rom[de+8:de+12] == bytes([0x7c, 0x26, 0x2f, 0xe9])
        assert rom[repeat:repeat+6] == bytes([0x3b] * 6)
        if not notes or notes[-1]['source_pc'] != f'{bc:04X}':
            inc = [step(bc, 'bc'), step(de, 'de')]
            notes.append({'source_pc': f'{bc:04X}', 'steps': inc, 'groups': 0,
                          'group_t': group - 2 * inc.count(None)})
        notes[-1]['groups'] += 256
        cursor += 8
        if rom[following:following+2] == bytes([0xf3, 0x76]):
            break
        assert following == word(cursor) - 16
    for note in notes:
        note['duration_t'] = note['groups'] * note['group_t'] - note['groups'] // 16
    assert len(notes) == 325
    return {'name': name, 'original_sha256': digest, 'source': '../../Emulator/tests/roms/' + name + '.bin',
            'initial_phases': [0, 0], 'initial_level': 0, 'notes': notes}


@lru_cache(None)
def delays(ticks, scratch_h=False):
    if ticks == 0:
        return ()
    options = []
    for cost, text, op in [(4, 'NOP', (0,)), (5, 'MOV A,A', (0x7f,))] + ([(7, 'MVI H,000H', (0x26, 0))] if scratch_h else []):
        if ticks >= cost:
            rest = delays(ticks-cost, scratch_h)
            if rest is not None:
                options.append(((cost, text, op, None, scratch_h),) + rest)
    return min(options, key=lambda seq: sum(len(x[2]) for x in seq)) if options else None


def ins(cost, text, *op, target=None, scratch=False):
    return (cost, text, op, target, scratch)


def jump(text, target, op=0xc3):
    return ins(10, f'{text} {target}', op, 0, 0, target=target)


def di_options(actions, start, done, width, permit_future):
    """Insert the falling edge on the requested T-state, preserving branch flags."""
    if done:
        return [(list(actions), start + sum(x[0] for x in actions), True)]
    result, elapsed = [], start
    for index, action in enumerate(actions):
        gap = width - elapsed
        fill = delays(gap, action[4]) if gap >= 0 else None
        if fill is not None:
            seq = list(actions[:index]) + list(fill) + [ins(4, 'DI', 0xf3)] + list(actions[index:])
            result.append((seq, start + sum(x[0] for x in seq), True))
        elapsed += action[0]
    if permit_future and elapsed <= width:
        result.append((list(actions), elapsed, False))
    return result


def schedule(node, start, done, width, period):
    actions, children = node
    candidates = []
    if children:
        for seq, now, finished in di_options(actions, start, done, width, True):
            planned = [schedule(child, now, finished, width, period) for _, child in children]
            if all(part is not None for part in planned):
                result = (seq, [(children[i][0], planned[i]) for i in range(len(planned))])
                candidates.append(result)
    else:
        # The last two operations overwrite H then branch; H is disposable here.
        for seq, now, finished in di_options(actions, start, done, width, False):
            falling = next((i for i, op in enumerate(seq) if op[1] == 'DI'), -1)
            split = max(len(seq)-2, falling+1)
            scratch = split == len(seq)-2 or seq[-1][1] == 'HLT'
            fill = delays(period-now, scratch) if now <= period else None
            if finished and fill is not None:
                candidates.append((seq[:split] + list(fill) + seq[split:], []))
    if not candidates:
        return None
    def size(part):
        return sum(len(x[2]) for x in part[0]) + sum(size(child) for _, child in part[1])
    return min(candidates, key=size)


def tail(level, page):
    return [ins(7, f'MVI L,{level*16:03X}H', 0x2e, level*16, scratch=True),
            ins(7, f'MVI H,{page:03X}H', 0x26, page, scratch=True), ins(5, 'PCHL', 0xe9)]


def program(phase, level, period, page=0x10):
    name = f'P{phase}_L{level}'
    body = name + '_BODY'
    head = [ins(4, 'EI' if level else 'DI', 0xfb if level else 0xf3), jump('JMP', body)]
    if phase < 2:
        reset = name + '_RESET'
        prefix = [ins(10, 'POP H', 0xe1, scratch=True), ins(5, 'INR H', 0x24), jump('JZ', reset, 0xca)]
        pair = 'B' if phase == 0 else 'D'
        normal = [ins(5, 'DCR H', 0x25), ins(10, f'DAD {pair}', 0x09 if phase == 0 else 0x19),
                  ins(5, f'MOV {pair},H', 0x44 if phase == 0 else 0x54),
                  ins(5, f'MOV {"C" if phase == 0 else "E"},L', 0x4d if phase == 0 else 0x5d, scratch=True)]
        reset_ops = [ins(10, f'LXI {pair},08000H', 0x01 if phase == 0 else 0x11, 0, 0x80, scratch=True)]
        tree = (prefix, [(None, (normal + tail(level, page+phase+1), [])),
                         (reset, (reset_ops + tail(level, page+phase+1), []))])
    elif phase == 2:
        record, eof = name + '_RECORD', name + '_EOF'
        prefix = [ins(5, 'DCR A', 0x3d, scratch=True), jump('JZ', record, 0xca)]
        rewind = [ins(10, 'LXI H,0FFFCH', 0x21, 0xfc, 0xff, scratch=True),
                  ins(10, 'DAD SP', 0x39), ins(5, 'SPHL', 0xf9)]
        read = [ins(10, 'POP H', 0xe1, scratch=True), ins(5, 'MOV A,L', 0x7d),
                ins(4, 'ORA A', 0xb7, scratch=True), jump('JZ', eof, 0xca)]
        tree = (prefix, [(None, (rewind + tail(level, page+3), [])),
                         (record, (read, [(None, (tail(level, page+3), [])),
                                         (eof, (tail(level, page+4), []))]))])
    elif phase == 3:
        mix = [ins(5, 'MOV H,A', 0x67, scratch=True), ins(5, 'MOV A,B', 0x78),
               ins(4, 'ADD D', 0x82), ins(4, 'RAR', 0x1f), ins(7, 'ANI 0F0H', 0xe6, 0xf0),
               ins(5, 'MOV L,A', 0x6f), ins(5, 'MOV A,H', 0x7c),
               ins(7, f'MVI H,{page:03X}H', 0x26, page, scratch=True), ins(5, 'PCHL', 0xe9)]
        tree = (mix, [])
    else:
        # A final fourth pulse, with a full last period and a low output at HLT.
        tree = ([ins(7, 'MVI H,000H', 0x26, 0, scratch=True), ins(7, 'HLT', 0x76)], [])

    options = []
    for rest, ht, hd in di_options(head[1:], 4, level == 0, level*4, True):
        hseq = [head[0]] + rest
        if sum(len(x[2]) for x in hseq) > 16:
            continue
        planned = schedule(tree, ht, hd, level*4, period)
        if planned:
            options.append((hseq, planned))
    if not options:
        return None
    hseq, planned = options[0]
    return name, body, hseq, planned


def emit_actions(code, actions):
    for _, text, op, target, _ in actions:
        code.emit(text, *op)
        if target:
            code.fixups.append((len(code.data)-2, target))


def emit_tree(code, tree):
    actions, children = tree
    emit_actions(code, actions)
    for label, child in children:
        if label:
            code.label(label)
        emit_tree(code, child)


def plan_score(source, period):
    elapsed, emitted, chunks, notes = 0, 0, [], []
    for note in source['notes']:
        elapsed += note['duration_t']
        count = (elapsed + period*2) // (period*4) - emitted
        emitted += count
        ratio = period*4 / (note['duration_t']/note['groups'])
        steps = [None if value is None else round(value*ratio) for value in note['steps']]
        assert all(value is None or 0 < value < 0xff00 for value in steps)
        notes.append({'frames': count, 'steps': steps, 'duration_error_t': emitted*period*4-elapsed,
                      'pitch_error_cents': [None if old is None else 1200*math.log2(new/(old*ratio))
                                            for old, new in zip(note['steps'], steps)]})
        while count:
            n = min(255, count)
            chunks.append({'frames': n, 'steps': steps})
            count -= n
    return chunks, notes


def build_rom(source, period, check):
    programs = [program(phase, level, period) for phase in range(5) for level in range(16)]
    assert all(programs), period
    chunks, notes = plan_score(source, period)
    head = Code(0)
    head.emit('DI', 0xf3)
    head.emit('LXI B,00000H', 0x01, 0, 0)
    head.emit('LXI D,00000H', 0x11, 0, 0)
    head.word('LXI SP,SCORE', 0x31, 'SCORE')
    head.emit(f'MVI A,{chunks[0]["frames"]:03X}H', 0x3e, chunks[0]['frames'])
    head.emit('LXI H,01000H', 0x21, 0, 0x10)
    head.emit('PCHL', 0xe9)
    codes, cursor = [head], 0x1500
    for index, (name, body, entry, planned) in enumerate(programs):
        phase, level = divmod(index, 16)
        slot = Code((0x10+phase)*256+level*16)
        slot.label(name)
        emit_actions(slot, entry)
        assert len(slot.data) <= 16
        code = Code(cursor)
        code.label(body)
        emit_tree(code, planned)
        codes += [slot, code]
        cursor = code.pc
    score_at = (cursor+1) & ~1
    data = bytearray()
    for i, chunk in enumerate(chunks):
        for value in chunk['steps']:
            data += (0xff00 if value is None else value).to_bytes(2, 'little')
        following = chunks[i+1]['frames'] if i+1 < len(chunks) else 0
        data += bytes([following, 0])
    assert score_at + len(data) <= 32768, (score_at, len(data))
    labels = {key: value for code in codes for key, value in code.labels.items()} | {'SCORE': score_at}
    rom = bytearray([0xff]*32768)
    for code in codes:
        code.resolve(labels)
        rom[code.origin:code.pc] = code.data
    rom[score_at:score_at+len(data)] = data
    name = source['name'] + f'-pwm{period}'
    meta = {'name': name, 'backend': 'i8080-asm', 'cpu_hz': 3500000, 'period_t': period,
            'carrier_hz': 3500000/period, 'frame_t': period*4, 'width_t': '4*level; zero is silent',
            'levels': 16, 'bytes': len(rom), 'sha256': hashlib.sha256(rom).hexdigest(),
            'source_sha256': source['original_sha256'], 'score_at': score_at, 'score_bytes': len(data),
            'used_bytes': score_at+len(data), 'chunks': chunks, 'notes': notes,
            'labels': {key: f'{value:04X}' for key, value in labels.items()},
            'frames': sum(chunk['frames'] for chunk in chunks), 'pulses_per_frame': 4,
            'hardware_tested': False, 'active_interrupts_supported': False}
    save(ROOT / (name+'.bin'), rom, check)
    save(ROOT / (name+'.hex'), voice.hex_image(rom), check)
    asm = ['; Intel 8080 only; generated by build.py --backend i8080-asm --architecture i8080 --enable-asm.',
           '; Bare ROM ABI: BC/DE phases, A counter, HL scratch/dispatch, SP read-only score cursor.',
           '; INTE is the audio output. INT must be inactive; no WAIT or HOLD. No RAM writes.',
           '; Portable arithmetic fallback: music.c / mm_music_frame_c; default backend is C.']
    for code in codes:
        asm += ['', f'    ORG {code.origin:05X}H'] + code.source
    asm += ['', f'    ORG {score_at:05X}H', 'SCORE:']
    for at in range(0, len(data), 6):
        values = [int.from_bytes(data[at+n:at+n+2], 'little') for n in (0, 2, 4)]
        asm.append('    DW ' + ','.join(f'{value:05X}H' for value in values))
    save(ROOT / (name+'.asm'), '\n'.join(asm)+'\n', check)
    save(ROOT / (name+'.json'), json.dumps(meta, indent=2)+'\n', check)
    print(f'{name}: {meta["carrier_hz"]:.3f} Hz, {meta["frames"]} frames, {meta["used_bytes"]}/32768 bytes')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', choices=['c', 'i8080-asm'], default='c')
    parser.add_argument('--architecture', default='portable')
    parser.add_argument('--enable-asm', action='store_true')
    parser.add_argument('--period', type=int, default=108)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--search-periods', action='store_true')
    args = parser.parse_args()
    if args.backend == 'i8080-asm' and (args.architecture != 'i8080' or not args.enable_asm):
        parser.error('Assembly requires --architecture i8080 --enable-asm')
    if args.search_periods:
        for period in range(98, 121):
            missing = [(p,l) for p in range(5) for l in range(16) if program(p,l,period) is None]
            print(period, 'PASS' if not missing else missing)
        return
    sources = [source_score(name) for name in BASES]
    source = {'format': 1, 'cpu_hz': 3500000, 'provenance': '../../Emulator/SOURCE.json', 'tunes': sources}
    save(ROOT / 'source-score.json', json.dumps(source, indent=2)+'\n', args.check)
    if args.backend == 'i8080-asm':
        for item in sources:
            build_rom(item, args.period, args.check)
    else:
        print('Portable C backend selected: music.c; source-score.json verified/generated. Assembly was not selected.')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Build a ROM-only 8080 voice engine, two uniform 109T pulses per PCM4 sample."""
from pathlib import Path
from functools import lru_cache
import argparse
import hashlib
import importlib.util
import json

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('legacy', ROOT / '../dual-crc-voice/build.py')
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)
Code = legacy.Code
PERIOD, PAGE = 109, 0x3c
NAME = 'dualcrc-voice32'


def save(name, data, check, root=ROOT):
    data = data.encode('utf-8') if isinstance(data, str) else bytes(data)
    if check:
        actual = (root / name).read_bytes()
        if Path(name).suffix in ('.asm', '.json'):
            actual = actual.replace(b'\r\n', b'\n')
        assert actual == data, f'Stale: {name}'
    else:
        (root / name).write_bytes(data)


def ins(t, text, *op, target=None):
    return t, text, op, target


def jump(text, target, op):
    return ins(10, f'{text} {target}', op, 0, 0, target=target)


@lru_cache(None)
def delay(t):
    seq = legacy.padding(t) if t >= 0 else None
    return None if seq is None else tuple(ins(4 if op == 0 else 5, text, op) for op, text in seq)


def tree_size(tree):
    return sum(len(op[2]) for op in tree[0]) + sum(tree_size(child) for _, child in tree[1])


def plan(tree, width):
    """Place three remaining edges at fixed deadlines on EVERY branch.

    Instructions cannot cross an edge. NOP/MOV A,A preserve all live registers
    and flags. The final PCHL costs 5T plus the destination table's 10T JMP.
    """
    edges = ((width, ins(4, 'DI', 0xf3)), (PERIOD, ins(4, 'EI', 0xfb)),
             (PERIOD + width, ins(4, 'DI', 0xf3)))

    @lru_cache(None)
    def visit(actions, children, now, edge):
        options = []
        if not actions:
            if children:
                parts = tuple((label, visit(*child, now, edge)) for label, child in children)
                if all(child is not None for _, child in parts):
                    options.append(((), parts))
        elif len(actions) == 1 and not children:
            # Terminal PCHL/HLT: padding belongs before the transfer.
            action = actions[0]
            fill = delay(2*PERIOD - now - action[0]) if edge == len(edges) else None
            if fill is not None:
                options.append((fill + actions, ()))
        else:
            action = actions[0]
            deadline = edges[edge][0] if edge < len(edges) else 2*PERIOD
            if now + action[0] <= deadline:
                rest = visit(actions[1:], children, now + action[0], edge)
                if rest is not None:
                    options.append(((action,) + rest[0], rest[1]))
        # After a conditional jump, each child must own its remaining edges.
        # Shared instructions here would be skipped by the taken branch.
        if edge < len(edges) and (actions or not children):
            deadline, op = edges[edge]
            fill = delay(deadline - now)
            if fill is not None:
                rest = visit(actions, children, deadline + op[0], edge + 1)
                if rest is not None:
                    options.append((fill + (op,) + rest[0], rest[1]))
        return min(options, key=tree_size) if options else None

    result = visit(*tree, 4, 0)  # First EI is already present.
    assert result is not None, width
    return ((ins(4, 'EI', 0xfb),) + result[0], result[1])


def decode(phase):
    register, high = ('C' if phase < 2 else 'B'), phase % 2
    ops = [ins(5, 'MOV A,' + register, 0x79 if register == 'C' else 0x78)]
    ops += [ins(4, 'RRC' if high else 'RLC', 0x0f if high else 0x07)] * 2
    ops += [ins(7, 'ANI 03CH', 0xe6, 0x3c)]
    if phase:
        ops += [ins(7, f'ORI {phase*64:03X}H', 0xf6, phase*64)]
    ops += [ins(5, 'MOV L,A', 0x6f), ins(7, 'MVI H,03CH', 0x26, PAGE),
            ins(15, 'PCHL', 0xe9)]
    return tuple(ops)


def program(phase, level):
    name = f'P{phase}_L{level}'
    if phase < 3:
        tree = (decode(phase + 1), ())
    else:
        normal, eof = name + '_WORD', name + '_EOF'
        prefix = (ins(5, 'DCR E', 0x1d), jump('JNZ', normal, 0xc2))
        link = (ins(10, 'POP H', 0xe1), ins(5, 'SPHL', 0xf9),
                ins(5, 'MOV A,H', 0x7c), ins(4, 'ORA L', 0xb5), jump('JZ', eof, 0xca))
        new_word = (ins(10, 'POP B', 0xc1),) + decode(0)
        tree = (prefix, ((None, (link, (
            (None, ((ins(10, 'POP D', 0xd1),) + new_word, ())),
            (eof, ((ins(7, 'HLT', 0x76),), ()))))),
            (normal, (new_word, ()))))
    return name, plan(tree, 4 + level*4)


def emit_tree(code, tree):
    for _, text, op, target in tree[0]:
        code.emit(text, *op)
        if target:
            code.fixups.append((len(code.data)-2, target))
    for label, child in tree[1]:
        if label:
            code.label(label)
        emit_tree(code, child)


def build(check, profile='balloon', cpu_hz=3500000):
    source_root = ROOT if profile == 'balloon' else ROOT / profile
    target_root = source_root if cpu_hz == 3500000 else source_root / 'clocks' / str(cpu_hz)
    direct = profile != 'balloon'
    rom_name = NAME if not direct else json.loads((source_root / 'profile.json').read_text(encoding='utf-8'))['name']
    source = json.loads((target_root / 'pcm4.json').read_text())
    assert source['cpu_hz'] == cpu_hz
    packed = bytes.fromhex(source['packed_hex'])
    assert source['period_t'] == PERIOD and source['pulses_per_sample'] == 2
    original = legacy.BASE.read_bytes()
    assert hashlib.sha256(original).hexdigest() == legacy.ORIGINAL_SHA
    rom = bytearray([0xff]*32768) if direct else bytearray(original)
    startup_timing = None
    if not direct and cpu_hz != 3500000:
        # Shared diagnostic tone: high=11+15*h T, low=26+15*l T.
        # h=l+1 gives equal halves; choose the closest original audible pitch.
        lo = round((3187*cpu_hz/3500000-52)/30)
        assert original[0xf8c:0xf8e] == bytes([0x2e, 105])
        assert original[0xf93:0xf95] == bytes([0x2e, 105])
        rom[0xf8d], rom[0xf94] = lo+1, lo
        ramp_counts = []
        for stage in legacy.META['ramp_stage_pc']:
            at = int(stage, 16) if isinstance(stage, str) else stage
            assert original[at] == 0x16 and original[at+2] == 0x06
            count = round(original[at+3]*cpu_hz/3500000)
            rom[at+3] = count
            ramp_counts.append(count)
        startup_timing = {'tone_period_t': 52+30*lo, 'tone_hz': cpu_hz/(52+30*lo),
                          'ramp_inner_counts': ramp_counts}
    probes, checks = set(), []
    for pc in range(0x200, 0xff0 - 8):
        if (original[pc] == 0x21 and original[pc+3:pc+5] == bytes([0x7e, 0xfe])
                and original[pc+6:pc+9] == bytes([0xc2, 0xc7, 0x0e])):
            address = int.from_bytes(original[pc+1:pc+3], 'little') & 0x7fff
            probes.add(address)
            checks.append((pc+5, address))
    assert len(checks) == 60
    if direct:
        probes, checks = set(), []
    ranges = [(3, 32768)] if direct else [(0xfb0, 0xff0), (0x10b0, 0x1100), (0x1100, 0x7c40), (0x7f86, 0x7ff0)]
    available = {at for lo, hi in ranges for at in range(lo, hi)} - probes
    for bank in range(0 if direct else 8):
        available.difference_update(range(bank*4096+0xff0, bank*4096+0xff4))
    available.difference_update(range(PAGE*256, PAGE*256+256))

    def reserve(start, size):
        assert all(at in available for at in range(start, start+size)), hex(start)
        available.difference_update(range(start, start+size))

    def spans():
        result = []
        for at in sorted(available):
            if result and result[-1][1] == at:
                result[-1][1] += 1
            else:
                result.append([at, at+1])
        return result

    def place(code):
        start = next(lo for lo, hi in spans() if hi-lo >= len(code.data))
        code.labels = {key: value+start-code.origin for key, value in code.labels.items()}
        code.origin = start
        reserve(start, len(code.data))

    head = Code(0x1100)
    head.label('VOICE')
    head.emit('DI', 0xf3)
    head.word('LXI SP,STREAM', 0x31, 'STREAM')
    head.emit('POP D', 0xd1)
    head.emit('POP B', 0xc1)
    for _, text, op, _ in decode(0):
        head.emit(text, *op)
    reserve(head.origin, len(head.data))
    codes = [head]
    for phase in range(4):
        for level in range(16):
            name, tree = program(phase, level)
            code = Code(0)
            code.label(name)
            emit_tree(code, tree)
            place(code)
            codes.append(code)

    labels = {key: value for code in codes for key, value in code.labels.items()}
    for phase in range(4):
        for level in range(16):
            at, target = PAGE*256+phase*64+level*4, labels[f'P{phase}_L{level}']
            rom[at:at+4] = bytes([0xc3, target & 255, target >> 8, 0])
    parts, index = [], 0
    # Header word: E=number of words (0 means 256), D unused. After the final
    # word a little-endian link points at the next header, or zero for EOF.
    for lo, hi in spans():
        at = lo
        while hi-at >= 6 and index < len(packed):
            count = min(256, (hi-at-4)//2, (len(packed)-index)//2)
            assert count
            rom[at:at+2] = bytes([count & 255, 0])
            rom[at+2:at+2+count*2] = packed[index:index+count*2]
            parts.append({'header': at, 'words': count, 'data': at+2, 'link': at+2+count*2})
            reserve(at, 4+count*2)
            at += 4+count*2
            index += count*2
    assert index == len(packed), (index, len(packed), len(available))
    for i, part in enumerate(parts):
        target = parts[i+1]['header'] if i+1 < len(parts) else 0
        part['target'] = target
        rom[part['link']:part['link']+2] = target.to_bytes(2, 'little')
    labels['STREAM'] = parts[0]['header']
    for code in codes:
        code.resolve(labels)
        rom[code.origin:code.pc] = code.data
    for dest, address in checks:
        if dest != address:
            rom[dest] = rom[address]
    for bit in range(0 if direct else 15):
        assert rom[0] != rom[1 << bit]
        assert rom[0x7fff] != rom[0x7fff ^ (1 << bit)]
    footers = []
    for bank in range(0 if direct else 8):
        at = bank*4096+0xff0
        rom[at:at+4] = legacy.footer(rom[bank*4096:(bank+1)*4096])
        footers.append({'address': f'{at:04X}', 'hex': rom[at:at+4].hex()})
    if direct:
        rom[:3] = bytes([0xc3, 0, 0x11])  # RESET -> VOICE; no diagnostics, tones or ramp.
    meta = {'name': rom_name, 'backend': 'i8080-asm', 'bytes': len(rom),
        'sha256': hashlib.sha256(rom).hexdigest(), 'original_sha256': legacy.ORIGINAL_SHA,
        'cpu_hz': cpu_hz, 'period_t': PERIOD, 'carrier_hz': cpu_hz/PERIOD,
        'pulses_per_sample': 2, 'sample_rate_hz': source['sample_rate_hz'],
        'sample_count': source['sample_count'], 'levels': 16, 'width_t': '4+4*level',
        'code_bytes': sum(len(code.data) for code in codes), 'dispatch_bytes': 256,
        'packed_bytes': len(packed), 'free_voice_region_bytes': len(available),
        'voice_code_start': '1100', 'ramp_start': legacy.META['ramp_start'],
        'ramp_stage_pc': legacy.META['ramp_stage_pc'], 'segments': parts,
        'footers': footers, 'address_tests': len(checks),
        'labels': {key: f'{value:04X}' for key, value in labels.items()},
        'hardware_tested': False, 'active_interrupts_supported': False}
    if startup_timing:
        meta['retimed_startup'] = startup_timing
    if direct:
        del meta['original_sha256']
        meta.update(startup='direct', diagnostics=False, soft_start=False, ramp_start=None, ramp_stage_pc=[])
    save(rom_name+'.bin', rom, check, target_root)
    save(rom_name+'.hex', legacy.hex_image(rom), check, target_root)
    asm = [f'; Intel 8080; two equal-width pulses/sample, each 109T at {cpu_hz/1e6:g} MHz.',
        '; Generated by build.py --backend i8080-asm --architecture i8080 --enable-asm.',
        '; BC=4 PCM nibbles; E=word count (0=256); HL/A scratch; SP=read-only ROM cursor.',
        '; No RAM writes, CALL or PUSH. INT inactive, no WAIT/HOLD. INTE is audio.',
        '; Portable arithmetic fallback remains selectable: voice.c / voice.h.',
        '; PCHL=5T; the dispatch table JMP adds 10T (included by the scheduler).']
    for code in codes:
        asm += ['', f'    ORG {code.origin:05X}H'] + code.source
    if direct:
        asm = ['; RESET jumps directly to VOICE. No diagnostics, beeps or soft start.',
               '    ORG 00000H', '    JMP VOICE'] + asm
    save(rom_name+'.asm', '\n'.join(asm)+'\n', check, target_root)
    save(rom_name+'.json', json.dumps(meta, indent=2)+'\n', check, target_root)
    print(f'{rom_name}: {meta["carrier_hz"]:.3f} Hz PWM; {meta["sample_rate_hz"]:.3f} samples/s; '
          f'{meta["code_bytes"]} code bytes; {len(available)} free bytes')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', choices=['c', 'i8080-asm'], default='c')
    parser.add_argument('--architecture', default='portable')
    parser.add_argument('--enable-asm', action='store_true')
    parser.add_argument('--profile', choices=['balloon', 'owl'], default='balloon')
    parser.add_argument('--cpu-hz', type=int, choices=[2000000, 2500000, 3500000], default=3500000)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.backend == 'i8080-asm':
        if args.architecture != 'i8080' or not args.enable_asm:
            parser.error('Assembly requires --architecture i8080 --enable-asm')
        build(args.check, args.profile, args.cpu_hz)
    else:
        print('Portable C backend selected: voice.c. Assembly ROM requires explicit opt-in.')


if __name__ == '__main__':
    main()
